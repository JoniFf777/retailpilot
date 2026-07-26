from collections import deque
from typing import Any

import pytest

from app.runtime import (
    AdmissionRequest,
    CacheKey,
    CachePutRequest,
    DeduplicationRequest,
    RateLimitRequest,
    RedisCoordinationError,
    RedisRuntimeCoordinationBackend,
    RuntimeCoordinationBackend,
    coordination_key_fingerprint,
)


class StubRedisClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, int, tuple[Any, ...]]] = []

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        self.calls.append((script, numkeys, keys_and_args))
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

    def ping(self) -> bool:
        return True


def fingerprint(value: str) -> str:
    return coordination_key_fingerprint("redis-test", value)


def test_redis_backend_maps_atomic_script_results_to_closed_contracts() -> None:
    client = StubRedisClient(
        [
            [1, 0],
            [0, 125],
            1,
            1,
            [1, 2, 0],
            [0, 0, 90],
            [1, 0],
            [0, 75],
            1,
            1,
            [1, '{"v":1}'],
            1,
            [0, ""],
        ]
    )
    backend = RedisRuntimeCoordinationBackend(client)
    assert isinstance(backend, RuntimeCoordinationBackend)

    admission = AdmissionRequest(
        resource="runtime.stream",
        subject_fingerprint=fingerprint("global"),
        limit=1,
        lease_ttl_ms=1_000,
    )
    accepted = backend.try_acquire(admission)
    rejected = backend.try_acquire(admission)
    assert accepted.backend == "redis"
    assert accepted.accepted is True
    assert rejected.model_dump() == {
        "backend": "redis",
        "accepted": False,
        "reason": "capacity_exhausted",
        "lease_id": None,
        "retry_after_ms": 125,
    }
    assert backend.renew_admission(
        accepted.lease_id, lease_ttl_ms=1_000
    ).renewed is True
    assert backend.release_admission(accepted.lease_id).released is True

    rate_request = RateLimitRequest(
        bucket="chat",
        subject_fingerprint=fingerprint("user"),
        limit=3,
        window_ms=1_000,
    )
    assert backend.check_rate_limit(rate_request).remaining == 2
    rate_limited = backend.check_rate_limit(rate_request)
    assert rate_limited.reason == "rate_limited"
    assert rate_limited.retry_after_ms == 90

    dedup_request = DeduplicationRequest(
        namespace="agent-task",
        key_fingerprint=fingerprint("task"),
        ttl_ms=1_000,
    )
    claim = backend.claim_duplicate(dedup_request)
    duplicate = backend.claim_duplicate(dedup_request)
    assert claim.acquired is True
    assert duplicate.reason == "duplicate"
    assert duplicate.retry_after_ms == 75
    assert backend.forget_duplicate(claim.claim_id).released is True

    cache_key = CacheKey(namespace="answer", key_fingerprint=fingerprint("answer"))
    assert backend.put_cache(
        CachePutRequest(**cache_key.model_dump(), value={"v": 1}, ttl_ms=1_000)
    ).stored is True
    assert backend.get_cache(cache_key).value == {"v": 1}
    assert backend.invalidate_cache(cache_key).released is True
    assert backend.get_cache(cache_key).hit is False

    markers = [call[0].splitlines()[0] for call in client.calls]
    assert markers == [
        "-- shopmind:coord:v1 admission.acquire",
        "-- shopmind:coord:v1 admission.acquire",
        "-- shopmind:coord:v1 admission.renew",
        "-- shopmind:coord:v1 admission.release",
        "-- shopmind:coord:v1 rate.check",
        "-- shopmind:coord:v1 rate.check",
        "-- shopmind:coord:v1 dedup.claim",
        "-- shopmind:coord:v1 dedup.claim",
        "-- shopmind:coord:v1 dedup.release",
        "-- shopmind:coord:v1 cache.put",
        "-- shopmind:coord:v1 cache.get",
        "-- shopmind:coord:v1 cache.invalidate",
        "-- shopmind:coord:v1 cache.get",
    ]
    for _, numkeys, values in client.calls:
        keys = values[:numkeys]
        assert keys
        assert all(
            key.startswith("shopmind:coord:v1:{shopmind-coordination}:")
            for key in keys
        )
        assert all("user" not in str(value) for value in values)


def test_redis_backend_rejects_invalid_values_before_writing() -> None:
    client = StubRedisClient([])
    backend = RedisRuntimeCoordinationBackend(
        client,
        max_cache_value_bytes=16,
    )

    unserializable = backend.put_cache(
        CachePutRequest(
            namespace="answer",
            key_fingerprint=fingerprint("invalid"),
            value={"v": object()},
        )
    )
    oversized = backend.put_cache(
        CachePutRequest(
            namespace="answer",
            key_fingerprint=fingerprint("large"),
            value={"v": "x" * 32},
        )
    )

    assert unserializable.reason == "value_not_serializable"
    assert oversized.reason == "value_too_large"
    assert client.calls == []


def test_redis_backend_sanitizes_transport_and_protocol_failures() -> None:
    secret = "redis://:do-not-leak@example.invalid/0"
    failing_client = StubRedisClient([RuntimeError(secret)])
    backend = RedisRuntimeCoordinationBackend(failing_client)
    request = AdmissionRequest(
        resource="run",
        subject_fingerprint=fingerprint("global"),
        limit=1,
    )

    with pytest.raises(RedisCoordinationError, match="operation failed") as raised:
        backend.try_acquire(request)
    assert secret not in str(raised.value)

    invalid_client = StubRedisClient([["invalid"]])
    invalid_backend = RedisRuntimeCoordinationBackend(invalid_client)
    with pytest.raises(RedisCoordinationError, match="invalid data"):
        invalid_backend.try_acquire(request)


def test_redis_backend_bounds_must_be_positive() -> None:
    with pytest.raises(ValueError, match="bounds"):
        RedisRuntimeCoordinationBackend(StubRedisClient([]), max_cache_entries=0)
