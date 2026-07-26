"""Bounded, thread-safe and PII-free service metrics and SLO evaluation."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from enum import StrEnum
from threading import Lock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.settings import (
    DEFAULT_SHOPMIND_SERVICE_SLO_MIN_RUNS,
    DEFAULT_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS,
    DEFAULT_SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET,
)

from .contracts import RunOperation, RunResult, RunStatus


SERVICE_METRICS_SCHEMA_VERSION = "shopmind.service-metrics.v1"
SERVICE_SLO_SCHEMA_VERSION = "shopmind.service-slo.v1"
SERVICE_HEALTH_SCHEMA_VERSION = "shopmind.service-health.v1"
SERVICE_LATENCY_WINDOW_CAPACITY = 1_000


class ServiceMetricsSnapshot(BaseModel):
    """One process-local snapshot with no identity or payload dimensions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.service-metrics.v1"] = (
        SERVICE_METRICS_SCHEMA_VERSION
    )
    process_scope: Literal["in_process"] = "in_process"
    status: Literal["idle", "active"]
    runs_total: int = Field(ge=0)
    chat_runs_total: int = Field(ge=0)
    confirmation_runs_total: int = Field(ge=0)
    completed_total: int = Field(ge=0)
    confirmation_required_total: int = Field(ge=0)
    cancelled_total: int = Field(ge=0)
    failed_total: int = Field(ge=0)
    replayed_total: int = Field(ge=0)
    measured_token_runs_total: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    measured_cost_runs_total: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0)
    tool_calls_total: int = Field(ge=0)
    steps_total: int = Field(ge=0)
    latency_observations_total: int = Field(ge=0)
    latency_window_capacity: int = Field(
        ge=1,
        le=SERVICE_LATENCY_WINDOW_CAPACITY,
    )
    latency_window_runs: int = Field(ge=0, le=SERVICE_LATENCY_WINDOW_CAPACITY)
    slo_window_eligible_runs: int = Field(
        ge=0,
        le=SERVICE_LATENCY_WINDOW_CAPACITY,
    )
    slo_window_successful_runs: int = Field(
        ge=0,
        le=SERVICE_LATENCY_WINDOW_CAPACITY,
    )
    latency_p50_ms: float | None = Field(default=None, ge=0)
    latency_p95_ms: float | None = Field(default=None, ge=0)
    latency_max_ms: float | None = Field(default=None, ge=0)
    last_status: Literal[
        "completed",
        "confirmation_required",
        "cancelled",
        "failed",
    ] | None = None
    last_observed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_aggregate(self) -> "ServiceMetricsSnapshot":
        if self.chat_runs_total + self.confirmation_runs_total != self.runs_total:
            raise ValueError("Service operation counts are invalid.")
        if (
            self.completed_total
            + self.confirmation_required_total
            + self.cancelled_total
            + self.failed_total
            != self.runs_total
        ):
            raise ValueError("Service status counts are invalid.")
        if self.replayed_total > self.runs_total:
            raise ValueError("Service replay count is invalid.")
        if (
            self.measured_token_runs_total > self.runs_total
            or self.measured_cost_runs_total > self.runs_total
        ):
            raise ValueError("Service usage coverage is invalid.")
        if self.latency_observations_total != self.runs_total:
            raise ValueError("Service latency count is invalid.")
        if self.latency_window_runs > self.runs_total:
            raise ValueError("Service latency window is invalid.")
        if (
            self.slo_window_eligible_runs > self.latency_window_runs
            or self.slo_window_successful_runs
            > self.slo_window_eligible_runs
        ):
            raise ValueError("Service SLO window counts are invalid.")
        percentiles = (
            self.latency_p50_ms,
            self.latency_p95_ms,
            self.latency_max_ms,
        )
        if self.latency_window_runs == 0:
            if any(value is not None for value in percentiles):
                raise ValueError("Empty service latency window is invalid.")
        elif any(value is None for value in percentiles):
            raise ValueError("Service latency percentiles are incomplete.")
        if self.status == "idle" and self.runs_total != 0:
            raise ValueError("Idle service metrics are invalid.")
        if self.status == "active" and self.runs_total == 0:
            raise ValueError("Active service metrics are invalid.")
        return self


class ServiceSloCheckStatus(StrEnum):
    MET = "met"
    BREACHED = "breached"
    INSUFFICIENT_DATA = "insufficient_data"


