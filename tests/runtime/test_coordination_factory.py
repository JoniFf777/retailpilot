import pytest
from pydantic import SecretStr

from app.core.settings import Settings
from app.runtime import (
    CoordinationConfigurationError,
    LocalRuntimeCoordinationBackend,
    RedisCoordinationError,
    RedisRuntimeCoordinationBackend,
    build_runtime_coordination_backend,
)


def test_factory_builds_explicit_local_fallback():
    backend = build_runtime_coordination_backend(
        Settings(shopmind_coordination_backend="local")
    )

    assert isinstance(backend, LocalRuntimeCoordinationBackend)


def test_factory_fails_closed_for_unconfigured_or_unavailable_redis(monkeypatch):
    with pytest.raises(CoordinationConfigurationError, match="connection URL"):
        build_runtime_coordination_backend(
            Settings(shopmind_coordination_backend="redis")
        )

    def fail_safely(cls, url):
        assert "private-value" in url
        raise RedisCoordinationError("Redis coordination backend is unavailable.")

    monkeypatch.setattr(
        RedisRuntimeCoordinationBackend,
        "from_url",
        classmethod(fail_safely),
    )
    with pytest.raises(CoordinationConfigurationError, match="unavailable") as raised:
        build_runtime_coordination_backend(
            Settings(
                shopmind_coordination_backend="redis",
                shopmind_coordination_redis_url=SecretStr(
                    "redis://:private-value@127.0.0.1:6379/0"
                ),
            )
        )
    assert "private-value" not in str(raised.value)


def test_factory_builds_explicit_redis_backend(monkeypatch):
    expected = RedisRuntimeCoordinationBackend(
        type(
            "Client",
            (),
            {"eval": lambda *args: None, "ping": lambda self: True},
        )()
    )

    monkeypatch.setattr(
        RedisRuntimeCoordinationBackend,
        "from_url",
        classmethod(lambda cls, url: expected),
    )
    actual = build_runtime_coordination_backend(
        Settings(
            shopmind_coordination_backend="redis",
            shopmind_coordination_redis_url=SecretStr("redis://127.0.0.1:6379/0"),
        )
    )

    assert actual is expected
