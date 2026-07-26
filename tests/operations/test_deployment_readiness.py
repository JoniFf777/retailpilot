from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.routes import health
from app.core.settings import Settings
from app.db.version import MIGRATION_HEAD
from app.operations import (
    RuntimeCleanupEvidenceError,
    evaluate_deployment_readiness,
    load_runtime_cleanup_evidence,
    write_runtime_cleanup_evidence,
)
from app.main import create_app
from scripts import check_deployment_readiness


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def _session_factory(*, migration: str = MIGRATION_HEAD):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("create table alembic_version (version_num varchar(64))")
        )
        connection.execute(
            text("insert into alembic_version values (:version)"),
            {"version": migration},
        )
    return sessionmaker(bind=engine)


def _production_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "shopmind_deployment_profile": "production",
        "shopmind_deployment_replicas": 1,
        "shopmind_identity_provider": "trusted_header",
        "shopmind_trusted_proxy_authentication": True,
        "shopmind_governance_audit_enabled": True,
        "shopmind_runtime_cleanup_scheduled": True,
        "shopmind_runtime_cleanup_evidence_path": str(
            tmp_path / "cleanup-evidence.json"
        ),
        "shopmind_runtime_cleanup_evidence_max_age_seconds": 90_000,
        "shopmind_runtime_max_duration_ms": 30_000,
        "shopmind_runtime_max_steps": 20,
        "shopmind_runtime_max_tool_calls": 10,
        "shopmind_runtime_max_total_tokens": 20_000,
        "shopmind_runtime_max_cost_usd": 1.0,
    }
    values.update(overrides)
    return Settings(**values)


def _check_map(report):
    return {check.check_id: check for check in report.checks}


def _evaluate(settings: Settings, **overrides):
    values = {
        "session_factory": _session_factory(),
        "coordination_probe": lambda _settings: None,
        "clock": lambda: NOW,
    }
    values.update(overrides)
    return evaluate_deployment_readiness(settings, **values)


def test_cleanup_evidence_round_trip_is_minimal_and_atomic(tmp_path) -> None:
    target = tmp_path / "nested" / "cleanup.json"
    evidence = write_runtime_cleanup_evidence(target, completed_at=NOW)
    loaded = load_runtime_cleanup_evidence(target)
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert loaded == evidence
    assert payload == {
        "schema_version": "shopmind.runtime-cleanup-evidence.v1",
        "status": "succeeded",
        "completed_at": "2026-07-26T08:00:00Z",
    }
    assert list(target.parent.glob("*.tmp")) == []


def test_cleanup_evidence_rejects_naive_or_arbitrary_payloads(tmp_path) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        write_runtime_cleanup_evidence(
            tmp_path / "naive.json",
            completed_at=datetime(2026, 7, 26, 8, 0),
        )

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        '{"status":"succeeded","completed_at":"2026-07-26T08:00:00Z",'
        '"owner_id":"private"}',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeCleanupEvidenceError) as raised:
        load_runtime_cleanup_evidence(invalid)
    assert "private" not in str(raised.value)


def test_development_readiness_probes_live_dependencies_without_cleanup() -> None:
    report = _evaluate(Settings())
    checks = _check_map(report)

    assert report.status == "ready"
    assert report.ready is True
    assert report.total_checks == 5
    assert report.passed_checks == 3
    assert report.failed_checks == 0
    assert report.not_applicable_checks == 2
    assert checks["configuration.preflight"].reason == "development_profile"
    assert checks["retention.cleanup"].reason == "cleanup_not_required"


def test_production_readiness_accepts_fresh_cleanup_evidence(tmp_path) -> None:
    settings = _production_settings(tmp_path)
    write_runtime_cleanup_evidence(
        settings.shopmind_runtime_cleanup_evidence_path,
        completed_at=NOW - timedelta(minutes=5),
    )

    report = _evaluate(settings)

    assert report.status == "ready"
    assert report.ready is True
    assert report.passed_checks == report.total_checks == 5
    assert [check.check_id for check in report.checks] == [
        "configuration.preflight",
        "postgres.connectivity",
        "postgres.migration",
        "coordination.backend",
        "retention.cleanup",
    ]
    assert _check_map(report)["retention.cleanup"].reason == "cleanup_recent"


@pytest.mark.parametrize(
    ("settings_overrides", "evidence_age", "expected_reason"),
    (
        (
            {"shopmind_runtime_cleanup_scheduled": False},
            None,
            "cleanup_unscheduled",
        ),
        (
            {"shopmind_runtime_cleanup_evidence_path": None},
            None,
            "cleanup_evidence_unconfigured",
        ),
        ({}, None, "cleanup_evidence_missing"),
        ({}, timedelta(days=2), "cleanup_evidence_stale"),
        ({}, timedelta(minutes=-1), "cleanup_evidence_invalid"),
    ),
)
def test_production_readiness_blocks_without_recent_cleanup_proof(
    tmp_path,
    settings_overrides,
    evidence_age,
    expected_reason,
) -> None:
    settings = _production_settings(tmp_path, **settings_overrides)
    if (
        evidence_age is not None
        and settings.shopmind_runtime_cleanup_evidence_path is not None
    ):
        write_runtime_cleanup_evidence(
            settings.shopmind_runtime_cleanup_evidence_path,
            completed_at=NOW - evidence_age,
        )

    report = _evaluate(settings)

    assert report.status == "blocked"
    assert report.ready is False
    assert _check_map(report)["retention.cleanup"].reason == expected_reason


