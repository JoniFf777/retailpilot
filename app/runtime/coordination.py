"""Typed coordination contracts with an explicit in-process fallback."""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
_NAME_PATTERN = r"^[a-z][a-z0-9_.:-]*$"


def coordination_key_fingerprint(namespace: str, value: str) -> str:
    """Return an opaque coordination key without retaining the raw subject."""

    normalized_namespace = namespace.strip().lower()
    if not normalized_namespace or not value:
        raise ValueError("Coordination key namespace and value are required.")
    return hashlib.sha256(
        f"{normalized_namespace}\0{value}".encode("utf-8")
    ).hexdigest()


class CoordinationBackendName(StrEnum):
    LOCAL = "local"
    REDIS = "redis"


class CoordinationReason(StrEnum):
    ACCEPTED = "accepted"
    CAPACITY_EXHAUSTED = "capacity_exhausted"
    RATE_LIMITED = "rate_limited"
    DUPLICATE = "duplicate"
    BACKEND_CAPACITY_EXHAUSTED = "backend_capacity_exhausted"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    VALUE_TOO_LARGE = "value_too_large"
    VALUE_NOT_SERIALIZABLE = "value_not_serializable"
    STORED = "stored"
    INVALIDATED = "invalidated"
    NOT_FOUND = "not_found"


class _CoordinationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)


class AdmissionRequest(_CoordinationModel):
    resource: str = Field(pattern=_NAME_PATTERN)
    subject_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    limit: int = Field(ge=1)
    lease_ttl_ms: int = Field(default=30_000, ge=1, le=300_000)


class AdmissionDecision(_CoordinationModel):
    backend: CoordinationBackendName
    accepted: bool
    reason: CoordinationReason
    lease_id: str | None = None
    retry_after_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_lease(self) -> "AdmissionDecision":
        if self.accepted != (self.lease_id is not None):
            raise ValueError("Accepted admission decisions require exactly one lease.")
        return self


class CoordinationRelease(_CoordinationModel):
    backend: CoordinationBackendName
    released: bool
    reason: CoordinationReason


class AdmissionRenewal(_CoordinationModel):
    backend: CoordinationBackendName
    renewed: bool
    reason: CoordinationReason


class RateLimitRequest(_CoordinationModel):
    bucket: str = Field(pattern=_NAME_PATTERN)
    subject_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    limit: int = Field(ge=1)
    window_ms: int = Field(ge=1, le=3_600_000)
    cost: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_cost(self) -> "RateLimitRequest":
        if self.cost > self.limit:
            raise ValueError("Rate-limit cost cannot exceed its limit.")
        return self


class RateLimitDecision(_CoordinationModel):
    backend: CoordinationBackendName
    accepted: bool
    reason: CoordinationReason
    remaining: int = Field(ge=0)
    retry_after_ms: int | None = Field(default=None, ge=0)


class DeduplicationRequest(_CoordinationModel):
    namespace: str = Field(pattern=_NAME_PATTERN)
    key_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    ttl_ms: int = Field(default=30_000, ge=1, le=3_600_000)


class DeduplicationDecision(_CoordinationModel):
    backend: CoordinationBackendName
    acquired: bool
    reason: CoordinationReason
    claim_id: str | None = None
    retry_after_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_claim(self) -> "DeduplicationDecision":
        if self.acquired != (self.claim_id is not None):
            raise ValueError("Acquired deduplication decisions require exactly one claim.")
        return self


class CacheKey(_CoordinationModel):
    namespace: str = Field(pattern=_NAME_PATTERN)
    key_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)


class CachePutRequest(CacheKey):
    value: dict[str, Any]
    ttl_ms: int = Field(default=30_000, ge=1, le=3_600_000)


class CacheLookup(_CoordinationModel):
    backend: CoordinationBackendName
    hit: bool
    reason: CoordinationReason
    value: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "CacheLookup":
        if self.hit != (self.value is not None):
            raise ValueError("Cache hits require exactly one value.")
        return self


class CacheStoreDecision(_CoordinationModel):
    backend: CoordinationBackendName
    stored: bool
    reason: CoordinationReason


@runtime_checkable
class RuntimeCoordinationBackend(Protocol):
    backend_name: CoordinationBackendName

    def try_acquire(self, request: AdmissionRequest) -> AdmissionDecision: ...

    def release_admission(self, lease_id: str) -> CoordinationRelease: ...

    def renew_admission(
        self, lease_id: str, *, lease_ttl_ms: int
    ) -> AdmissionRenewal: ...

    def check_rate_limit(self, request: RateLimitRequest) -> RateLimitDecision: ...

    def claim_duplicate(
        self, request: DeduplicationRequest
    ) -> DeduplicationDecision: ...

    def forget_duplicate(self, claim_id: str) -> CoordinationRelease: ...

    def get_cache(self, key: CacheKey) -> CacheLookup: ...

    def put_cache(self, request: CachePutRequest) -> CacheStoreDecision: ...

    def invalidate_cache(self, key: CacheKey) -> CoordinationRelease: ...


@dataclass
class _Lease:
    scope: tuple[str, str]
    expires_at: float


