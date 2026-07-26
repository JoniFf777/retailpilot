"""Closed release-operation checks over existing versioned health contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.monitoring import GovernanceAuditMonitorSnapshot
from app.runtime.service_monitoring import (
    ServiceHealthReport,
    evaluate_service_slo,
)

from .readiness import DeploymentReadinessReport


RELEASE_OPERATION_INPUT_SCHEMA_VERSION = (
    "shopmind.release-operation-input.v1"
)
RELEASE_OPERATION_REPORT_SCHEMA_VERSION = (
    "shopmind.release-operation-check.v1"
)

ReleaseOperation = Literal["deployment", "rollback", "incident"]
ReleaseOperationCheckId = Literal[
    "health.liveness",
    "readiness.deployment",
    "coordination.backend",
    "service.slo",
    "governance.audit",
    "rollback.target",
    "rollback.migration",
]


class GovernanceAuditHealthEvidence(BaseModel):
    """Typed projection of the existing governance-audit health endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.governance-audit-health.v1"]
    status: Literal["disabled", "ok", "warning", "degraded"]
    audit_enabled: bool
    monitor: GovernanceAuditMonitorSnapshot

    @model_validator(mode="after")
    def validate_state(self) -> "GovernanceAuditHealthEvidence":
        if self.monitor.alert_active:
            expected_monitor = "alerting"
        elif self.monitor.consecutive_failures:
            expected_monitor = "warning"
        elif self.monitor.emission_calls_total:
            expected_monitor = "healthy"
        else:
            expected_monitor = "idle"
        if self.monitor.status != expected_monitor:
            raise ValueError("Governance audit monitor evidence is invalid.")
        if not self.audit_enabled:
            expected = "disabled"
        elif self.monitor.alert_active:
            expected = "degraded"
        elif self.monitor.consecutive_failures:
            expected = "warning"
        else:
            expected = "ok"
        if self.status != expected:
            raise ValueError("Governance audit health evidence is invalid.")
        return self


class ReleaseOperationInput(BaseModel):
    """Value-free release-controller input assembled from health snapshots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.release-operation-input.v1"] = (
        RELEASE_OPERATION_INPUT_SCHEMA_VERSION
    )
    operation: ReleaseOperation
    liveness_status: Literal["ok", "unavailable"]
    readiness: DeploymentReadinessReport
    service_health: ServiceHealthReport
    governance_audit_health: GovernanceAuditHealthEvidence
    rollback_target_status: Literal[
        "not_applicable",
        "verified",
        "unverified",
    ] = "not_applicable"
    rollback_migration_status: Literal[
        "not_applicable",
        "compatible",
        "incompatible",
        "unverified",
    ] = "not_applicable"

    @model_validator(mode="after")
    def validate_operation_evidence(self) -> "ReleaseOperationInput":
        expected_slo = evaluate_service_slo(
            self.service_health.metrics,
            minimum_runs=self.service_health.slo.minimum_runs,
            success_rate_target=self.service_health.slo.success_rate_target,
            p95_latency_target_ms=(
                self.service_health.slo.p95_latency_target_ms
            ),
        )
        if (
            self.service_health.status != expected_slo.status
            or self.service_health.slo != expected_slo
        ):
            raise ValueError("Service health evidence is invalid.")
        if self.operation == "rollback":
            if self.rollback_target_status == "not_applicable":
                raise ValueError("Rollback target evidence is required.")
            if self.rollback_migration_status == "not_applicable":
                raise ValueError("Rollback migration evidence is required.")
        elif (
            self.rollback_target_status != "not_applicable"
            or self.rollback_migration_status != "not_applicable"
        ):
            raise ValueError(
                "Rollback evidence is invalid for this operation."
            )
        return self


class ReleaseOperationCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WAITING = "waiting"
    NOT_APPLICABLE = "not_applicable"


class ReleaseOperationReason(StrEnum):
    LIVENESS_HEALTHY = "liveness_healthy"
    LIVENESS_UNAVAILABLE = "liveness_unavailable"
    READINESS_READY = "readiness_ready"
    READINESS_BLOCKED = "readiness_blocked"
    COORDINATION_READY = "coordination_ready"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"
    SERVICE_SLO_MET = "service_slo_met"
    SERVICE_SLO_INSUFFICIENT_DATA = "service_slo_insufficient_data"
    SERVICE_SLO_BREACHED = "service_slo_breached"
    GOVERNANCE_AUDIT_HEALTHY = "governance_audit_healthy"
    GOVERNANCE_AUDIT_WARNING = "governance_audit_warning"
    GOVERNANCE_AUDIT_DISABLED = "governance_audit_disabled"
    GOVERNANCE_AUDIT_DEGRADED = "governance_audit_degraded"
    ROLLBACK_TARGET_VERIFIED = "rollback_target_verified"
    ROLLBACK_TARGET_UNVERIFIED = "rollback_target_unverified"
    ROLLBACK_MIGRATION_COMPATIBLE = "rollback_migration_compatible"
    ROLLBACK_MIGRATION_INCOMPATIBLE = "rollback_migration_incompatible"
    ROLLBACK_MIGRATION_UNVERIFIED = "rollback_migration_unverified"
    ROLLBACK_NOT_APPLICABLE = "rollback_not_applicable"


class ReleaseOperationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    check_id: ReleaseOperationCheckId
    status: ReleaseOperationCheckStatus
    reason: ReleaseOperationReason


class ReleaseOperationReport(BaseModel):
    """Sanitized decision artifact for rollout, rollback, or incident response."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    schema_version: Literal["shopmind.release-operation-check.v1"] = (
        RELEASE_OPERATION_REPORT_SCHEMA_VERSION
    )
    operation: ReleaseOperation
    status: Literal[
        "ready",
        "hold",
        "blocked",
        "stable",
        "observe",
        "action_required",
    ]
    recommended_action: Literal[
        "continue_rollout",
        "hold_rollout",
        "stop_rollout",
        "execute_rollback",
        "hold_rollback",
        "block_rollback",
        "no_action",
        "observe",
        "mitigate",
    ]
    passed: bool
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    failed_checks: int = Field(ge=0)
    waiting_checks: int = Field(ge=0)
    not_applicable_checks: int = Field(ge=0)
    checks: tuple[ReleaseOperationCheck, ...]

    @model_validator(mode="after")
    def validate_aggregate(self) -> "ReleaseOperationReport":
        if self.total_checks != len(self.checks):
            raise ValueError("Release operation check count is invalid.")
        counts = {
            status: sum(check.status == status for check in self.checks)
            for status in (
                "passed",
                "failed",
                "waiting",
                "not_applicable",
            )
        }
        if (
            self.passed_checks != counts["passed"]
            or self.failed_checks != counts["failed"]
            or self.waiting_checks != counts["waiting"]
            or self.not_applicable_checks != counts["not_applicable"]
        ):
            raise ValueError("Release operation aggregate is invalid.")

        if self.operation == "incident":
            if self.failed_checks:
                expected = ("action_required", "mitigate", False)
            elif self.waiting_checks:
                expected = ("observe", "observe", False)
            else:
                expected = ("stable", "no_action", True)
        elif self.operation == "rollback":
            if self.failed_checks:
                expected = ("blocked", "block_rollback", False)
            elif self.waiting_checks:
                expected = ("hold", "hold_rollback", False)
            else:
                expected = ("ready", "execute_rollback", True)
        elif self.failed_checks:
            expected = ("blocked", "stop_rollout", False)
        elif self.waiting_checks:
            expected = ("hold", "hold_rollout", False)
        else:
            expected = ("ready", "continue_rollout", True)

        if (self.status, self.recommended_action, self.passed) != expected:
            raise ValueError("Release operation decision is invalid.")
        return self


