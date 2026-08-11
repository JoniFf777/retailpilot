from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.core.langsmith_policy import initialize_langsmith_runtime
from app.core.settings import Settings
from app.main import create_app
from app.operations import evaluate_deployment_readiness, evaluate_production_preflight
from app.recommendation.rag import OfflineDemoRecommendationEvidenceProvider
from app.schemas.catalog import CatalogSkuCandidate
from scripts.smoke_shopmind_demo import (
    DemoSmokeError,
    _assert_offline_demo_readiness,
)


def test_offline_demo_forces_langsmith_off_even_with_stale_process_values(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "offline-demo")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

    runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.profile == "offline-demo"
    assert runtime.tracing_enabled is False
    assert runtime.project == "shopmind-offline-demo"


def test_offline_demo_is_local_ready_and_does_not_run_production_preflight():
    settings = Settings(shopmind_deployment_profile="offline-demo")
    preflight = evaluate_production_preflight(settings)

    def session_factory():
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        engine = create_engine("sqlite:///:memory:")
        connection = engine.connect()
        connection.execute(text("create table alembic_version (version_num varchar(64))"))
        connection.execute(text("insert into alembic_version values ('0014_shopmind_outbox_events')"))
        return Session(bind=connection)

    readiness = evaluate_deployment_readiness(
        settings,
        session_factory=session_factory,
        coordination_probe=lambda _settings: None,
        clock=lambda: datetime.now(timezone.utc),
    )

    assert preflight.status == "not_applicable"
    assert preflight.profile == "offline-demo"
    assert readiness.profile == "offline-demo"
    assert readiness.ready is True
    assert create_app(settings=settings).state.production_preflight.status == "not_applicable"


def test_offline_demo_evidence_provider_never_initializes_embeddings():
    candidate = CatalogSkuCandidate(
        sku_id="00000000-0000-0000-0000-000000000001",
        product_id="00000000-0000-0000-0000-000000000002",
        product_code="DEMO-001",
        product_name="Demo laptop",
        brand="Demo",
        sku_code="DEMO-001-SKU",
        sku_name="Demo laptop",
        money_amount="1.00",
        currency="CNY",
        variant_attributes={},
        available_quantity=1,
        legacy_product_id=None,
    )

    evidence = OfflineDemoRecommendationEvidenceProvider().retrieve(
        message="offline demo",
        top_k=[candidate],
    )

    assert evidence.product_evidence == {candidate.sku_code: []}
    assert evidence.policy_evidence == []
    assert evidence.diagnostics["offline_demo"] is True


def test_demo_smoke_rejects_a_ready_non_demo_backend():
    with pytest.raises(DemoSmokeError, match="offline-demo profile"):
        _assert_offline_demo_readiness(
            {"profile": "development", "status": "ready", "ready": True}
        )
