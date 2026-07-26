"""Deterministic local/Redis coordination contract trajectories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.runtime import (
    AdmissionRequest,
    CacheKey,
    CachePutRequest,
    DeduplicationRequest,
    LocalRuntimeCoordinationBackend,
    RateLimitRequest,
    RedisCoordinationError,
    RedisRuntimeCoordinationBackend,
    coordination_key_fingerprint,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance_ms(self, milliseconds: int) -> None:
        self.value += milliseconds / 1_000


class _ReferenceRedisClient:
    """Deterministic script-wire reference backed by the local semantics."""

    def __init__(self, clock: _Clock) -> None:
        self.backend = LocalRuntimeCoordinationBackend(
            clock=clock,
            max_cache_entries=2,
            max_cache_value_bytes=32,
        )
        self.lease_ids: dict[str, str] = {}
        self.claim_ids: dict[str, str] = {}

    def ping(self) -> bool:
        return True

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        marker = script.splitlines()[0]
        args = keys_and_args[numkeys:]
        if marker.endswith("admission.acquire"):
            namespace, fingerprint = self._scope(args[0])
            decision = self.backend.try_acquire(
                AdmissionRequest(
                    resource=namespace,
                    subject_fingerprint=fingerprint,
                    limit=int(args[1]),
                    lease_ttl_ms=int(args[4]),
                )
            )
            if decision.accepted:
                self.lease_ids[str(args[3])] = decision.lease_id
                return [1, 0]
            if decision.reason == "capacity_exhausted":
                return [0, decision.retry_after_ms]
            return [-1, 0]
        if marker.endswith("admission.renew"):
            local_id = self.lease_ids.get(str(args[0]))
            if local_id is None:
                return 0
            return int(
                self.backend.renew_admission(
                    local_id,
                    lease_ttl_ms=int(args[1]),
                ).renewed
            )
        if marker.endswith("admission.release"):
            local_id = self.lease_ids.pop(str(args[0]), None)
            return int(
                local_id is not None
                and self.backend.release_admission(local_id).released
            )
        if marker.endswith("rate.check"):
            namespace, fingerprint = self._scope(args[0])
            decision = self.backend.check_rate_limit(
                RateLimitRequest(
                    bucket=namespace,
                    subject_fingerprint=fingerprint,
                    limit=int(args[1]),
                    window_ms=int(args[2]),
                    cost=int(args[3]),
                )
            )
            if decision.accepted:
                return [1, decision.remaining, 0]
            if decision.reason == "rate_limited":
                return [0, decision.remaining, decision.retry_after_ms]
            return [-1, 0, 0]
        if marker.endswith("dedup.claim"):
            namespace, fingerprint = self._scope(args[0])
            decision = self.backend.claim_duplicate(
                DeduplicationRequest(
                    namespace=namespace,
                    key_fingerprint=fingerprint,
                    ttl_ms=int(args[3]),
                )
            )
            if decision.acquired:
                self.claim_ids[str(args[2])] = decision.claim_id
                return [1, 0]
            if decision.reason == "duplicate":
                return [0, decision.retry_after_ms]
            return [-1, 0]
        if marker.endswith("dedup.release"):
            local_id = self.claim_ids.pop(str(args[0]), None)
            return int(
                local_id is not None
                and self.backend.forget_duplicate(local_id).released
            )
        if marker.endswith("cache.put"):
            namespace, fingerprint = self._scope(args[0])
            self.backend.put_cache(
                CachePutRequest(
                    namespace=namespace,
                    key_fingerprint=fingerprint,
                    value=json.loads(str(args[1])),
                    ttl_ms=int(args[2]),
                )
            )
            return 1
        if marker.endswith("cache.get"):
            namespace, fingerprint = self._scope(args[0])
            lookup = self.backend.get_cache(
                CacheKey(namespace=namespace, key_fingerprint=fingerprint)
            )
            return (
                [1, json.dumps(lookup.value, sort_keys=True, separators=(",", ":"))]
                if lookup.hit
                else [0, ""]
            )
        if marker.endswith("cache.invalidate"):
            namespace, fingerprint = self._scope(args[0])
            return int(
                self.backend.invalidate_cache(
                    CacheKey(namespace=namespace, key_fingerprint=fingerprint)
                ).released
            )
        raise AssertionError("Unknown versioned coordination script.")

    @staticmethod
    def _scope(value: Any) -> tuple[str, str]:
        namespace, fingerprint = str(value).split(":", 1)
        return namespace, fingerprint


class _FailingRedisClient:
    def ping(self) -> bool:
        return True

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        raise RuntimeError("redis://:private-secret@example.invalid/0")


@dataclass
class _BackendPair:
    local: LocalRuntimeCoordinationBackend
    redis: RedisRuntimeCoordinationBackend
    local_clock: _Clock
    redis_clock: _Clock

    def advance_ms(self, milliseconds: int) -> None:
        self.local_clock.advance_ms(milliseconds)
        self.redis_clock.advance_ms(milliseconds)


def _pair() -> _BackendPair:
    local_clock = _Clock()
    redis_clock = _Clock()
    return _BackendPair(
        local=LocalRuntimeCoordinationBackend(
            clock=local_clock,
            max_cache_entries=2,
            max_cache_value_bytes=32,
        ),
        redis=RedisRuntimeCoordinationBackend(
            _ReferenceRedisClient(redis_clock),
            max_cache_entries=2,
            max_cache_value_bytes=32,
        ),
        local_clock=local_clock,
        redis_clock=redis_clock,
    )


def _fingerprint(value: str) -> str:
    return coordination_key_fingerprint("coordination-eval", value)


def _normalize(value: Any) -> dict[str, Any]:
    payload = value.model_dump(mode="json")
    payload.pop("backend", None)
    if payload.get("lease_id") is not None:
        payload["lease_id"] = "present"
    if payload.get("claim_id") is not None:
        payload["claim_id"] = "present"
    return payload


def _equivalent(local: Any, redis: Any) -> bool:
    return _normalize(local) == _normalize(redis)


def evaluate_coordination_equivalence() -> dict[str, Any]:
    """Replay closed coordination cases without a live Redis dependency."""

    cases: list[dict[str, Any]] = []

    pair = _pair()
    admission = AdmissionRequest(
        resource="runtime.stream",
        subject_fingerprint=_fingerprint("global"),
        limit=1,
        lease_ttl_ms=1_000,
    )
    local_lease = pair.local.try_acquire(admission)
    redis_lease = pair.redis.try_acquire(admission)
    admission_checks = [
        _equivalent(local_lease, redis_lease),
        _equivalent(pair.local.try_acquire(admission), pair.redis.try_acquire(admission)),
        _equivalent(
            pair.local.renew_admission(local_lease.lease_id, lease_ttl_ms=1_000),
            pair.redis.renew_admission(redis_lease.lease_id, lease_ttl_ms=1_000),
        ),
        _equivalent(
            pair.local.release_admission(local_lease.lease_id),
            pair.redis.release_admission(redis_lease.lease_id),
        ),
    ]
    cases.append({"case_id": "admission_lease", "checks": admission_checks})

    pair = _pair()
    rate = RateLimitRequest(
        bucket="chat",
        subject_fingerprint=_fingerprint("user"),
        limit=2,
        window_ms=1_000,
    )
    rate_checks = [
        _equivalent(pair.local.check_rate_limit(rate), pair.redis.check_rate_limit(rate))
        for _ in range(3)
    ]
    pair.advance_ms(1_000)
    rate_checks.append(
        _equivalent(pair.local.check_rate_limit(rate), pair.redis.check_rate_limit(rate))
    )
    cases.append({"case_id": "fixed_window_rate_limit", "checks": rate_checks})

    pair = _pair()
    dedup = DeduplicationRequest(
        namespace="agent-task",
        key_fingerprint=_fingerprint("task"),
        ttl_ms=500,
    )
    local_claim = pair.local.claim_duplicate(dedup)
    redis_claim = pair.redis.claim_duplicate(dedup)
    dedup_checks = [
        _equivalent(local_claim, redis_claim),
        _equivalent(
            pair.local.claim_duplicate(dedup),
            pair.redis.claim_duplicate(dedup),
        ),
        _equivalent(
            pair.local.forget_duplicate(local_claim.claim_id),
            pair.redis.forget_duplicate(redis_claim.claim_id),
        ),
        _equivalent(
            pair.local.claim_duplicate(dedup),
            pair.redis.claim_duplicate(dedup),
        ),
    ]
    cases.append({"case_id": "duplicate_claim", "checks": dedup_checks})

    pair = _pair()
    cache_key = CacheKey(
        namespace="answer",
        key_fingerprint=_fingerprint("cache"),
    )
    cache_put = CachePutRequest(
        **cache_key.model_dump(),
        value={"answer": "stable"},
        ttl_ms=1_000,
    )
    cache_checks = [
        _equivalent(pair.local.put_cache(cache_put), pair.redis.put_cache(cache_put)),
        _equivalent(pair.local.get_cache(cache_key), pair.redis.get_cache(cache_key)),
        _equivalent(
            pair.local.invalidate_cache(cache_key),
            pair.redis.invalidate_cache(cache_key),
        ),
        _equivalent(pair.local.get_cache(cache_key), pair.redis.get_cache(cache_key)),
    ]
    cases.append({"case_id": "bounded_cache", "checks": cache_checks})

    failing = RedisRuntimeCoordinationBackend(_FailingRedisClient())
    try:
        failing.try_acquire(admission)
        sanitized = False
        safe_code = False
    except RedisCoordinationError as exc:
        sanitized = "private-secret" not in str(exc)
        safe_code = str(exc) == "Redis coordination operation failed."
    failure_checks = [sanitized, safe_code]
    cases.append({"case_id": "transport_failure", "checks": failure_checks})

    case_results = []
    failures = []
    total_checks = 0
    passed_checks = 0
    for case in cases:
        checks = case["checks"]
        total_checks += len(checks)
        passed_checks += sum(checks)
        passed = all(checks)
        case_results.append(
            {
                "case_id": case["case_id"],
                "passed": passed,
                "total_checks": len(checks),
                "passed_checks": sum(checks),
            }
        )
        if not passed:
            failures.append(
                {
                    "case_id": case["case_id"],
                    "code": "coordination.contract_mismatch",
                }
            )
    passed_cases = sum(case["passed"] for case in case_results)
    return {
        "schema_version": "shopmind.coordination-equivalence-eval.v1",
        "evaluation": "coordination_backend_equivalence",
        "total_cases": len(case_results),
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(case_results),
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "check_pass_rate": passed_checks / total_checks,
        "failures": failures,
        "cases": case_results,
    }


__all__ = ["evaluate_coordination_equivalence"]