class ServiceSloReason(StrEnum):
    SAMPLE_SIZE_SUFFICIENT = "sample_size_sufficient"
    SAMPLE_SIZE_INSUFFICIENT = "sample_size_insufficient"
    SUCCESS_RATE_MET = "success_rate_met"
    SUCCESS_RATE_BREACHED = "success_rate_breached"
    SUCCESS_RATE_UNAVAILABLE = "success_rate_unavailable"
    P95_LATENCY_MET = "p95_latency_met"
    P95_LATENCY_BREACHED = "p95_latency_breached"
    P95_LATENCY_UNAVAILABLE = "p95_latency_unavailable"


ServiceSloCheckId = Literal[
    "telemetry.sample_size",
    "availability.success_rate",
    "latency.p95",
]


class ServiceSloCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    check_id: ServiceSloCheckId
    status: ServiceSloCheckStatus
    reason: ServiceSloReason


class ServiceSloReport(BaseModel):
    """Closed SLO evaluation over one bounded process-local snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    schema_version: Literal["shopmind.service-slo.v1"] = (
        SERVICE_SLO_SCHEMA_VERSION
    )
    process_scope: Literal["in_process"] = "in_process"
    status: Literal["insufficient_data", "met", "breached"]
    eligible_runs_total: int = Field(ge=0)
    successful_runs_total: int = Field(ge=0)
    minimum_runs: int = Field(ge=1)
    success_rate_target: float = Field(gt=0, le=1)
    observed_success_rate: float | None = Field(default=None, ge=0, le=1)
    p95_latency_target_ms: int = Field(ge=1)
    observed_p95_latency_ms: float | None = Field(default=None, ge=0)
    checks: tuple[ServiceSloCheck, ...]

    @model_validator(mode="after")
    def validate_aggregate(self) -> "ServiceSloReport":
        if len(self.checks) != 3:
            raise ValueError("Service SLO check count is invalid.")
        statuses = {check.status for check in self.checks}
        if self.status == "insufficient_data":
            if "insufficient_data" not in statuses:
                raise ValueError("Service SLO sample state is invalid.")
        elif self.status == "breached":
            if "breached" not in statuses:
                raise ValueError("Service SLO breach state is invalid.")
        elif statuses != {"met"}:
            raise ValueError("Service SLO met state is invalid.")
        return self


class ServiceHealthReport(BaseModel):
    """Additive health payload; SLO status never changes liveness/readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.service-health.v1"] = (
        SERVICE_HEALTH_SCHEMA_VERSION
    )
    status: Literal["insufficient_data", "met", "breached"]
    metrics: ServiceMetricsSnapshot
    slo: ServiceSloReport


