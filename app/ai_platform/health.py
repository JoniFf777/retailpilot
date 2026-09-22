"""Closed capability health aggregation for readiness and rollout decisions."""

from __future__ import annotations

from collections.abc import Iterable

from app.ai_platform.contracts import CapabilityStatus, ModelHealthSnapshot


def aggregate_ai_status(
    *,
    enabled: bool,
    model_health: Iterable[ModelHealthSnapshot] = (),
    evidence_status: str = "ready",
) -> CapabilityStatus:
    if not enabled:
        return CapabilityStatus.DISABLED
    models = tuple(model_health)
    if models and all(item.state == "open" for item in models):
        return CapabilityStatus.NOT_READY
    if evidence_status in {"unavailable", "degraded"}:
        return CapabilityStatus.DEGRADED
    return CapabilityStatus.READY


__all__ = ["aggregate_ai_status"]
