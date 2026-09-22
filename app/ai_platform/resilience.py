"""Bounded admission and model-candidate resilience for ShopMind."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, Generic, TypeVar

from app.ai_platform.contracts import (
    ModelCandidate,
    ModelFailureCode,
    ModelHealthSnapshot,
    ModelAttempt,
    ModelOperation,
)
from app.runtime.coordination import (
    AdmissionRequest,
    CoordinationReason,
    RateLimitRequest,
    RuntimeCoordinationBackend,
    coordination_key_fingerprint,
)


T = TypeVar("T")


class AdmissionRejected(RuntimeError):
    """An AI operation was rejected before expensive work started."""

    def __init__(self, reason: CoordinationReason | str, retry_after_ms: int | None = None):
        super().__init__(str(reason.value if isinstance(reason, CoordinationReason) else reason))
        self.reason = reason
        self.retry_after_ms = retry_after_ms


class ModelGatewayError(RuntimeError):
    """A sanitized, closed-set model execution failure."""

    def __init__(self, code: ModelFailureCode, *, stream_started: bool = False):
        super().__init__(code.value)
        self.code = code
        self.stream_started = stream_started


class SharedAIBudget:
    """Thread-safe cumulative token/cost ceiling shared by candidate attempts."""

    def __init__(self, *, max_total_tokens: int | None = None, max_cost_usd: float | None = None) -> None:
        if max_total_tokens is not None and max_total_tokens <= 0:
            raise ValueError("AI token budget must be positive.")
        if max_cost_usd is not None and max_cost_usd <= 0:
            raise ValueError("AI cost budget must be positive.")
        self.max_total_tokens = max_total_tokens
        self.max_cost_usd = max_cost_usd
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self._lock = Lock()

    def account(self, result: ModelInvocation) -> None:
        tokens = (result.prompt_tokens or 0) + (result.completion_tokens or 0)
        cost = result.cost_usd or 0.0
        with self._lock:
            if self.max_total_tokens is not None and self.total_tokens + tokens > self.max_total_tokens:
                raise ModelGatewayError(ModelFailureCode.BUDGET_EXCEEDED)
            if self.max_cost_usd is not None and self.total_cost_usd + cost > self.max_cost_usd:
                raise ModelGatewayError(ModelFailureCode.BUDGET_EXCEEDED)
            self.total_tokens += tokens
            self.total_cost_usd += cost


@dataclass
class AdmissionLease:
    backend: RuntimeCoordinationBackend
    lease_id: str
    released: bool = False

    def release(self) -> bool:
        if self.released:
            return False
        self.released = True
        return self.backend.release_admission(self.lease_id).released

    def renew(self, lease_ttl_ms: int) -> bool:
        if self.released:
            return False
        return self.backend.renew_admission(
            self.lease_id, lease_ttl_ms=lease_ttl_ms
        ).renewed


class OperationAdmission:
    """Apply an operation lane before model or high-cost retrieval work."""

    def __init__(
        self,
        backend: RuntimeCoordinationBackend,
        *,
        max_concurrency: int = 8,
        rate_limit: int = 60,
        window_ms: int = 60_000,
        lease_ttl_ms: int = 30_000,
    ) -> None:
        if min(max_concurrency, rate_limit, window_ms, lease_ttl_ms) <= 0:
            raise ValueError("Admission settings must be positive.")
        self._backend = backend
        self._max_concurrency = max_concurrency
        self._rate_limit = rate_limit
        self._window_ms = window_ms
        self._lease_ttl_ms = lease_ttl_ms

    def acquire(self, operation: str, subject: str) -> AdmissionLease:
        subject_fingerprint = coordination_key_fingerprint(operation, subject)
        rate = self._backend.check_rate_limit(
            RateLimitRequest(
                bucket=f"ai.{operation}",
                subject_fingerprint=subject_fingerprint,
                limit=self._rate_limit,
                window_ms=self._window_ms,
            )
        )
        if not rate.accepted:
            raise AdmissionRejected(rate.reason, rate.retry_after_ms)
        decision = self._backend.try_acquire(
            AdmissionRequest(
                resource=f"ai.{operation}",
                subject_fingerprint=subject_fingerprint,
                limit=self._max_concurrency,
                lease_ttl_ms=self._lease_ttl_ms,
            )
        )
        if not decision.accepted or not decision.lease_id:
            raise AdmissionRejected(decision.reason, decision.retry_after_ms)
        return AdmissionLease(self._backend, decision.lease_id)


@dataclass(frozen=True)
class ModelInvocation(Generic[T]):
    value: T
    first_token_emitted: bool = False
    first_token_ms: int | None = None
    duration_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


class _Circuit:
    def __init__(self, *, failure_threshold: int, open_seconds: float, clock=time.monotonic):
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.clock = clock
        self.state = "closed"
        self.consecutive_failures = 0
        self.total_failures = 0
        self.total_successes = 0
        self.opened_until: float | None = None
        self.lock = Lock()

    def allow(self) -> bool:
        with self.lock:
            now = self.clock()
            if self.state == "open":
                if self.opened_until is None or now < self.opened_until:
                    return False
                self.state = "half_open"
            return True

    def success(self) -> None:
        with self.lock:
            self.total_successes += 1
            self.consecutive_failures = 0
            self.state = "closed"
            self.opened_until = None

    def failure(self) -> None:
        with self.lock:
            self.total_failures += 1
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.failure_threshold:
                self.state = "open"
                self.opened_until = self.clock() + self.open_seconds

    def snapshot(self, candidate: ModelCandidate) -> ModelHealthSnapshot:
        with self.lock:
            opened_until = (
                datetime.now(timezone.utc) + timedelta(seconds=max(0, self.opened_until - self.clock()))
                if self.opened_until is not None and self.state == "open"
                else None
            )
            return ModelHealthSnapshot(
                candidate_id=candidate.candidate_id,
                operation=candidate.operation,
                state=self.state,
                consecutive_failures=self.consecutive_failures,
                total_failures=self.total_failures,
                total_successes=self.total_successes,
                opened_until=opened_until,
            )


class ModelGateway(Generic[T]):
    """Select and execute trusted candidates with safe pre-first-token fallback."""

    def __init__(
        self,
        candidates: list[ModelCandidate],
        *,
        failure_threshold: int = 2,
        open_seconds: float = 30.0,
        clock=time.monotonic,
        attempt_observer: Callable[[ModelAttempt], None] | None = None,
        budget: SharedAIBudget | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> None:
        if not candidates:
            raise ValueError("ModelGateway requires at least one candidate.")
        if failure_threshold <= 0 or open_seconds <= 0:
            raise ValueError("Circuit settings must be positive.")
        self._candidates = tuple(sorted(candidates, key=lambda item: (str(item.operation), item.priority, item.candidate_id)))
        self._circuits = {
            candidate.candidate_id: _Circuit(
                failure_threshold=failure_threshold,
                open_seconds=open_seconds,
                clock=clock,
            )
            for candidate in self._candidates
        }
        self._attempt_observer = attempt_observer
        self._budget = budget
        self._cancellation_check = cancellation_check

    def candidates_for(self, operation: ModelOperation) -> tuple[ModelCandidate, ...]:
        return tuple(candidate for candidate in self._candidates if candidate.operation == operation)

    def execute(
        self,
        operation: ModelOperation,
        invoker: Callable[[ModelCandidate], ModelInvocation[T]],
    ) -> ModelInvocation[T]:
        candidates = self.candidates_for(operation)
        if not candidates:
            raise ModelGatewayError(ModelFailureCode.UNAVAILABLE)
        last_error: ModelGatewayError | None = None
        for candidate in candidates:
            if self._cancellation_check is not None and self._cancellation_check():
                raise ModelGatewayError(ModelFailureCode.CANCELLED)
            circuit = self._circuits[candidate.candidate_id]
            if not circuit.allow():
                last_error = ModelGatewayError(ModelFailureCode.CIRCUIT_OPEN)
                continue
            for _attempt in range(candidate.max_attempts):
                started_at = time.monotonic()
                self._notify_attempt(
                    ModelAttempt(
                        operation=operation,
                        candidate_id=candidate.candidate_id,
                        attempt=_attempt + 1,
                        status="started",
                    )
                )
                try:
                    if self._cancellation_check is not None and self._cancellation_check():
                        raise ModelGatewayError(ModelFailureCode.CANCELLED)
                    result = invoker(candidate)
                    if not isinstance(result, ModelInvocation):
                        raise ModelGatewayError(ModelFailureCode.PROTOCOL_ERROR)
                    if result.first_token_ms is not None and result.first_token_ms > candidate.first_token_timeout_ms:
                        raise ModelGatewayError(
                            ModelFailureCode.FIRST_TOKEN_TIMEOUT,
                            stream_started=result.first_token_emitted,
                        )
                    if result.duration_ms is not None and result.duration_ms > candidate.total_timeout_ms:
                        raise ModelGatewayError(
                            ModelFailureCode.TOTAL_TIMEOUT,
                            stream_started=result.first_token_emitted,
                        )
                    if result.value is None or result.value == "":
                        raise ModelGatewayError(
                            ModelFailureCode.EMPTY_RESPONSE,
                            stream_started=result.first_token_emitted,
                        )
                    if self._budget is not None:
                        self._budget.account(result)
                except ModelGatewayError as exc:
                    circuit.failure()
                    last_error = exc
                    self._notify_attempt(
                        ModelAttempt(
                            operation=operation,
                            candidate_id=candidate.candidate_id,
                            attempt=_attempt + 1,
                            status="failed",
                            failure_code=exc.code,
                            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
                        )
                    )
                    if exc.stream_started:
                        raise
                    if exc.code not in {
                        ModelFailureCode.UNAVAILABLE,
                        ModelFailureCode.CONNECTION,
                        ModelFailureCode.FIRST_TOKEN_TIMEOUT,
                        ModelFailureCode.TOTAL_TIMEOUT,
                    }:
                        break
                    continue
                except TimeoutError:
                    circuit.failure()
                    last_error = ModelGatewayError(ModelFailureCode.TOTAL_TIMEOUT)
                    self._notify_attempt(
                        ModelAttempt(
                            operation=operation,
                            candidate_id=candidate.candidate_id,
                            attempt=_attempt + 1,
                            status="failed",
                            failure_code=ModelFailureCode.TOTAL_TIMEOUT,
                            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
                        )
                    )
                    continue
                except ConnectionError:
                    circuit.failure()
                    last_error = ModelGatewayError(ModelFailureCode.CONNECTION)
                    self._notify_attempt(
                        ModelAttempt(
                            operation=operation,
                            candidate_id=candidate.candidate_id,
                            attempt=_attempt + 1,
                            status="failed",
                            failure_code=ModelFailureCode.CONNECTION,
                            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
                        )
                    )
                    continue
                except Exception:
                    circuit.failure()
                    last_error = ModelGatewayError(ModelFailureCode.UNAVAILABLE)
                    self._notify_attempt(
                        ModelAttempt(
                            operation=operation,
                            candidate_id=candidate.candidate_id,
                            attempt=_attempt + 1,
                            status="failed",
                            failure_code=ModelFailureCode.UNAVAILABLE,
                            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
                        )
                    )
                    break
                circuit.success()
                self._notify_attempt(
                    ModelAttempt(
                        operation=operation,
                        candidate_id=candidate.candidate_id,
                        attempt=_attempt + 1,
                        status="succeeded",
                        first_token_ms=result.first_token_ms,
                        duration_ms=result.duration_ms,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        cost_usd=result.cost_usd,
                    )
                )
                return result
        raise last_error or ModelGatewayError(ModelFailureCode.UNAVAILABLE)

    def health(self) -> tuple[ModelHealthSnapshot, ...]:
        return tuple(
            self._circuits[candidate.candidate_id].snapshot(candidate)
            for candidate in self._candidates
        )

    def set_attempt_observer(self, observer: Callable[[ModelAttempt], None] | None) -> None:
        self._attempt_observer = observer

    def _notify_attempt(self, attempt: ModelAttempt) -> None:
        if self._attempt_observer is not None:
            self._attempt_observer(attempt)


__all__ = [
    "AdmissionLease",
    "AdmissionRejected",
    "ModelGateway",
    "ModelGatewayError",
    "ModelInvocation",
    "SharedAIBudget",
    "OperationAdmission",
]