def _check(
    check_id: ReleaseOperationCheckId,
    status: ReleaseOperationCheckStatus,
    reason: ReleaseOperationReason,
) -> ReleaseOperationCheck:
    return ReleaseOperationCheck(
        check_id=check_id,
        status=status,
        reason=reason,
    )


def _coordination_check(
    readiness: DeploymentReadinessReport,
) -> ReleaseOperationCheck:
    coordination = next(
        (
            check
            for check in readiness.checks
            if check.check_id == "coordination.backend"
        ),
        None,
    )
    ready = coordination is not None and coordination.status == "passed"
    return _check(
        "coordination.backend",
        (
            ReleaseOperationCheckStatus.PASSED
            if ready
            else ReleaseOperationCheckStatus.FAILED
        ),
        (
            ReleaseOperationReason.COORDINATION_READY
            if ready
            else ReleaseOperationReason.COORDINATION_UNAVAILABLE
        ),
    )


def _service_check(
    service_health: ServiceHealthReport,
) -> ReleaseOperationCheck:
    if service_health.status == "met":
        return _check(
            "service.slo",
            ReleaseOperationCheckStatus.PASSED,
            ReleaseOperationReason.SERVICE_SLO_MET,
        )
    if service_health.status == "insufficient_data":
        return _check(
            "service.slo",
            ReleaseOperationCheckStatus.WAITING,
            ReleaseOperationReason.SERVICE_SLO_INSUFFICIENT_DATA,
        )
    return _check(
        "service.slo",
        ReleaseOperationCheckStatus.FAILED,
        ReleaseOperationReason.SERVICE_SLO_BREACHED,
    )


def _governance_check(
    health: GovernanceAuditHealthEvidence,
) -> ReleaseOperationCheck:
    if health.status == "ok":
        return _check(
            "governance.audit",
            ReleaseOperationCheckStatus.PASSED,
            ReleaseOperationReason.GOVERNANCE_AUDIT_HEALTHY,
        )
    if health.status == "warning":
        return _check(
            "governance.audit",
            ReleaseOperationCheckStatus.WAITING,
            ReleaseOperationReason.GOVERNANCE_AUDIT_WARNING,
        )
    return _check(
        "governance.audit",
        ReleaseOperationCheckStatus.FAILED,
        (
            ReleaseOperationReason.GOVERNANCE_AUDIT_DISABLED
            if health.status == "disabled"
            else ReleaseOperationReason.GOVERNANCE_AUDIT_DEGRADED
        ),
    )


