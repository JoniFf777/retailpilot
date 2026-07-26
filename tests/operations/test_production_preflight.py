import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.routes import health
from app.core.settings import Settings
from app.main import create_app
from app.operations import (
    ProductionPreflightError,
    evaluate_production_preflight,
)
from scripts import check_production_config


def _ready_settings(**overrides) -> Settings:
    values = {
        "shopmind_deployment_profile": "production",
        "shopmind_deployment_replicas": 1,
        "shopmind_identity_provider": "trusted_header",
        "shopmind_trusted_proxy_authentication": True,
        "shopmind_governance_audit_enabled": True,
        "shopmind_runtime_cleanup_scheduled": True,
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


def test_development_profile_remains_unchanged_and_not_applicable() -> None:
    report = evaluate_production_preflight(Settings())

    assert report.profile == "development"
    assert report.status == "not_applicable"
    assert report.ready is False
    assert report.total_checks == 6
    assert report.passed_checks == 0
    assert report.failed_checks == 0
    assert {check.status for check in report.checks} == {"not_applicable"}
    assert {check.reason for check in report.checks} == {"development_profile"}


def test_production_profile_accepts_bounded_single_replica_configuration() -> None:
    report = evaluate_production_preflight(_ready_settings())

    assert report.profile == "production"
    assert report.status == "ready"
    assert report.ready is True
    assert report.passed_checks == report.total_checks == 6
    assert report.failed_checks == 0
    assert [check.check_id for check in report.checks] == [
        "identity.boundary",
        "coordination.topology",
        "governance.audit",
        "transport.rag",
        "retention.cleanup",
        "runtime.limits",
    ]


def test_production_profile_reports_all_unsafe_defaults_without_values() -> None:
    settings = Settings(shopmind_deployment_profile="production")
    report = evaluate_production_preflight(settings)
    checks = _check_map(report)
    serialized = report.model_dump_json()

    assert report.status == "blocked"
    assert report.ready is False
    assert report.failed_checks == 4
    assert checks["identity.boundary"].reason == (
        "development_identity_forbidden"
    )
    assert checks["governance.audit"].reason == "governance_audit_disabled"
    assert checks["retention.cleanup"].reason == (
        "retention_cleanup_unscheduled"
    )
    assert checks["runtime.limits"].reason == "runtime_limits_unbounded"
    for forbidden in (
        "database_url",
        "redis_url",
        "endpoint",
        "allowed_hosts",
        "secret",
        "token",
    ):
        assert forbidden not in serialized


def test_multi_replica_requires_configured_redis_coordination() -> None:
    local_report = evaluate_production_preflight(
        _ready_settings(shopmind_deployment_replicas=2)
    )
    missing_report = evaluate_production_preflight(
        _ready_settings(
            shopmind_deployment_replicas=2,
            shopmind_coordination_backend="redis",
        )
    )
    redis_report = evaluate_production_preflight(
        _ready_settings(
            shopmind_deployment_replicas=2,
            shopmind_coordination_backend="redis",
            shopmind_coordination_redis_url="redis://private-host:6379/0",
        )
    )

    assert _check_map(local_report)["coordination.topology"].reason == (
        "local_coordination_multi_replica"
    )
    assert _check_map(missing_report)["coordination.topology"].reason == (
        "redis_url_missing"
    )
    assert _check_map(redis_report)["coordination.topology"].reason == (
        "redis_coordination"
    )
    assert "private-host" not in redis_report.model_dump_json()


@pytest.mark.parametrize(
    ("endpoint", "allowed_hosts", "expected_status"),
    (
        (
            "https://rag.internal.example/v1/tasks",
            frozenset({"rag.internal.example"}),
            "passed",
        ),
        (
            "http://rag.internal.example/v1/tasks",
            frozenset({"rag.internal.example"}),
            "failed",
        ),
        (
            "https://other.internal.example/v1/tasks",
            frozenset({"rag.internal.example"}),
            "failed",
        ),
        (
            "https://rag.internal.example/v1/tasks?token=private",
            frozenset({"rag.internal.example"}),
            "failed",
        ),
    ),
)
def test_http_transport_requires_fixed_query_free_https_allowlist(
    endpoint,
    allowed_hosts,
    expected_status,
) -> None:
    report = evaluate_production_preflight(
        _ready_settings(
            shopmind_rag_agent_transport="http",
            shopmind_rag_agent_http_endpoint=endpoint,
            shopmind_rag_agent_http_allowed_hosts=allowed_hosts,
        )
    )

    assert _check_map(report)["transport.rag"].status == expected_status
    assert endpoint not in report.model_dump_json()


def test_application_creation_fails_closed_only_for_production() -> None:
    development = create_app(settings=Settings())
    ready = create_app(settings=_ready_settings())

    assert development.state.production_preflight.status == "not_applicable"
    assert ready.state.production_preflight.status == "ready"
    health_report = asyncio.run(
        health.production_preflight_health_check(
            SimpleNamespace(app=ready)
        )
    )
    assert health_report["profile"] == "production"
    assert health_report["status"] == "ready"
    with pytest.raises(
        ProductionPreflightError,
        match="production preflight failed",
    ) as raised:
        create_app(settings=Settings(shopmind_deployment_profile="production"))
    assert raised.value.report.status == "blocked"
    assert "database" not in str(raised.value)


def test_preflight_cli_writes_safe_artifact_and_sanitizes_settings_failure(
    capsys,
    monkeypatch,
    tmp_path,
) -> None:
    output = tmp_path / "production-preflight.json"
    monkeypatch.setattr(
        check_production_config.Settings,
        "from_env",
        lambda *args: _ready_settings(),
    )

    assert (
        check_production_config.main(["--output-json", str(output)]) == 0
    )
    assert "status: ready" in capsys.readouterr().out
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "shopmind.production-preflight.v1"
    assert artifact["passed_checks"] == artifact["total_checks"] == 6

    private_error = "private URL, signing secret, and database password"

    def fail_settings(*_args):
        raise RuntimeError(private_error)

    monkeypatch.setattr(
        check_production_config.Settings,
        "from_env",
        fail_settings,
    )
    assert check_production_config.main([]) == 1
    failure_output = capsys.readouterr().out
    assert "settings_invalid" in failure_output
    assert private_error not in failure_output


def test_ci_gates_and_uploads_production_preflight_before_evaluations() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = (
        "python scripts/check_production_config.py --output-json "
        "artifacts/v6-production-preflight/summary.json"
    )

    assert "Gate V6 production configuration preflight" in workflow
    assert command in workflow
    assert "name: v6-production-preflight" in workflow
    assert "tests/operations" in workflow
    assert workflow.index(
        "Gate V6 production configuration preflight"
    ) < workflow.index("Gate V5 planner policy")
