import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from app.runtime import (
    AdmissionRequest,
    CacheKey,
    CachePutRequest,
    DeduplicationRequest,
    RateLimitRequest,
    RedisRuntimeCoordinationBackend,
    coordination_key_fingerprint,
)
from app.security import (
    IdentityAuthenticationFailure,
    SignedHeaderIdentityVerifier,
    signed_identity_signature,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REDIS_INTEGRATION") != "1",
    reason="set RUN_REDIS_INTEGRATION=1 for isolated Redis coordination tests",
)


def _fingerprint(value: str) -> str:
    return coordination_key_fingerprint("redis-integration", value)


def test_two_redis_backends_share_atomic_coordination_state() -> None:
    redis_url = os.getenv("TEST_COORDINATION_REDIS_URL")
    if not redis_url:
        pytest.fail(
            "TEST_COORDINATION_REDIS_URL is required when Redis integration is enabled."
        )
    redis_module = pytest.importorskip("redis")
    key_scope = f"shopmind-test-{uuid4().hex}"
    first_client = redis_module.Redis.from_url(redis_url, decode_responses=True)
    second_client = redis_module.Redis.from_url(redis_url, decode_responses=True)
    first = RedisRuntimeCoordinationBackend(first_client, key_scope=key_scope)
    second = RedisRuntimeCoordinationBackend(second_client, key_scope=key_scope)
    prefix = f"shopmind:coord:v1:{{{key_scope}}}:"

    try:
        admission_request = AdmissionRequest(
            resource="runtime.stream",
            subject_fingerprint=_fingerprint("global"),
            limit=1,
            lease_ttl_ms=5_000,
        )
        lease = first.try_acquire(admission_request)
        assert lease.accepted is True
        assert second.try_acquire(admission_request).reason == "capacity_exhausted"
        assert second.release_admission(lease.lease_id).released is True
        assert second.try_acquire(admission_request).accepted is True

        concurrent_request = AdmissionRequest(
            resource="runtime.concurrent",
            subject_fingerprint=_fingerprint("global"),
            limit=3,
            lease_ttl_ms=5_000,
        )
        barrier = Barrier(8)

        def acquire_concurrently(index: int) -> bool:
            barrier.wait(timeout=2)
            backend = first if index % 2 == 0 else second
            return backend.try_acquire(concurrent_request).accepted

        with ThreadPoolExecutor(max_workers=8) as executor:
            concurrent_results = list(
                executor.map(acquire_concurrently, range(8))
            )
        assert sum(concurrent_results) == 3

        expiry_request = AdmissionRequest(
            resource="runtime.expiry",
            subject_fingerprint=_fingerprint("global"),
            limit=1,
            lease_ttl_ms=200,
        )
        assert first.try_acquire(expiry_request).accepted is True
        assert second.try_acquire(expiry_request).reason == "capacity_exhausted"
        time.sleep(0.25)
        assert second.try_acquire(expiry_request).accepted is True

        rate_request = RateLimitRequest(
            bucket="chat",
            subject_fingerprint=_fingerprint("user"),
            limit=1,
            window_ms=5_000,
        )
        assert first.check_rate_limit(rate_request).accepted is True
        assert second.check_rate_limit(rate_request).reason == "rate_limited"

        dedup_request = DeduplicationRequest(
            namespace="agent-task",
            key_fingerprint=_fingerprint("task"),
            ttl_ms=5_000,
        )
        assert first.claim_duplicate(dedup_request).acquired is True
        assert second.claim_duplicate(dedup_request).reason == "duplicate"

        cache_key = CacheKey(
            namespace="answer",
            key_fingerprint=_fingerprint("cache"),
        )
        assert first.put_cache(
            CachePutRequest(
                **cache_key.model_dump(),
                value={"answer": "shared"},
                ttl_ms=5_000,
            )
        ).stored is True
        assert second.get_cache(cache_key).value == {"answer": "shared"}
        assert second.invalidate_cache(cache_key).released is True
        assert first.get_cache(cache_key).hit is False

        expiring_cache_key = CacheKey(
            namespace="answer",
            key_fingerprint=_fingerprint("expiring-cache"),
        )
        assert first.put_cache(
            CachePutRequest(
                **expiring_cache_key.model_dump(),
                value={"answer": "temporary"},
                ttl_ms=100,
            )
        ).stored is True
        time.sleep(0.15)
        assert second.get_cache(expiring_cache_key).hit is False
    finally:
        keys = list(first_client.scan_iter(match=f"{prefix}*"))
        if keys:
            first_client.delete(*keys)
        first_client.close()
        second_client.close()


def test_signed_identity_replay_is_atomic_across_redis_clients() -> None:
    redis_url = os.getenv("TEST_COORDINATION_REDIS_URL")
    if not redis_url:
        pytest.fail(
            "TEST_COORDINATION_REDIS_URL is required when Redis integration is enabled."
        )
    redis_module = pytest.importorskip("redis")
    key_scope = f"shopmind-identity-test-{uuid4().hex}"
    first_client = redis_module.Redis.from_url(redis_url, decode_responses=True)
    second_client = redis_module.Redis.from_url(redis_url, decode_responses=True)
    first_backend = RedisRuntimeCoordinationBackend(
        first_client,
        key_scope=key_scope,
    )
    second_backend = RedisRuntimeCoordinationBackend(
        second_client,
        key_scope=key_scope,
    )
    secret = "signed-redis-identity-secret-32-bytes-minimum"
    subject = "private-signed-redis-user"
    nonce = "signed-redis-nonce-0123456789"
    issued_at = 1_800_000_000
    signature = signed_identity_signature(
        secret=secret,
        subject_id=subject,
        issued_at=issued_at,
        nonce=nonce,
    )
    prefix = f"shopmind:coord:v1:{{{key_scope}}}:"

    try:
        first_result = SignedHeaderIdentityVerifier(
            signing_secret=secret,
            replay_backend=first_backend,
            max_age_seconds=60,
            clock_skew_seconds=5,
            clock=lambda: issued_at,
        ).verify(
            subject_id=subject,
            issued_at=str(issued_at),
            nonce=nonce,
            signature=signature,
        )
        second_result = SignedHeaderIdentityVerifier(
            signing_secret=secret,
            replay_backend=second_backend,
            max_age_seconds=60,
            clock_skew_seconds=5,
            clock=lambda: issued_at,
        ).verify(
            subject_id=subject,
            issued_at=str(issued_at),
            nonce=nonce,
            signature=signature,
        )
        keys = list(first_client.scan_iter(match=f"{prefix}*"))

        assert first_result.authenticated is True
        assert second_result.authenticated is False
        assert second_result.failure == IdentityAuthenticationFailure.REPLAYED
        serialized_keys = " ".join(keys)
        assert subject not in serialized_keys
        assert nonce not in serialized_keys
        assert signature not in serialized_keys
        assert secret not in serialized_keys
    finally:
        keys = list(first_client.scan_iter(match=f"{prefix}*"))
        if keys:
            first_client.delete(*keys)
        first_client.close()
        second_client.close()