@dataclass
class _RateBucket:
    expires_at: float
    used: int


@dataclass
class _Claim:
    claim_id: str
    expires_at: float


@dataclass
class _CacheEntry:
    value: dict[str, Any]
    expires_at: float


class LocalRuntimeCoordinationBackend:
    """Thread-safe bounded coordination for one application process."""

    backend_name = CoordinationBackendName.LOCAL

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_active_leases: int = 1_024,
        max_rate_buckets: int = 1_024,
        max_deduplication_claims: int = 1_024,
        max_cache_entries: int = 128,
        max_cache_value_bytes: int = 65_536,
    ) -> None:
        for value in (
            max_active_leases,
            max_rate_buckets,
            max_deduplication_claims,
            max_cache_entries,
            max_cache_value_bytes,
        ):
            if value <= 0:
                raise ValueError("Local coordination bounds must be positive.")
        self._clock = clock
        self._max_active_leases = max_active_leases
        self._max_rate_buckets = max_rate_buckets
        self._max_deduplication_claims = max_deduplication_claims
        self._max_cache_entries = max_cache_entries
        self._max_cache_value_bytes = max_cache_value_bytes
        self._leases: dict[str, _Lease] = {}
        self._rate_buckets: dict[tuple[str, str], _RateBucket] = {}
        self._claims: dict[tuple[str, str], _Claim] = {}
        self._claim_scopes: dict[str, tuple[str, str]] = {}
        self._cache: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()
        self._lock = Lock()

    def try_acquire(self, request: AdmissionRequest) -> AdmissionDecision:
        now = self._clock()
        scope = (request.resource, request.subject_fingerprint)
        with self._lock:
            self._expire_leases(now)
            matching_expiries = [
                lease.expires_at
                for lease in self._leases.values()
                if lease.scope == scope
            ]
            if len(matching_expiries) >= request.limit:
                return AdmissionDecision(
                    backend=self.backend_name,
                    accepted=False,
                    reason=CoordinationReason.CAPACITY_EXHAUSTED,
                    retry_after_ms=self._remaining_ms(min(matching_expiries), now),
                )
            if len(self._leases) >= self._max_active_leases:
                return AdmissionDecision(
                    backend=self.backend_name,
                    accepted=False,
                    reason=CoordinationReason.BACKEND_CAPACITY_EXHAUSTED,
                )
            lease_id = str(uuid4())
            self._leases[lease_id] = _Lease(
                scope=scope,
                expires_at=now + request.lease_ttl_ms / 1_000,
            )
            return AdmissionDecision(
                backend=self.backend_name,
                accepted=True,
                reason=CoordinationReason.ACCEPTED,
                lease_id=lease_id,
            )

    def release_admission(self, lease_id: str) -> CoordinationRelease:
        with self._lock:
            released = self._leases.pop(lease_id, None) is not None
        return CoordinationRelease(
            backend=self.backend_name,
            released=released,
            reason=(
                CoordinationReason.INVALIDATED
                if released
                else CoordinationReason.NOT_FOUND
            ),
        )

    def renew_admission(
        self, lease_id: str, *, lease_ttl_ms: int
    ) -> AdmissionRenewal:
        if lease_ttl_ms < 1 or lease_ttl_ms > 300_000:
            raise ValueError("Admission lease TTL is outside the supported range.")
        now = self._clock()
        with self._lock:
            self._expire_leases(now)
            lease = self._leases.get(lease_id)
            if lease is None:
                return AdmissionRenewal(
                    backend=self.backend_name,
                    renewed=False,
                    reason=CoordinationReason.NOT_FOUND,
                )
            lease.expires_at = now + lease_ttl_ms / 1_000
        return AdmissionRenewal(
            backend=self.backend_name,
            renewed=True,
            reason=CoordinationReason.ACCEPTED,
        )

    def check_rate_limit(self, request: RateLimitRequest) -> RateLimitDecision:
        now = self._clock()
        scope = (request.bucket, request.subject_fingerprint)
        window_seconds = request.window_ms / 1_000
        with self._lock:
            self._expire_rate_buckets(now)
            state = self._rate_buckets.get(scope)
            if state is None:
                if len(self._rate_buckets) >= self._max_rate_buckets:
                    return RateLimitDecision(
                        backend=self.backend_name,
                        accepted=False,
                        reason=CoordinationReason.BACKEND_CAPACITY_EXHAUSTED,
                        remaining=0,
                    )
                state = _RateBucket(expires_at=now + window_seconds, used=0)
                self._rate_buckets[scope] = state
            if state.used + request.cost > request.limit:
                return RateLimitDecision(
                    backend=self.backend_name,
                    accepted=False,
                    reason=CoordinationReason.RATE_LIMITED,
                    remaining=max(0, request.limit - state.used),
                    retry_after_ms=self._remaining_ms(state.expires_at, now),
                )
            state.used += request.cost
            return RateLimitDecision(
                backend=self.backend_name,
                accepted=True,
                reason=CoordinationReason.ACCEPTED,
                remaining=request.limit - state.used,
            )

    def claim_duplicate(
        self, request: DeduplicationRequest
    ) -> DeduplicationDecision:
        now = self._clock()
        scope = (request.namespace, request.key_fingerprint)
        with self._lock:
            self._expire_claims(now)
            existing = self._claims.get(scope)
            if existing is not None:
                return DeduplicationDecision(
                    backend=self.backend_name,
                    acquired=False,
                    reason=CoordinationReason.DUPLICATE,
                    retry_after_ms=self._remaining_ms(existing.expires_at, now),
                )
            if len(self._claims) >= self._max_deduplication_claims:
                return DeduplicationDecision(
                    backend=self.backend_name,
                    acquired=False,
                    reason=CoordinationReason.BACKEND_CAPACITY_EXHAUSTED,
                )
            claim_id = str(uuid4())
            claim = _Claim(
                claim_id=claim_id,
                expires_at=now + request.ttl_ms / 1_000,
            )
            self._claims[scope] = claim
            self._claim_scopes[claim_id] = scope
            return DeduplicationDecision(
                backend=self.backend_name,
                acquired=True,
                reason=CoordinationReason.ACCEPTED,
                claim_id=claim_id,
            )

    def forget_duplicate(self, claim_id: str) -> CoordinationRelease:
        with self._lock:
            scope = self._claim_scopes.pop(claim_id, None)
            released = scope is not None and self._claims.pop(scope, None) is not None
        return CoordinationRelease(
            backend=self.backend_name,
            released=released,
            reason=(
                CoordinationReason.INVALIDATED
                if released
                else CoordinationReason.NOT_FOUND
            ),
        )

    def get_cache(self, key: CacheKey) -> CacheLookup:
        now = self._clock()
        scope = (key.namespace, key.key_fingerprint)
        with self._lock:
            self._expire_cache(now)
            entry = self._cache.get(scope)
            if entry is None:
                return CacheLookup(
                    backend=self.backend_name,
                    hit=False,
                    reason=CoordinationReason.CACHE_MISS,
                )
            self._cache.move_to_end(scope)
            return CacheLookup(
                backend=self.backend_name,
                hit=True,
                reason=CoordinationReason.CACHE_HIT,
                value=deepcopy(entry.value),
            )

    def put_cache(self, request: CachePutRequest) -> CacheStoreDecision:
        try:
            encoded = json.dumps(
                request.value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        except (TypeError, ValueError):
            return CacheStoreDecision(
                backend=self.backend_name,
                stored=False,
                reason=CoordinationReason.VALUE_NOT_SERIALIZABLE,
            )
        if len(encoded) > self._max_cache_value_bytes:
            return CacheStoreDecision(
                backend=self.backend_name,
                stored=False,
                reason=CoordinationReason.VALUE_TOO_LARGE,
            )
        now = self._clock()
        scope = (request.namespace, request.key_fingerprint)
        with self._lock:
            self._expire_cache(now)
            self._cache[scope] = _CacheEntry(
                value=deepcopy(request.value),
                expires_at=now + request.ttl_ms / 1_000,
            )
            self._cache.move_to_end(scope)
            while len(self._cache) > self._max_cache_entries:
                self._cache.popitem(last=False)
        return CacheStoreDecision(
            backend=self.backend_name,
            stored=True,
            reason=CoordinationReason.STORED,
        )

    def invalidate_cache(self, key: CacheKey) -> CoordinationRelease:
        scope = (key.namespace, key.key_fingerprint)
        with self._lock:
            released = self._cache.pop(scope, None) is not None
        return CoordinationRelease(
            backend=self.backend_name,
            released=released,
            reason=(
                CoordinationReason.INVALIDATED
                if released
                else CoordinationReason.NOT_FOUND
            ),
        )

    def _expire_leases(self, now: float) -> None:
        for lease_id in [
            lease_id
            for lease_id, lease in self._leases.items()
            if lease.expires_at <= now
        ]:
            del self._leases[lease_id]

    def _expire_rate_buckets(self, now: float) -> None:
        for scope in [
            scope
            for scope, state in self._rate_buckets.items()
            if state.expires_at <= now
        ]:
            del self._rate_buckets[scope]

    def _expire_claims(self, now: float) -> None:
        for scope, claim in list(self._claims.items()):
            if claim.expires_at <= now:
                del self._claims[scope]
                self._claim_scopes.pop(claim.claim_id, None)

    def _expire_cache(self, now: float) -> None:
        for scope, entry in list(self._cache.items()):
            if entry.expires_at <= now:
                del self._cache[scope]

    @staticmethod
    def _remaining_ms(expires_at: float, now: float) -> int:
        return max(0, int((expires_at - now) * 1_000 + 0.999))


__all__ = [
    "AdmissionDecision",
    "AdmissionRequest",
    "AdmissionRenewal",
    "CacheKey",
    "CacheLookup",
    "CachePutRequest",
    "CacheStoreDecision",
    "CoordinationBackendName",
    "CoordinationReason",
    "CoordinationRelease",
    "DeduplicationDecision",
    "DeduplicationRequest",
    "LocalRuntimeCoordinationBackend",
    "RateLimitDecision",
    "RateLimitRequest",
    "RuntimeCoordinationBackend",
    "coordination_key_fingerprint",
]
