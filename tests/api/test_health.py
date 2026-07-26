import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import health
from app.core.settings import Settings
from app.governance import (
    GovernanceAuditEmissionMonitor,
    GovernanceAuditEmissionReason,
    GovernanceAuditEmissionResult,
    GovernanceAuditEmissionStatus,
)
from app.main import app, create_app
from app.runtime import (
    RunOperation,
    RunResult,
    RunStatus,
    RuntimeServiceMonitor,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_preflight_health_exposes_closed_development_report() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/preflight")
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema_version"] == "shopmind.production-preflight.v1"
    assert payload["profile"] == "development"
    assert payload["status"] == "not_applicable"
    assert payload["ready"] is False
    assert payload["total_checks"] == 6
    assert payload["failed_checks"] == 0


def test_preflight_health_report_never_exposes_configuration_values() -> None:
    report = health.get_production_preflight_health_report(
        SimpleNamespace(
            shopmind_deployment_profile="production",
            shopmind_deployment_replicas=2,
            shopmind_identity_provider="trusted_header",
            shopmind_trusted_proxy_authentication=False,
            shopmind_coordination_backend="redis",
            shopmind_coordination_redis_url=None,
            shopmind_governance_audit_enabled=False,
            shopmind_rag_agent_transport="http",
            shopmind_rag_agent_http_endpoint=(
                "https://private.internal.example/v1/tasks"
            ),
            shopmind_rag_agent_http_allowed_hosts=frozenset(),
            shopmind_runtime_cleanup_scheduled=False,
            shopmind_runtime_max_duration_ms=None,
            shopmind_runtime_max_steps=None,
            shopmind_runtime_max_tool_calls=None,
            shopmind_runtime_max_total_tokens=None,
            shopmind_runtime_max_cost_usd=None,
        )
    )
    serialized = json.dumps(report)

    assert report["status"] == "blocked"
    assert report["failed_checks"] == 6
    assert "private.internal.example" not in serialized
    assert "endpoint" not in serialized
    assert "shopmind_coordination_redis_url" not in serialized


@pytest.mark.anyio
async def test_governance_audit_health_exposes_only_sanitized_metrics(
    monkeypatch,
) -> None:
    monitor = GovernanceAuditEmissionMonitor(alert_failure_threshold=1)
    monitor.observe(
        GovernanceAuditEmissionResult(
            status=GovernanceAuditEmissionStatus.FAILED,
            reason=GovernanceAuditEmissionReason.STORAGE_UNAVAILABLE,
            requested_records=2,
            persisted_records=0,
            duplicate_records=0,
        )
    )
    monkeypatch.setattr(health, "governance_audit_monitor", monitor)
    monkeypatch.setattr(
        health,
        "get_settings",
        lambda: SimpleNamespace(shopmind_governance_audit_enabled=True),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/governance-audit")
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema_version"] == (
        "shopmind.governance-audit-health.v1"
    )
    assert payload["status"] == "degraded"
    assert payload["audit_enabled"] is True
    assert payload["monitor"]["status"] == "alerting"
    assert payload["monitor"]["failed_calls_total"] == 1
    assert payload["monitor"]["requested_records_total"] == 2
    serialized = response.text
    for forbidden in (
        "owner_id",
        "subject_id",
        "message",
        "arguments",
        "credentials",
        "connection_url",
    ):
        assert forbidden not in serialized


def test_governance_audit_health_reports_default_off_without_mutating_monitor():
    monitor = GovernanceAuditEmissionMonitor(alert_failure_threshold=3)

    report = health.get_governance_audit_health_report(
        monitor,
        SimpleNamespace(shopmind_governance_audit_enabled=False),
    )

    assert report["status"] == "disabled"
    assert report["audit_enabled"] is False
    assert report["monitor"]["status"] == "idle"
    assert report["monitor"]["emission_calls_total"] == 0


@pytest.mark.anyio
async def test_service_metrics_health_exposes_closed_slo_and_returns_200(
    monkeypatch,
) -> None:
    monitor = RuntimeServiceMonitor()
    private_result = RunResult(
        run_id="private-health-run",
        runtime_thread_id="private-health-thread",
        trace_id="private-health-trace",
        request_id="private-health-request",
        user_id="private-health-user",
        status=RunStatus.FAILED,
    )
    for _ in range(2):
        monitor.observe(
            private_result,
            operation=RunOperation.CHAT,
            duration_ms=1_000,
        )
    monkeypatch.setattr(health, "runtime_service_monitor", monitor)
    test_app = create_app(
        settings=Settings(
            shopmind_service_slo_min_runs=2,
            shopmind_service_slo_success_rate_target=0.99,
            shopmind_service_slo_p95_latency_ms=500,
        )
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/service-metrics")
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema_version"] == "shopmind.service-health.v1"
    assert payload["status"] == "breached"
    assert payload["metrics"]["schema_version"] == (
        "shopmind.service-metrics.v1"
    )
    assert payload["slo"]["schema_version"] == "shopmind.service-slo.v1"
    assert payload["metrics"]["failed_total"] == 2
    assert payload["slo"]["observed_success_rate"] == 0
    for private_value in (
        "private-health-run",
        "private-health-thread",
        "private-health-trace",
        "private-health-request",
        "private-health-user",
    ):
        assert private_value not in response.text


@pytest.mark.anyio
async def test_postgres_health_check_returns_report(monkeypatch) -> None:
    def fake_report():
        return {
            "status": "ok",
            "database": "retailpilot_v2_smoke",
            "user": "postgres",
            "alembic_version": "0002_documents_pgvector",
        }

    monkeypatch.setattr(health, "get_postgres_health_report", fake_report)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/postgres")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "retailpilot_v2_smoke",
        "user": "postgres",
        "alembic_version": "0002_documents_pgvector",
    }


@pytest.mark.anyio
async def test_postgres_health_check_returns_503_on_failure(monkeypatch) -> None:
    def fail_report():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(health, "get_postgres_health_report", fail_report)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/postgres")

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "error"
    assert response.json()["detail"]["message"] == "PostgreSQL health check failed"
    assert response.json()["detail"]["reason"] == "postgres_unavailable"
    assert "database unavailable" not in response.text
