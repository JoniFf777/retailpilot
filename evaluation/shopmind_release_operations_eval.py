"""Deterministic release-operation checks for rollout and incident policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.governance import GovernanceAuditMonitorSnapshot
from app.operations import (
    GovernanceAuditHealthEvidence,
    ReleaseOperationInput,
    evaluate_release_operation,
)
from app.runtime import (
    ServiceHealthReport,
    ServiceMetricsSnapshot,
    evaluate_service_slo,
)


RELEASE_OPERATIONS_EVAL_SCHEMA_VERSION = (
    "shopmind.release-operations-eval.v1"
)
RELEASE_OPERATIONS_SCENARIOS: tuple[str, ...] = (
    "deployment_ready",
    "deployment_warmup",
    "deployment_blocked",
    "rollback_ready",
    "rollback_unverified",
    "incident_stable",
    "incident_escalation",
)


def _readiness(*, ready: bool = True, coordination: bool = True) -> dict:
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
            "status": "passed" if coordination else "failed",
            "reason": (
                "local_coordination_ready"
                if coordination
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
    if not ready and coordination:
        checks[1] = {
            **checks[1],
            "status": "failed",
            "reason": "postgres_unavailable",
        }
    failures = sum(check["status"] == "failed" for check in checks)
    return {
        "profile": "production",
        "status": "ready" if not failures else "blocked",
        "ready": not failures,
        "total_checks": len(checks),
        "passed_checks": len(checks) - failures,
        "failed_checks": failures,
        "not_applicable_checks": 0,
        "checks": checks,
    }


def _service_health(status: str) -> ServiceHealthReport:
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
    return ServiceHealthReport(status=slo.status, metrics=metrics, slo=slo)


def _audit_health(status: str) -> GovernanceAuditHealthEvidence:
    degraded = status == "degraded"
    warning = status == "warning"
    failures = 3 if degraded else int(warning)
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
        emission_calls_total=failures,
        storage_attempts_total=failures,
        requested_records_total=failures,
        persisted_records_total=0,
        duplicate_records_total=0,
        skipped_calls_total=0,
        failed_calls_total=failures,
        consecutive_failures=failures,
        alert_transitions_total=int(degraded),
        recovery_transitions_total=0,
        last_status="failed" if failures else None,
        last_reason="storage_unavailable" if failures else None,
    )
    return GovernanceAuditHealthEvidence(
        schema_version="shopmind.governance-audit-health.v1",
        status=status,
        audit_enabled=True,
        monitor=monitor,
    )


def _evidence(
    operation: str,
    *,
    readiness_ready: bool = True,
    coordination_ready: bool = True,
    service_status: str = "met",
    audit_status: str = "ok",
    liveness_status: str = "ok",
    rollback_target_status: str = "not_applicable",
    rollback_migration_status: str = "not_applicable",
) -> ReleaseOperationInput:
    return ReleaseOperationInput(
        operation=operation,
        liveness_status=liveness_status,
        readiness=_readiness(
            ready=readiness_ready,
            coordination=coordination_ready,
        ),
        service_health=_service_health(service_status),
        governance_audit_health=_audit_health(audit_status),
        rollback_target_status=rollback_target_status,
        rollback_migration_status=rollback_migration_status,
    )


def _case_result(
    name: str,
    evidence: ReleaseOperationInput,
    *,
    expected_status: str,
    expected_action: str,
    expected_failed: int,
    expected_waiting: int,
) -> dict[str, Any]:
    report = evaluate_release_operation(evidence)
    check_ids = [check.check_id for check in report.checks]
    checks: Mapping[str, bool] = {
        "schema_version": (
            report.schema_version == "shopmind.release-operation-check.v1"
        ),
        "status": report.status == expected_status,
        "recommended_action": (
            report.recommended_action == expected_action
        ),
        "failed_count": report.failed_checks == expected_failed,
        "waiting_count": report.waiting_checks == expected_waiting,
        "ordered_boundaries": check_ids
        == [
            "health.liveness",
            "readiness.deployment",
            "coordination.backend",
            "service.slo",
            "governance.audit",
            "rollback.target",
            "rollback.migration",
        ],
    }
    failures = [check_id for check_id, passed in checks.items() if not passed]
    return {
        "name": name,
        "passed": not failures,
        "checks_passed": sum(checks.values()),
        "total_checks": len(checks),
        "failures": failures,
        "outcome": {
            "operation": report.operation,
            "status": report.status,
            "recommended_action": report.recommended_action,
            "failed_checks": report.failed_checks,
            "waiting_checks": report.waiting_checks,
        },
    }


def evaluate_release_operations() -> dict[str, Any]:
    cases = [
        _case_result(
            "deployment_ready",
            _evidence("deployment"),
            expected_status="ready",
            expected_action="continue_rollout",
            expected_failed=0,
            expected_waiting=0,
        ),
        _case_result(
            "deployment_warmup",
            _evidence("deployment", service_status="insufficient_data"),
            expected_status="hold",
            expected_action="hold_rollout",
            expected_failed=0,
            expected_waiting=1,
        ),
        _case_result(
            "deployment_blocked",
            _evidence(
                "deployment",
                readiness_ready=False,
                coordination_ready=False,
            ),
            expected_status="blocked",
            expected_action="stop_rollout",
            expected_failed=2,
            expected_waiting=0,
        ),
        _case_result(
            "rollback_ready",
            _evidence(
                "rollback",
                rollback_target_status="verified",
                rollback_migration_status="compatible",
            ),
            expected_status="ready",
            expected_action="execute_rollback",
            expected_failed=0,
            expected_waiting=0,
        ),
        _case_result(
            "rollback_unverified",
            _evidence(
                "rollback",
                rollback_target_status="unverified",
                rollback_migration_status="unverified",
            ),
            expected_status="blocked",
            expected_action="block_rollback",
            expected_failed=2,
            expected_waiting=0,
        ),
        _case_result(
            "incident_stable",
            _evidence("incident"),
            expected_status="stable",
            expected_action="no_action",
            expected_failed=0,
            expected_waiting=0,
        ),
        _case_result(
            "incident_escalation",
            _evidence(
                "incident",
                service_status="breached",
                audit_status="degraded",
                liveness_status="unavailable",
            ),
            expected_status="action_required",
            expected_action="mitigate",
            expected_failed=3,
            expected_waiting=0,
        ),
    ]
    failures = [case["name"] for case in cases if not case["passed"]]
    return {
        "schema_version": RELEASE_OPERATIONS_EVAL_SCHEMA_VERSION,
        "suite": "shopmind_release_operations",
        "total_cases": len(cases),
        "passed_cases": len(cases) - len(failures),
        "total_checks": sum(case["total_checks"] for case in cases),
        "checks_passed": sum(case["checks_passed"] for case in cases),
        "failures": failures,
        "cases": cases,
    }


def format_release_operations_summary(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        (
            "# ShopMind Release Operations Evaluation",
            "",
            f"- cases: {summary['passed_cases']}/{summary['total_cases']}",
            f"- checks: {summary['checks_passed']}/{summary['total_checks']}",
            (
                "- failures: "
                + (
                    ", ".join(summary["failures"])
                    if summary["failures"]
                    else "none"
                )
            ),
        )
    )


__all__ = [
    "RELEASE_OPERATIONS_EVAL_SCHEMA_VERSION",
    "RELEASE_OPERATIONS_SCENARIOS",
    "evaluate_release_operations",
    "format_release_operations_summary",
]