def _rollback_checks(
    evidence: ReleaseOperationInput,
) -> tuple[ReleaseOperationCheck, ReleaseOperationCheck]:
    if evidence.operation != "rollback":
        not_applicable = _check(
            "rollback.target",
            ReleaseOperationCheckStatus.NOT_APPLICABLE,
            ReleaseOperationReason.ROLLBACK_NOT_APPLICABLE,
        )
        migration_not_applicable = _check(
            "rollback.migration",
            ReleaseOperationCheckStatus.NOT_APPLICABLE,
            ReleaseOperationReason.ROLLBACK_NOT_APPLICABLE,
        )
        return not_applicable, migration_not_applicable

    target_verified = evidence.rollback_target_status == "verified"
    target = _check(
        "rollback.target",
        (
            ReleaseOperationCheckStatus.PASSED
            if target_verified
            else ReleaseOperationCheckStatus.FAILED
        ),
        (
            ReleaseOperationReason.ROLLBACK_TARGET_VERIFIED
            if target_verified
            else ReleaseOperationReason.ROLLBACK_TARGET_UNVERIFIED
        ),
    )
    migration_compatible = (
        evidence.rollback_migration_status == "compatible"
    )
    if migration_compatible:
        migration_reason = (
            ReleaseOperationReason.ROLLBACK_MIGRATION_COMPATIBLE
        )
    elif evidence.rollback_migration_status == "incompatible":
        migration_reason = (
            ReleaseOperationReason.ROLLBACK_MIGRATION_INCOMPATIBLE
        )
    else:
        migration_reason = (
            ReleaseOperationReason.ROLLBACK_MIGRATION_UNVERIFIED
        )
    migration = _check(
        "rollback.migration",
        (
            ReleaseOperationCheckStatus.PASSED
            if migration_compatible
            else ReleaseOperationCheckStatus.FAILED
        ),
        migration_reason,
    )
    return target, migration


def evaluate_release_operation(
    evidence: ReleaseOperationInput,
) -> ReleaseOperationReport:
    """Evaluate only closed snapshots; never probe or mutate external state."""

    checks = (
        _check(
            "health.liveness",
            (
                ReleaseOperationCheckStatus.PASSED
                if evidence.liveness_status == "ok"
                else ReleaseOperationCheckStatus.FAILED
            ),
            (
                ReleaseOperationReason.LIVENESS_HEALTHY
                if evidence.liveness_status == "ok"
                else ReleaseOperationReason.LIVENESS_UNAVAILABLE
            ),
        ),
        _check(
            "readiness.deployment",
            (
                ReleaseOperationCheckStatus.PASSED
                if (
                    evidence.readiness.profile == "production"
                    and evidence.readiness.ready
                )
                else ReleaseOperationCheckStatus.FAILED
            ),
            (
                ReleaseOperationReason.READINESS_READY
                if (
                    evidence.readiness.profile == "production"
                    and evidence.readiness.ready
                )
                else ReleaseOperationReason.READINESS_BLOCKED
            ),
        ),
        _coordination_check(evidence.readiness),
        _service_check(evidence.service_health),
        _governance_check(evidence.governance_audit_health),
        *_rollback_checks(evidence),
    )
    failed = sum(check.status == "failed" for check in checks)
    waiting = sum(check.status == "waiting" for check in checks)
    passed = sum(check.status == "passed" for check in checks)
    not_applicable = sum(
        check.status == "not_applicable" for check in checks
    )

    if evidence.operation == "incident":
        if failed:
            status, action, successful = (
                "action_required",
                "mitigate",
                False,
            )
        elif waiting:
            status, action, successful = "observe", "observe", False
        else:
            status, action, successful = "stable", "no_action", True
    elif evidence.operation == "rollback":
        if failed:
            status, action, successful = (
                "blocked",
                "block_rollback",
                False,
            )
        elif waiting:
            status, action, successful = (
                "hold",
                "hold_rollback",
                False,
            )
        else:
            status, action, successful = (
                "ready",
                "execute_rollback",
                True,
            )
    elif failed:
        status, action, successful = "blocked", "stop_rollout", False
    elif waiting:
        status, action, successful = "hold", "hold_rollout", False
    else:
        status, action, successful = "ready", "continue_rollout", True

    return ReleaseOperationReport(
        operation=evidence.operation,
        status=status,
        recommended_action=action,
        passed=successful,
        total_checks=len(checks),
        passed_checks=passed,
        failed_checks=failed,
        waiting_checks=waiting,
        not_applicable_checks=not_applicable,
        checks=checks,
    )


__all__ = [
    "RELEASE_OPERATION_INPUT_SCHEMA_VERSION",
    "RELEASE_OPERATION_REPORT_SCHEMA_VERSION",
    "GovernanceAuditHealthEvidence",
    "ReleaseOperation",
    "ReleaseOperationCheck",
    "ReleaseOperationCheckStatus",
    "ReleaseOperationInput",
    "ReleaseOperationReason",
    "ReleaseOperationReport",
    "evaluate_release_operation",
]
