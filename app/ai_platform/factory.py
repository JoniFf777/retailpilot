"""Server-owned factories for optional AI platform components."""

from __future__ import annotations

from app.ai_platform.resilience import OperationAdmission
from app.runtime.coordination import LocalRuntimeCoordinationBackend
from app.runtime.coordination_factory import build_runtime_coordination_backend


def build_operation_admission(settings, operation: str = "chat"):
    if not hasattr(settings, "shopmind_coordination_backend"):
        backend = LocalRuntimeCoordinationBackend()
    else:
        backend = build_runtime_coordination_backend(settings)
    admission = OperationAdmission(
        backend,
        max_concurrency=getattr(settings, "shopmind_ai_max_concurrency", 8),
        rate_limit=getattr(settings, "shopmind_ai_rate_limit", 60),
        window_ms=getattr(settings, "shopmind_ai_rate_window_ms", 60_000),
        lease_ttl_ms=getattr(settings, "shopmind_ai_lease_ttl_ms", 30_000),
    )
    return backend, admission, operation


__all__ = ["build_operation_admission"]
