"""Adapters that put existing structured planner/model providers behind Gateway."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.ai_platform.contracts import ModelAttempt, ModelOperation
from app.ai_platform.resilience import ModelGateway, ModelInvocation


def gateway_provider(
    operation: ModelOperation,
    provider: Callable[[Mapping[str, Any]], Any],
    gateway: ModelGateway,
    *,
    attempt_observer: Callable[[ModelAttempt], None] | None = None,
) -> Callable[[Mapping[str, Any]], Any]:
    """Wrap an existing provider without changing its structured output contract."""

    if attempt_observer is not None:
        # The gateway owns attempt events; the argument is accepted to make the
        # adapter explicit at call sites and keep this seam transport-neutral.
        gateway.set_attempt_observer(attempt_observer)

    def invoke(payload: Mapping[str, Any]) -> Any:
        result = gateway.execute(
            operation,
            lambda _candidate: ModelInvocation(value=provider(payload)),
        )
        return result.value

    return invoke


def harness_attempt_observer(context) -> Callable[[ModelAttempt], None]:
    """Project model attempts onto the existing ordered Harness event stream."""

    def observe(attempt: ModelAttempt) -> None:
        context.emit_event(
            f"model.attempt.{attempt.status}",
            agent_name="model_gateway",
            payload=attempt.model_dump(mode="json"),
        )

    return observe


__all__ = ["gateway_provider", "harness_attempt_observer"]
