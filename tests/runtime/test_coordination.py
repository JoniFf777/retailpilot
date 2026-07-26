from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.runtime import (
    AdmissionRequest,
    CacheKey,
    CachePutRequest,
    DeduplicationRequest,
    LocalRuntimeCoordinationBackend,
    RateLimitRequest,
    RuntimeCoordinationBackend,
    coordination_key_fingerprint,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance_ms(self, milliseconds: int) -> None:
        self.value += milliseconds / 1_000


def fingerprint(value: str) -> str:
    return coordination_key_fingerprint("test", value)


def test_local_backend_satisfies_the_typed_coordination_protocol() -> None:
    backend = LocalRuntimeCoordinationBackend()

    assert isinstance(backend, RuntimeCoordinationBackend)
    assert backend.backend_name == "local"
    assert fingerprint("user-1") != fingerprint("user-2")
    assert "user-1" not in fingerprint("user-1")


def test_admission_lease_rejects_excess_and_recovers_after_release_or_ttl() -> None:
    clock = FakeClock()
    backend = LocalRuntimeCoordinationBackend(clock=clock)
    request = AdmissionRequest(
        resource="stream",
        subject_fingerprint=fingerprint("global"),
        limit=1,
        lease_ttl_ms=1_000,
    )

    first = backend.try_acquire(request)
    rejected = backend.try_acquire(request)

    assert first.accepted is True
    assert rejected.accepted is False
    assert rejected.reason == "capacity_exhausted"
    assert rejected.retry_after_ms == 1_000
    clock.advance_ms(500)
    assert backend.renew_admission(
        first.lease_id, lease_ttl_ms=1_000
    ).renewed is True
    clock.advance_ms(500)
    assert backend.try_acquire(request).accepted is False
    assert backend.release_admission(first.lease_id).released is True
    assert backend.release_admission(first.lease_id).released is False
    second = backend.try_acquire(request)
    clock.advance_ms(1_000)
    third = backend.try_acquire(request)
    assert second.accepted is True
    assert third.accepted is True


def test_admission_is_atomic_under_concurrency() -> None:
    backend = LocalRuntimeCoordinationBackend()
    barrier = Barrier(8)
    request = AdmissionRequest(
        resource="run",
        subject_fingerprint=fingerprint("global"),
        limit=3,
    )

    def acquire() -> bool:
        barrier.wait(timeout=2)
        return backend.try_acquire(request).accepted

    with ThreadPoolExecutor(max_workers=8) as executor:
        accepted = list(executor.map(lambda _: acquire(), range(8)))

    assert sum(accepted) == 3


def test_fixed_window_rate_limit_is_scoped_and_resets_deterministically() -> None:
    clock = FakeClock()
    backend = LocalRuntimeCoordinationBackend(clock=clock)
    request = RateLimitRequest(
        bucket="chat",
        subject_fingerprint=fingerprint("user-1"),
        limit=3,
        window_ms=1_000,
    )

    decisions = [backend.check_rate_limit(request) for _ in range(4)]

    assert [decision.accepted for decision in decisions] == [True, True, True, False]
    assert decisions[-1].reason == "rate_limited"
    assert decisions[-1].retry_after_ms == 1_000
    other_user = backend.check_rate_limit(
        request.model_copy(update={"subject_fingerprint": fingerprint("user-2")})
    )
    assert other_user.accepted is True
    clock.advance_ms(1_000)
    assert backend.check_rate_limit(request).accepted is True


def test_deduplication_claim_retains_success_until_ttl_and_can_be_forgotten() -> None:
    clock = FakeClock()
    backend = LocalRuntimeCoordinationBackend(clock=clock)
    request = DeduplicationRequest(
        namespace="agent-task",
        key_fingerprint=fingerprint("task-1"),
        ttl_ms=500,
    )

    first = backend.claim_duplicate(request)
    duplicate = backend.claim_duplicate(request)

    assert first.acquired is True
    assert duplicate.acquired is False
    assert duplicate.reason == "duplicate"
    assert duplicate.retry_after_ms == 500
    assert backend.forget_duplicate(first.claim_id).released is True
    second = backend.claim_duplicate(request)
    assert second.acquired is True
    clock.advance_ms(500)
    assert backend.claim_duplicate(request).acquired is True


def test_coordination_state_bounds_fail_closed() -> None:
    backend = LocalRuntimeCoordinationBackend(
        max_active_leases=1,
        max_rate_buckets=1,
        max_deduplication_claims=1,
    )
    assert backend.try_acquire(
        AdmissionRequest(
            resource="run",
            subject_fingerprint=fingerprint("one"),
            limit=2,
        )
    ).accepted
    assert backend.try_acquire(
        AdmissionRequest(
            resource="run",
            subject_fingerprint=fingerprint("two"),
            limit=2,
        )
    ).reason == "backend_capacity_exhausted"
    assert backend.check_rate_limit(
        RateLimitRequest(
            bucket="chat",
            subject_fingerprint=fingerprint("one"),
            limit=2,
            window_ms=1_000,
        )
    ).accepted
    assert backend.check_rate_limit(
        RateLimitRequest(
            bucket="chat",
            subject_fingerprint=fingerprint("two"),
            limit=2,
            window_ms=1_000,
        )
    ).reason == "backend_capacity_exhausted"
    assert backend.claim_duplicate(
        DeduplicationRequest(
            namespace="run",
            key_fingerprint=fingerprint("one"),
        )
    ).acquired
    assert backend.claim_duplicate(
        DeduplicationRequest(
            namespace="run",
            key_fingerprint=fingerprint("two"),
        )
    ).reason == "backend_capacity_exhausted"


def test_bounded_cache_uses_ttl_lru_copying_and_value_size_limits() -> None:
    clock = FakeClock()
    backend = LocalRuntimeCoordinationBackend(
        clock=clock,
        max_cache_entries=2,
        max_cache_value_bytes=32,
    )
    first_key = CacheKey(namespace="answer", key_fingerprint=fingerprint("one"))
    second_key = CacheKey(namespace="answer", key_fingerprint=fingerprint("two"))
    third_key = CacheKey(namespace="answer", key_fingerprint=fingerprint("three"))

    assert backend.put_cache(
        CachePutRequest(**first_key.model_dump(), value={"v": 1}, ttl_ms=1_000)
    ).stored
    first_value = backend.get_cache(first_key)
    first_value.value["v"] = 99
    assert backend.get_cache(first_key).value == {"v": 1}
    assert backend.put_cache(
        CachePutRequest(**second_key.model_dump(), value={"v": 2}, ttl_ms=1_000)
    ).stored
    assert backend.put_cache(
        CachePutRequest(**third_key.model_dump(), value={"v": 3}, ttl_ms=1_000)
    ).stored
    assert backend.get_cache(first_key).hit is False
    assert backend.get_cache(second_key).hit is True
    clock.advance_ms(1_000)
    assert backend.get_cache(second_key).hit is False
    assert backend.put_cache(
        CachePutRequest(
            namespace="answer",
            key_fingerprint=fingerprint("large"),
            value={"value": "x" * 40},
        )
    ).reason == "value_too_large"
    assert backend.put_cache(
        CachePutRequest(
            namespace="answer",
            key_fingerprint=fingerprint("invalid"),
            value={"value": object()},
        )
    ).reason == "value_not_serializable"


def test_cache_invalidation_is_idempotent() -> None:
    backend = LocalRuntimeCoordinationBackend()
    key = CacheKey(namespace="answer", key_fingerprint=fingerprint("invalidate"))
    backend.put_cache(CachePutRequest(**key.model_dump(), value={"ok": True}))

    assert backend.invalidate_cache(key).released is True
    assert backend.invalidate_cache(key).released is False