def _nearest_rank(values: tuple[float, ...], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot calculate an empty percentile.")
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


class RuntimeServiceMonitor:
    """Accumulate bounded metrics without retaining any request-level facts."""

    def __init__(
        self,
        *,
        latency_window_capacity: int = SERVICE_LATENCY_WINDOW_CAPACITY,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= latency_window_capacity <= SERVICE_LATENCY_WINDOW_CAPACITY:
            raise ValueError("Service latency window capacity is out of bounds.")
        self._latency_window_capacity = latency_window_capacity
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = Lock()
        self._latencies: deque[float] = deque(
            maxlen=latency_window_capacity
        )
        self._statuses: deque[str] = deque(maxlen=latency_window_capacity)
        self._runs_total = 0
        self._chat_runs_total = 0
        self._confirmation_runs_total = 0
        self._completed_total = 0
        self._confirmation_required_total = 0
        self._cancelled_total = 0
        self._failed_total = 0
        self._replayed_total = 0
        self._measured_token_runs_total = 0
        self._total_tokens = 0
        self._measured_cost_runs_total = 0
        self._total_cost_usd = 0.0
        self._tool_calls_total = 0
        self._steps_total = 0
        self._last_status: str | None = None
        self._last_observed_at: datetime | None = None

    def observe(
        self,
        result: RunResult,
        *,
        operation: RunOperation,
        duration_ms: float,
        replayed: bool = False,
    ) -> None:
        self._observe(
            operation=operation,
            status=result.status,
            duration_ms=duration_ms,
            replayed=replayed,
            total_tokens=result.usage.total_tokens,
            cost_usd=result.usage.cost_usd,
            tool_call_count=result.usage.tool_call_count,
            step_count=result.usage.step_count,
        )

    def observe_failure(
        self,
        *,
        operation: RunOperation,
        duration_ms: float,
    ) -> None:
        self._observe(
            operation=operation,
            status=RunStatus.FAILED,
            duration_ms=duration_ms,
            replayed=False,
            total_tokens=None,
            cost_usd=None,
            tool_call_count=0,
            step_count=0,
        )

    def _observe(
        self,
        *,
        operation: RunOperation,
        status: RunStatus,
        duration_ms: float,
        replayed: bool,
        total_tokens: int | None,
        cost_usd: float | None,
        tool_call_count: int,
        step_count: int,
    ) -> None:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Service monitoring clock must be timezone-aware.")
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("Service duration must be finite and non-negative.")
        now = now.astimezone(timezone.utc)
        status_value = (
            status.value if isinstance(status, RunStatus) else str(status)
        )
        operation_value = (
            operation.value
            if isinstance(operation, RunOperation)
            else str(operation)
        )
        if operation_value not in {
            RunOperation.CHAT.value,
            RunOperation.CONFIRM_PENDING_ACTION.value,
        }:
            raise ValueError("Service operation is invalid.")
        if status_value not in {
            RunStatus.COMPLETED.value,
            RunStatus.CONFIRMATION_REQUIRED.value,
            RunStatus.CANCELLED.value,
            RunStatus.FAILED.value,
        }:
            raise ValueError("Service terminal status is invalid.")
        with self._lock:
            self._runs_total += 1
            if operation_value == RunOperation.CHAT.value:
                self._chat_runs_total += 1
            else:
                self._confirmation_runs_total += 1
            if status_value == RunStatus.COMPLETED.value:
                self._completed_total += 1
            elif status_value == RunStatus.CONFIRMATION_REQUIRED.value:
                self._confirmation_required_total += 1
            elif status_value == RunStatus.CANCELLED.value:
                self._cancelled_total += 1
            else:
                self._failed_total += 1
            if replayed:
                self._replayed_total += 1
            if total_tokens is not None:
                self._measured_token_runs_total += 1
                self._total_tokens += total_tokens
            if cost_usd is not None:
                self._measured_cost_runs_total += 1
                self._total_cost_usd += cost_usd
            self._tool_calls_total += tool_call_count
            self._steps_total += step_count
            self._latencies.append(round(duration_ms, 3))
            self._statuses.append(status_value)
            self._last_status = status_value
            self._last_observed_at = now

    def snapshot(self) -> ServiceMetricsSnapshot:
        with self._lock:
            latencies = tuple(self._latencies)
            statuses = tuple(self._statuses)
            successful_window = sum(
                status
                in {
                    RunStatus.COMPLETED.value,
                    RunStatus.CONFIRMATION_REQUIRED.value,
                }
                for status in statuses
            )
            eligible_window = successful_window + sum(
                status == RunStatus.FAILED.value for status in statuses
            )
            return ServiceMetricsSnapshot(
                status="active" if self._runs_total else "idle",
                runs_total=self._runs_total,
                chat_runs_total=self._chat_runs_total,
                confirmation_runs_total=self._confirmation_runs_total,
                completed_total=self._completed_total,
                confirmation_required_total=self._confirmation_required_total,
                cancelled_total=self._cancelled_total,
                failed_total=self._failed_total,
                replayed_total=self._replayed_total,
                measured_token_runs_total=self._measured_token_runs_total,
                total_tokens=self._total_tokens,
                measured_cost_runs_total=self._measured_cost_runs_total,
                total_cost_usd=round(self._total_cost_usd, 6),
                tool_calls_total=self._tool_calls_total,
                steps_total=self._steps_total,
                latency_observations_total=self._runs_total,
                latency_window_capacity=self._latency_window_capacity,
                latency_window_runs=len(latencies),
                slo_window_eligible_runs=eligible_window,
                slo_window_successful_runs=successful_window,
                latency_p50_ms=(
                    _nearest_rank(latencies, 0.5) if latencies else None
                ),
                latency_p95_ms=(
                    _nearest_rank(latencies, 0.95) if latencies else None
                ),
                latency_max_ms=(
                    round(max(latencies), 3) if latencies else None
                ),
                last_status=self._last_status,
                last_observed_at=self._last_observed_at,
            )


def evaluate_service_slo(
    metrics: ServiceMetricsSnapshot,
    *,
    minimum_runs: int = DEFAULT_SHOPMIND_SERVICE_SLO_MIN_RUNS,
    success_rate_target: float = (
        DEFAULT_SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET
    ),
    p95_latency_target_ms: int = (
        DEFAULT_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS
    ),
) -> ServiceSloReport:
    """Evaluate closed availability/latency checks over a metrics snapshot."""

    if minimum_runs < 1:
        raise ValueError("Service SLO minimum runs must be positive.")
    if not 0 < success_rate_target <= 1:
        raise ValueError("Service SLO success target is invalid.")
    if p95_latency_target_ms < 1:
        raise ValueError("Service SLO latency target must be positive.")

    successful = metrics.slo_window_successful_runs
    eligible = metrics.slo_window_eligible_runs
    sample_sufficient = (
        eligible >= minimum_runs
        and metrics.latency_window_runs >= minimum_runs
        and metrics.latency_p95_ms is not None
    )
    success_rate = (
        round(successful / eligible, 6) if eligible else None
    )
    if not sample_sufficient:
        checks = (
            ServiceSloCheck(
                check_id="telemetry.sample_size",
                status=ServiceSloCheckStatus.INSUFFICIENT_DATA,
                reason=ServiceSloReason.SAMPLE_SIZE_INSUFFICIENT,
            ),
            ServiceSloCheck(
                check_id="availability.success_rate",
                status=ServiceSloCheckStatus.INSUFFICIENT_DATA,
                reason=ServiceSloReason.SUCCESS_RATE_UNAVAILABLE,
            ),
            ServiceSloCheck(
                check_id="latency.p95",
                status=ServiceSloCheckStatus.INSUFFICIENT_DATA,
                reason=ServiceSloReason.P95_LATENCY_UNAVAILABLE,
            ),
        )
        status = "insufficient_data"
    else:
        success_met = (
            success_rate is not None
            and success_rate >= success_rate_target
        )
        latency_met = metrics.latency_p95_ms <= p95_latency_target_ms
        checks = (
            ServiceSloCheck(
                check_id="telemetry.sample_size",
                status=ServiceSloCheckStatus.MET,
                reason=ServiceSloReason.SAMPLE_SIZE_SUFFICIENT,
            ),
            ServiceSloCheck(
                check_id="availability.success_rate",
                status=(
                    ServiceSloCheckStatus.MET
                    if success_met
                    else ServiceSloCheckStatus.BREACHED
                ),
                reason=(
                    ServiceSloReason.SUCCESS_RATE_MET
                    if success_met
                    else ServiceSloReason.SUCCESS_RATE_BREACHED
                ),
            ),
            ServiceSloCheck(
                check_id="latency.p95",
                status=(
                    ServiceSloCheckStatus.MET
                    if latency_met
                    else ServiceSloCheckStatus.BREACHED
                ),
                reason=(
                    ServiceSloReason.P95_LATENCY_MET
                    if latency_met
                    else ServiceSloReason.P95_LATENCY_BREACHED
                ),
            ),
        )
        status = (
            "met"
            if success_met and latency_met
            else "breached"
        )
    return ServiceSloReport(
        status=status,
        eligible_runs_total=eligible,
        successful_runs_total=successful,
        minimum_runs=minimum_runs,
        success_rate_target=success_rate_target,
        observed_success_rate=success_rate,
        p95_latency_target_ms=p95_latency_target_ms,
        observed_p95_latency_ms=metrics.latency_p95_ms,
        checks=checks,
    )


runtime_service_monitor = RuntimeServiceMonitor()


__all__ = [
    "SERVICE_HEALTH_SCHEMA_VERSION",
    "SERVICE_LATENCY_WINDOW_CAPACITY",
    "SERVICE_METRICS_SCHEMA_VERSION",
    "SERVICE_SLO_SCHEMA_VERSION",
    "RuntimeServiceMonitor",
    "ServiceHealthReport",
    "ServiceMetricsSnapshot",
    "ServiceSloCheck",
    "ServiceSloCheckStatus",
    "ServiceSloReason",
    "ServiceSloReport",
    "evaluate_service_slo",
    "runtime_service_monitor",
]
