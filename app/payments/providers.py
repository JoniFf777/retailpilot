"""Provider boundary for Phase 5A Mock Payments."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Literal, Mapping, Protocol


ProviderOutcomeStatus = Literal["succeeded", "declined", "unknown", "not_found"]
MockScenario = Literal["success", "declined", "unknown", "timeout", "not_found"]


@dataclass(frozen=True)
class ProviderChargeRequest:
    provider_idempotency_key: str
    amount: str
    currency: str
    payment_method_ref: str


@dataclass(frozen=True)
class ProviderOutcome:
    status: ProviderOutcomeStatus
    provider_payment_id: str | None
    failure_code: str | None
    result_at: datetime


class PaymentProvider(Protocol):
    def charge(self, request: ProviderChargeRequest) -> ProviderOutcome:
        """Start or resume one idempotent provider operation."""

    def get_result(self, provider_idempotency_key: str) -> ProviderOutcome:
        """Read the result of an existing provider operation."""


def _normalize_outcome(value: MockScenario) -> ProviderOutcomeStatus:
    if value == "success":
        return "succeeded"
    if value == "declined":
        return "declined"
    if value in {"unknown", "timeout"}:
        return "unknown"
    return "not_found"


@dataclass
class _MockOperation:
    provider_payment_id: str
    outcomes: deque[ProviderOutcomeStatus]
    current: ProviderOutcomeStatus
    result_at: datetime


class MockPaymentProvider:
    """Deterministic in-process provider used only through dependency injection.

    ``scenarios_by_method`` is a server/test-owned script.  It is never read
    from the HTTP request as a scenario or force flag.  One provider key maps
    to one operation and one provider payment id for the life of this process.
    """

    def __init__(
        self,
        *,
        scenarios_by_method: Mapping[str, tuple[MockScenario, ...]] | None = None,
        default_scenario: MockScenario = "success",
    ) -> None:
        self._scenarios_by_method = dict(scenarios_by_method or {})
        self._default_scenario = default_scenario
        self._operations: dict[str, _MockOperation] = {}
        self._lock = RLock()
        self.charge_calls = 0
        self.get_result_calls = 0

    def charge(self, request: ProviderChargeRequest) -> ProviderOutcome:
        with self._lock:
            self.charge_calls += 1
            operation = self._operations.get(request.provider_idempotency_key)
            if operation is None:
                script = self._scenarios_by_method.get(
                    request.payment_method_ref,
                    (self._default_scenario,),
                )
                if not script:
                    script = (self._default_scenario,)
                statuses = deque(_normalize_outcome(value) for value in script)
                current = statuses.popleft()
                operation = _MockOperation(
                    provider_payment_id=f"mock-pay-{request.provider_idempotency_key}",
                    outcomes=statuses,
                    current=current,
                    result_at=datetime.now(timezone.utc),
                )
                self._operations[request.provider_idempotency_key] = operation
            return self._outcome(operation)

    def get_result(self, provider_idempotency_key: str) -> ProviderOutcome:
        with self._lock:
            self.get_result_calls += 1
            operation = self._operations.get(provider_idempotency_key)
            if operation is None:
                return ProviderOutcome(
                    status="not_found",
                    provider_payment_id=None,
                    failure_code="provider_not_found",
                    result_at=datetime.now(timezone.utc),
                )
            if operation.current == "unknown" and operation.outcomes:
                operation.current = operation.outcomes.popleft()
                operation.result_at = datetime.now(timezone.utc)
            return self._outcome(operation)

    @staticmethod
    def _outcome(operation: _MockOperation) -> ProviderOutcome:
        failure_code = {
            "declined": "payment_declined",
            "unknown": "provider_timeout",
        }.get(operation.current)
        return ProviderOutcome(
            status=operation.current,
            provider_payment_id=operation.provider_payment_id,
            failure_code=failure_code,
            result_at=operation.result_at,
        )


__all__ = [
    "MockPaymentProvider",
    "MockScenario",
    "PaymentProvider",
    "ProviderChargeRequest",
    "ProviderOutcome",
    "ProviderOutcomeStatus",
]
