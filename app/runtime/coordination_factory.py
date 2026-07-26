"""Server-owned runtime coordination backend construction."""

from __future__ import annotations

from app.core.settings import Settings, get_settings

from .coordination import (
    LocalRuntimeCoordinationBackend,
    RuntimeCoordinationBackend,
)
from .redis_coordination import (
    RedisCoordinationError,
    RedisRuntimeCoordinationBackend,
)


class CoordinationConfigurationError(RuntimeError):
    """Raised when an explicitly selected coordination backend is unavailable."""


def build_runtime_coordination_backend(
    settings: Settings | None = None,
) -> RuntimeCoordinationBackend:
    resolved = settings or get_settings()
    if resolved.shopmind_coordination_backend == "local":
        return LocalRuntimeCoordinationBackend()
    if resolved.shopmind_coordination_redis_url is None:
        raise CoordinationConfigurationError(
            "Redis coordination requires a server-owned connection URL."
        )
    try:
        return RedisRuntimeCoordinationBackend.from_url(
            resolved.shopmind_coordination_redis_url.get_secret_value()
        )
    except RedisCoordinationError as exc:
        raise CoordinationConfigurationError(str(exc)) from exc


__all__ = [
    "CoordinationConfigurationError",
    "build_runtime_coordination_backend",
]
