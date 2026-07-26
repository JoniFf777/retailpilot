from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.governance import GovernanceAuditMonitorSnapshot
from app.operations import (
    DeploymentReadinessReport,
    GovernanceAuditHealthEvidence,
    ReleaseOperationInput,
    evaluate_release_operation,
)
from app.runtime import (
    ServiceHealthReport,
    ServiceMetricsSnapshot,
    evaluate_service_slo,
)
from scripts import check_release_operations


def _readiness(
    *,
    ready: bool = True,
    coordination_ready: bool = True,
) -> DeploymentReadinessReport:
    checks = [
        {
            "check_id": "configuration.preflight",
            "category": "configuration",
            "status": "passed",
            "reason": "configuration_ready",
        },
        {
            "check_id": "postgres.connectivity",
            "category": "database",
            "status": "passed",
            "reason": "postgres_reachable",
        },
        {
            "check_id": "postgres.migration",
            "category": "database",
            "status": "passed",
            "reason": "migration_current",
        },
        {
            "check_id": "coordination.backend",
            "category": "coordination",
            "status": "passed" if coordination_ready else "failed",
            "reason": (
                "local_coordination_ready"
                if coordination_ready
                else "coordination_unavailable"
            ),
        },
        {
            "check_id": "retention.cleanup",
            "category": "retention",
            "status": "passed",
            "reason": "cleanup_recent",
        },
    ]
    failed = sum(check["status"] == "failed" for check in checks)
    effective_ready = ready and failed == 0
    if not ready and failed == 0:
        checks[1] = {
            **checks[1],
            "status": "failed",
            "reason": "postgres_unavailable",
        }
        failed = 1
    return DeploymentReadinessReport(
        profile="production",
        status="ready" if effective_ready else "blocked",
        ready=effective_ready,
        total_checks=len(checks),
        passed_checks=len(checks) - failed,
        failed_checks=failed,
        not_applicable_checks=0,
        checks=checks,
    )


def _service_health(
    status: str = "met",
) -> ServiceHealthReport:
    if status == "insufficient_data":
        runs = successful = failed = 0
        p50 = p95 = maximum = None
    elif status == "breached":
        runs, successful, failed = 20, 18, 2
        p50, p95, maximum = 100.0, 6_000.0, 6_000.0
    else:
        runs, successful, failed = 20, 20, 0
        p50, p95, maximum = 100.0, 200.0, 250.0
    metrics = ServiceMetricsSnapshot(
        status="active" if runs else "idle",
        runs_total=runs,
        chat_runs_total=runs,
        confirmation_runs_total=0,
        completed_total=successful,
        confirmation_required_total=0,
        cancelled_total=0,
        failed_total=failed,
        replayed_total=0,
        measured_token_runs_total=0,
        total_tokens=0,
        measured_cost_runs_total=0,
        total_cost_usd=0,
        tool_calls_total=0,
        steps_total=0,
        latency_observations_total=runs,
        latency_window_capacity=1_000,
        latency_window_runs=runs,
        slo_window_eligible_runs=runs,
        slo_window_successful_runs=successful,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_max_ms=maximum,
        last_status="completed" if runs else None,
    )
    slo = evaluate_service_slo(metrics)
    assert slo.status == status
    return ServiceHealthReport(status=status, metrics=metrics, slo=slo)


def _audit_health(
    status: str = "ok",
) -> GovernanceAuditHealthEvidence:
    enabled = status != "disabled"
    warning = status == "warning"
    degraded = status == "degraded"
    attempts = 3 if degraded else int(warning)
    failures = attempts
    monitor = GovernanceAuditMonitorSnapshot(
        status=(
            "alerting"
            if degraded
            else "warning"
            if warning
            else "idle"
        ),
        alert_active=degraded,
        alert_failure_threshold=3,
        emission_calls_total=attempts,
        storage_attempts_total=attempts,
        requested_records_total=attempts,
        persisted_records_total=0,
        duplicate_records_total=0,
        skipped_calls_total=0,
        failed_calls_total=attempts,
        consecutive_failures=failures,
        alert_transitions_total=int(degraded),
        recovery_transitions_total=0,
        last_status="failed" if attempts else None,
        last_reason="storage_unavailable" if attempts else None,
    )
    return GovernanceAuditHealthEvidence(
        schema_version="shopmind.governance-audit-health.v1",
        status=status,
        audit_enabled=enabled,
        monitor=monitor,
    )


def _input(
    operation: str,
    *,
    liveness_status: str = "ok",
    readiness: DeploymentReadinessReport | None = None,
    service_status: str = "met",
    audit_status: str = "ok",
    rollback_target_status: str = "not_applicable",
    rollback_migration_status: str = "not_applicable",
) -> ReleaseOperationInput:
    return ReleaseOperationInput(
        operation=operation,
        liveness_status=liveness_status,
        readiness=readiness or _readiness(),
        service_health=_service_health(service_status),
        governance_audit_health=_audit_health(audit_status),
        rollback_target_status=rollback_target_status,
        rollback_migration_status=rollback_migration_status,
    )