def test_readiness_sanitizes_database_coordination_and_evidence_failures(
    tmp_path,
) -> None:
    private_value = "redis://secret@private.internal:6379/0"
    settings = _production_settings(
        tmp_path,
        shopmind_coordination_backend="redis",
        shopmind_coordination_redis_url=private_value,
    )

    def database_failure():
        raise RuntimeError(f"database {private_value}")

    def coordination_failure(_settings):
        raise RuntimeError(private_value)

    def evidence_failure(_path):
        raise RuntimeError(private_value)

    report = evaluate_deployment_readiness(
        settings,
        session_factory=database_failure,
        coordination_probe=coordination_failure,
        cleanup_evidence_loader=evidence_failure,
        clock=lambda: NOW,
    )
    serialized = report.model_dump_json()
    checks = _check_map(report)

    assert report.failed_checks == 4
    assert checks["postgres.connectivity"].reason == "postgres_unavailable"
    assert checks["postgres.migration"].reason == "migration_unavailable"
    assert checks["coordination.backend"].reason == "coordination_unavailable"
    assert checks["retention.cleanup"].reason == "cleanup_evidence_invalid"
    assert private_value not in serialized
    for forbidden in ("database_url", "redis_url", "error", "path"):
        assert forbidden not in serialized


def test_readiness_blocks_outdated_migration_without_exposing_version() -> None:
    report = evaluate_deployment_readiness(
        Settings(),
        session_factory=_session_factory(migration="private-branch-version"),
        coordination_probe=lambda _settings: None,
        clock=lambda: NOW,
    )

    assert _check_map(report)["postgres.migration"].reason == (
        "migration_outdated"
    )
    assert "private-branch-version" not in report.model_dump_json()


def test_readiness_health_endpoint_uses_status_code_and_closed_payload(
    monkeypatch,
) -> None:
    ready = _evaluate(Settings()).model_dump(mode="json")
    application = create_app(settings=Settings())
    monkeypatch.setattr(
        health,
        "get_deployment_readiness_health_report",
        lambda **_kwargs: ready,
    )

    response = asyncio.run(
        health.deployment_readiness_health_check(
            type("Request", (), {"app": application})()
        )
    )
    assert response.status_code == 200
    assert json.loads(response.body)["schema_version"] == (
        "shopmind.deployment-readiness.v1"
    )

    blocked = {**ready, "status": "blocked", "ready": False}
    blocked["checks"] = [
        {
            **check,
            "status": "failed",
            "reason": "postgres_unavailable",
        }
        if check["check_id"] == "postgres.connectivity"
        else check
        for check in ready["checks"]
    ]
    blocked["passed_checks"] -= 1
    blocked["failed_checks"] = 1
    monkeypatch.setattr(
        health,
        "get_deployment_readiness_health_report",
        lambda **_kwargs: blocked,
    )
    response = asyncio.run(
        health.deployment_readiness_health_check(
            type("Request", (), {"app": application})()
        )
    )
    assert response.status_code == 503
    assert "postgres_unavailable" in response.body.decode()


def test_readiness_cli_writes_artifact_and_sanitizes_settings_failure(
    capsys,
    monkeypatch,
    tmp_path,
) -> None:
    output = tmp_path / "readiness.json"
    ready = _evaluate(Settings())
    monkeypatch.setattr(
        check_deployment_readiness.Settings,
        "from_env",
        lambda: Settings(),
    )
    monkeypatch.setattr(
        check_deployment_readiness,
        "evaluate_deployment_readiness",
        lambda _settings: ready,
    )

    assert (
        check_deployment_readiness.main(
            ["--output-json", str(output)]
        )
        == 0
    )
    assert "status: ready" in capsys.readouterr().out
    assert json.loads(output.read_text(encoding="utf-8"))["ready"] is True

    private_error = "postgresql://user:secret@private-host/database"

    def settings_failure():
        raise RuntimeError(private_error)

    monkeypatch.setattr(
        check_deployment_readiness.Settings,
        "from_env",
        settings_failure,
    )
    assert check_deployment_readiness.main([]) == 1
    failure_output = capsys.readouterr().out
    assert "settings_invalid" in failure_output
    assert private_error not in failure_output


def test_postgres_integration_ci_records_live_readiness_artifact() -> None:
    workflow = Path(
        ".github/workflows/postgres_integration.yml"
    ).read_text(encoding="utf-8")

    assert "Gate V6 deployment readiness" in workflow
    assert "python scripts/cleanup_runtime_persistence.py" in workflow
    assert (
        "python scripts/check_deployment_readiness.py --output-json "
        "artifacts/v6-deployment-readiness/summary.json"
    ) in workflow
    assert "name: v6-deployment-readiness" in workflow
