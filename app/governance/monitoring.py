"""Thread-safe, PII-free operational monitoring for audit emission."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Lock
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.settings import (
    DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
    MAX_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
    get_settings,
)

if TYPE_CHECKING:
    from .emitter import GovernanceAuditEmissionResult


GOVERNANCE_AUDIT_MONITOR_SCHEMA_VERSION = (
    "shopmind.governance-audit-monitor.v1"
)


class GovernanceAuditMonitorSnapshot(BaseModel):
    """One process-local metrics snapshot with no identity or payload fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.governance-audit-monitor.v1"] = (
        GOVERNANCE_AUDIT_MONITOR_SCHEMA_VERSION
    )
    process_scope: Literal["in_process"] = "in_process"
    status: Literal["idle", "healthy", "warning", "alerting"]
    alert_active: bool
    alert_failure_threshold: int = Field(ge=1)
    emission_calls_total: int = Field(ge=0)
    storage_attempts_total: int = Field(ge=0)
    requested_records_total: int = Field(ge=0)
    persisted_records_total: int = Field(ge=0)
    duplicate_records_total: int = Field(ge=0)
    skipped_calls_total: int = Field(ge=0)
    failed_calls_total: int = Field(ge=0)
    consecutive_failures: int = Field(ge=0)
    alert_transitions_total: int = Field(ge=0)
    recovery_transitions_total: int = Field(ge=0)
    last_status: Literal[
        "persisted",
        "duplicate",
        "skipped",
        "failed",
    ] | None = None
    last_reason: Literal[
        "completed",
        "already_exists",
        "disabled",
        "no_records",
        "storage_unavailable",
    ] | None = None
    last_emission_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None


class GovernanceAuditMonitorObservation(BaseModel):
    """Sanitized transition returned to the emitter for structured logging."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alert_activated: bool = False
    alert_recovered: bool = False
    consecutive_failures: int = Field(ge=0)
    alert_failure_threshold: int = Field(ge=1)


class GovernanceAuditEmissionMonitor:
    """Accumulate bounded counters and consecutive-failure alert state."""

    def __init__(
        self,
        *,
        alert_failure_threshold: int = (
            DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD
        ),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not (
            1
            <= alert_failure_threshold
            <= MAX_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD
        ):
            raise ValueError("Audit alert failure threshold is out of bounds.")
        self._alert_failure_threshold = alert_failure_threshold
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = Lock()
        self._emission_calls_total = 0
        self._storage_attempts_total = 0
        self._requested_records_total = 0
        self._persisted_records_total = 0
        self._duplicate_records_total = 0
        self._skipped_calls_total = 0
        self._failed_calls_total = 0
        self._consecutive_failures = 0
        self._alert_transitions_total = 0
        self._recovery_transitions_total = 0
        self._alert_active = False
        self._last_status: str | None = None
        self._last_reason: str | None = None
        self._last_emission_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._last_success_at: datetime | None = None

    def observe(
        self,
        result: "GovernanceAuditEmissionResult",
    ) -> GovernanceAuditMonitorObservation:
        """Record one closed emitter result without retaining its records."""

        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Audit monitoring clock must be timezone-aware.")
        now = now.astimezone(timezone.utc)
        status = str(result.status)
        reason = str(result.reason)
        alert_activated = False
        alert_recovered = False
        with self._lock:
            self._emission_calls_total += 1
            self._requested_records_total += result.requested_records
            self._persisted_records_total += result.persisted_records
            self._duplicate_records_total += result.duplicate_records
            self._last_status = status
            self._last_reason = reason
            self._last_emission_at = now

            if status == "skipped":
                self._skipped_calls_total += 1
            else:
                self._storage_attempts_total += 1

            if status == "failed":
                self._failed_calls_total += 1
                self._consecutive_failures += 1
                self._last_failure_at = now
                if (
                    not self._alert_active
                    and self._consecutive_failures
                    >= self._alert_failure_threshold
                ):
                    self._alert_active = True
                    self._alert_transitions_total += 1
                    alert_activated = True
            elif status in {"persisted", "duplicate"}:
                self._last_success_at = now
                self._consecutive_failures = 0
                if self._alert_active:
                    self._alert_active = False
                    self._recovery_transitions_total += 1
                    alert_recovered = True

            return GovernanceAuditMonitorObservation(
                alert_activated=alert_activated,
                alert_recovered=alert_recovered,
                consecutive_failures=self._consecutive_failures,
                alert_failure_threshold=self._alert_failure_threshold,
            )

    def snapshot(self) -> GovernanceAuditMonitorSnapshot:
        with self._lock:
            if self._alert_active:
                status = "alerting"
            elif self._consecutive_failures:
                status = "warning"
            elif self._emission_calls_total:
                status = "healthy"
            else:
                status = "idle"
            return GovernanceAuditMonitorSnapshot(
                status=status,
                alert_active=self._alert_active,
                alert_failure_threshold=self._alert_failure_threshold,
                emission_calls_total=self._emission_calls_total,
                storage_attempts_total=self._storage_attempts_total,
                requested_records_total=self._requested_records_total,
                persisted_records_total=self._persisted_records_total,
                duplicate_records_total=self._duplicate_records_total,
                skipped_calls_total=self._skipped_calls_total,
                failed_calls_total=self._failed_calls_total,
                consecutive_failures=self._consecutive_failures,
                alert_transitions_total=self._alert_transitions_total,
                recovery_transitions_total=self._recovery_transitions_total,
                last_status=self._last_status,
                last_reason=self._last_reason,
                last_emission_at=self._last_emission_at,
                last_failure_at=self._last_failure_at,
                last_success_at=self._last_success_at,
            )


governance_audit_monitor = GovernanceAuditEmissionMonitor(
    alert_failure_threshold=getattr(
        get_settings(),
        "shopmind_governance_audit_alert_failure_threshold",
        DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
    )
)


__all__ = [
    "GOVERNANCE_AUDIT_MONITOR_SCHEMA_VERSION",
    "GovernanceAuditEmissionMonitor",
    "GovernanceAuditMonitorObservation",
    "GovernanceAuditMonitorSnapshot",
    "governance_audit_monitor",
]