def test_deployment_ready_report_is_ordered_versioned_and_value_free() -> None:
    report = evaluate_release_operation(_input("deployment"))
    serialized = report.model_dump_json()

    assert report.schema_version == "shopmind.release-operation-check.v1"
    assert report.status == "ready"
    assert report.recommended_action == "continue_rollout"
    assert report.passed is True
    assert report.total_checks == 7
    assert report.passed_checks == 5
    assert report.not_applicable_checks == 2
    assert [check.check_id for check in report.checks] == [
        "health.liveness",
        "readiness.deployment",
        "coordination.backend",
        "service.slo",
        "governance.audit",
        "rollback.target",
        "rollback.migration",
    ]
    for forbidden in (
        "request_id",
        "user_id",
        "database_url",
        "redis_url",
        "private-host",
    ):
        assert forbidden not in serialized


def test_deployment_holds_for_warmup_and_blocks_failed_boundaries() -> None:
    warmup = evaluate_release_operation(
        _input("deployment", service_status="insufficient_data")
    )
    warning = evaluate_release_operation(
        _input("deployment", audit_status="warning")
    )
    blocked = evaluate_release_operation(
        _input(
            "deployment",
            readiness=_readiness(coordination_ready=False),
        )
    )
    development = evaluate_release_operation(
        _input(
            "deployment",
            readiness=_readiness().model_copy(
                update={"profile": "development"}
            ),
        )
    )

    assert (warmup.status, warmup.recommended_action) == (
        "hold",
        "hold_rollout",
    )
    assert warmup.waiting_checks == 1
    assert warning.status == "hold"
    assert blocked.status == "blocked"
    assert blocked.recommended_action == "stop_rollout"
    assert blocked.failed_checks == 2
    assert development.status == "blocked"
    assert {
        check.reason
        for check in development.checks
        if check.status == "failed"
    } == {"readiness_blocked"}


def test_rollback_fails_closed_without_target_and_migration_proof() -> None:
    with pytest.raises(ValidationError, match="target evidence"):
        _input("rollback")

    ready = evaluate_release_operation(
        _input(
            "rollback",
            rollback_target_status="verified",
            rollback_migration_status="compatible",
        )
    )
    incompatible = evaluate_release_operation(
        _input(
            "rollback",
            rollback_target_status="verified",
            rollback_migration_status="incompatible",
        )
    )

    assert (ready.status, ready.recommended_action, ready.passed) == (
        "ready",
        "execute_rollback",
        True,
    )
    assert ready.not_applicable_checks == 0
    assert incompatible.status == "blocked"
    assert incompatible.recommended_action == "block_rollback"
    assert {
        check.reason
        for check in incompatible.checks
        if check.status == "failed"
    } == {"rollback_migration_incompatible"}


def test_incident_check_distinguishes_stable_observe_and_mitigate() -> None:
    stable = evaluate_release_operation(_input("incident"))
    observe = evaluate_release_operation(
        _input("incident", service_status="insufficient_data")
    )
    mitigate = evaluate_release_operation(
        _input(
            "incident",
            service_status="breached",
            audit_status="degraded",
            liveness_status="unavailable",
        )
    )

    assert (stable.status, stable.recommended_action) == (
        "stable",
        "no_action",
    )
    assert (observe.status, observe.recommended_action) == (
        "observe",
        "observe",
    )
    assert (mitigate.status, mitigate.recommended_action) == (
        "action_required",
        "mitigate",
    )
    assert mitigate.failed_checks == 3


def test_release_input_rejects_inconsistent_or_extraneous_evidence() -> None:
    payload = _input("deployment").model_dump(mode="json")
    payload["service_health"]["status"] = "breached"
    with pytest.raises(ValidationError, match="Service health evidence"):
        ReleaseOperationInput.model_validate(payload)

    payload = _input("deployment").model_dump(mode="json")
    payload["rollback_target_status"] = "verified"
    with pytest.raises(ValidationError, match="invalid for this operation"):
        ReleaseOperationInput.model_validate(payload)

    audit_payload = _audit_health().model_dump(mode="json")
    audit_payload["status"] = "degraded"
    with pytest.raises(ValidationError, match="audit health evidence"):
        GovernanceAuditHealthEvidence.model_validate(audit_payload)

    audit_payload = _audit_health().model_dump(mode="json")
    audit_payload["monitor"]["status"] = "alerting"
    with pytest.raises(ValidationError, match="monitor evidence"):
        GovernanceAuditHealthEvidence.model_validate(audit_payload)


def test_release_operations_cli_writes_artifact_and_sanitizes_invalid_input(
    capsys,
    tmp_path,
) -> None:
    input_path = tmp_path / "release-input.json"
    output_path = tmp_path / "release-report.json"
    input_path.write_text(
        _input("deployment").model_dump_json(),
        encoding="utf-8",
    )

    assert (
        check_release_operations.main(
            [
                "--input-json",
                str(input_path),
                "--output-json",
                str(output_path),
            ]
        )
        == 0
    )
    assert "status: ready" in capsys.readouterr().out
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["recommended_action"] == "continue_rollout"

    private_value = "postgresql://user:secret@private-host/database"
    input_path.write_text(
        json.dumps({"schema_version": private_value}),
        encoding="utf-8",
    )
    assert (
        check_release_operations.main(["--input-json", str(input_path)])
        == 1
    )
    failure_output = capsys.readouterr().out
    assert "input_invalid" in failure_output
    assert private_value not in failure_output


def test_ci_runs_and_uploads_release_operations_gate() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "Gate V6 release operations checks" in workflow
    assert (
        "python evaluation/run_release_operations_eval.py --output-json "
        "artifacts/v6-release-operations/summary.json"
    ) in workflow
    assert "name: v6-release-operations" in workflow
