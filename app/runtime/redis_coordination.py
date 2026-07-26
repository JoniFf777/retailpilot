"""Atomic Redis implementation of the runtime coordination contract."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .coordination import (
    AdmissionDecision,
    AdmissionRenewal,
    AdmissionRequest,
    CacheKey,
    CacheLookup,
    CachePutRequest,
    CacheStoreDecision,
    CoordinationBackendName,
    CoordinationReason,
    CoordinationRelease,
    DeduplicationDecision,
    DeduplicationRequest,
    RateLimitDecision,
    RateLimitRequest,
)


_KEY_SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class RedisScriptClient(Protocol):
    """Minimal synchronous Redis surface required by the backend."""

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...

    def ping(self) -> Any: ...


class RedisCoordinationError(RuntimeError):
    """Sanitized Redis coordination failure."""


_ADMISSION_ACQUIRE_SCRIPT = """-- shopmind:coord:v1 admission.acquire
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now)
for _, lease_id in ipairs(expired) do
  redis.call('HDEL', KEYS[1], lease_id)
  redis.call('ZREM', KEYS[2], lease_id)
end
local scope_count = 0
local retry_at = nil
local leases = redis.call('HGETALL', KEYS[1])
for index = 1, #leases, 2 do
  if leases[index + 1] == ARGV[1] then
    scope_count = scope_count + 1
    local expires_at = tonumber(redis.call('ZSCORE', KEYS[2], leases[index]))
    if expires_at and (not retry_at or expires_at < retry_at) then
      retry_at = expires_at
    end
  end
end
if scope_count >= tonumber(ARGV[2]) then
  return {0, math.max(0, retry_at - now)}
end
if redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[3]) then
  return {-1, 0}
end
redis.call('HSET', KEYS[1], ARGV[4], ARGV[1])
redis.call('ZADD', KEYS[2], now + tonumber(ARGV[5]), ARGV[4])
return {1, 0}
"""

_ADMISSION_RELEASE_SCRIPT = """-- shopmind:coord:v1 admission.release
local removed = redis.call('HDEL', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
return removed
"""

_ADMISSION_RENEW_SCRIPT = """-- shopmind:coord:v1 admission.renew
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 0 then
  return 0
end
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local expires_at = tonumber(redis.call('ZSCORE', KEYS[2], ARGV[1]))
if not expires_at or expires_at <= now then
  redis.call('HDEL', KEYS[1], ARGV[1])
  redis.call('ZREM', KEYS[2], ARGV[1])
  return 0
end
redis.call('ZADD', KEYS[2], now + tonumber(ARGV[2]), ARGV[1])
return 1
"""

_RATE_LIMIT_SCRIPT = """-- shopmind:coord:v1 rate.check
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local entries = redis.call('HGETALL', KEYS[1])
for index = 1, #entries, 2 do
  local separator = string.find(entries[index + 1], '|', 1, true)
  local expires_at = tonumber(string.sub(entries[index + 1], separator + 1))
  if expires_at <= now then redis.call('HDEL', KEYS[1], entries[index]) end
end
local state = redis.call('HGET', KEYS[1], ARGV[1])
local used = 0
local expires_at = now + tonumber(ARGV[3])
if state then
  local separator = string.find(state, '|', 1, true)
  used = tonumber(string.sub(state, 1, separator - 1))
  expires_at = tonumber(string.sub(state, separator + 1))
elseif redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[5]) then
  return {-1, 0, 0}
end
local limit = tonumber(ARGV[2])
local cost = tonumber(ARGV[4])
if used + cost > limit then
  return {0, math.max(0, limit - used), math.max(0, expires_at - now)}
end
used = used + cost
redis.call('HSET', KEYS[1], ARGV[1], tostring(used) .. '|' .. tostring(expires_at))
return {1, limit - used, 0}
"""

_DEDUP_CLAIM_SCRIPT = """-- shopmind:coord:v1 dedup.claim
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local expired = redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', now)
for _, claim_id in ipairs(expired) do
  local scope = redis.call('HGET', KEYS[2], claim_id)
  if scope then redis.call('HDEL', KEYS[1], scope) end
  redis.call('HDEL', KEYS[2], claim_id)
  redis.call('ZREM', KEYS[3], claim_id)
end
local existing = redis.call('HGET', KEYS[1], ARGV[1])
if existing then
  local expires_at = tonumber(redis.call('ZSCORE', KEYS[3], existing))
  return {0, math.max(0, expires_at - now)}
end
if redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[2]) then return {-1, 0} end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[3])
redis.call('HSET', KEYS[2], ARGV[3], ARGV[1])
redis.call('ZADD', KEYS[3], now + tonumber(ARGV[4]), ARGV[3])
return {1, 0}
"""

_DEDUP_RELEASE_SCRIPT = """-- shopmind:coord:v1 dedup.release
local scope = redis.call('HGET', KEYS[2], ARGV[1])
if not scope then return 0 end
redis.call('HDEL', KEYS[1], scope)
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('ZREM', KEYS[3], ARGV[1])
return 1
"""

_CACHE_GET_SCRIPT = """-- shopmind:coord:v1 cache.get
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local expires_at = tonumber(redis.call('ZSCORE', KEYS[2], ARGV[1]))
if not expires_at or expires_at <= now then
  redis.call('HDEL', KEYS[1], ARGV[1])
  redis.call('ZREM', KEYS[2], ARGV[1])
  redis.call('ZREM', KEYS[3], ARGV[1])
  return {0, ''}
end
local value = redis.call('HGET', KEYS[1], ARGV[1])
if not value then return {0, ''} end
local recency = redis.call('INCR', KEYS[4])
redis.call('ZADD', KEYS[3], recency, ARGV[1])
return {1, value}
"""

_CACHE_PUT_SCRIPT = """-- shopmind:coord:v1 cache.put
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now)
for _, scope in ipairs(expired) do
  redis.call('HDEL', KEYS[1], scope)
  redis.call('ZREM', KEYS[2], scope)
  redis.call('ZREM', KEYS[3], scope)
end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('ZADD', KEYS[2], now + tonumber(ARGV[3]), ARGV[1])
local recency = redis.call('INCR', KEYS[4])
redis.call('ZADD', KEYS[3], recency, ARGV[1])
local overflow = redis.call('HLEN', KEYS[1]) - tonumber(ARGV[4])
if overflow > 0 then
  local victims = redis.call('ZRANGE', KEYS[3], 0, overflow - 1)
  for _, scope in ipairs(victims) do
    redis.call('HDEL', KEYS[1], scope)
    redis.call('ZREM', KEYS[2], scope)
    redis.call('ZREM', KEYS[3], scope)
  end
end
return 1
"""

_CACHE_INVALIDATE_SCRIPT = """-- shopmind:coord:v1 cache.invalidate
local removed = redis.call('HDEL', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('ZREM', KEYS[3], ARGV[1])
return removed
"""


class RedisRuntimeCoordinationBackend:
    """Cross-process coordination using versioned, atomic Redis scripts."""

    backend_name = CoordinationBackendName.REDIS

    def __init__(
        self,
        client: RedisScriptClient,
        *,
        max_active_leases: int = 1_024,
        max_rate_buckets: int = 1_024,
        max_deduplication_claims: int = 1_024,
        max_cache_entries: int = 128,
        max_cache_value_bytes: int = 65_536,
        key_scope: str = "shopmind-coordination",
    ) -> None:
        for value in (
            max_active_leases,
            max_rate_buckets,
            max_deduplication_claims,
            max_cache_entries,
            max_cache_value_bytes,
        ):
            if value <= 0:
                raise ValueError("Redis coordination bounds must be positive.")
        self._client = client
        self._max_active_leases = max_active_leases
        self._max_rate_buckets = max_rate_buckets
        self._max_deduplication_claims = max_deduplication_claims
        self._max_cache_entries = max_cache_entries
        self._max_cache_value_bytes = max_cache_value_bytes
        if not _KEY_SCOPE_PATTERN.fullmatch(key_scope):
            raise ValueError("Redis coordination key scope is invalid.")
        self._key_prefix = f"shopmind:coord:v1:{{{key_scope}}}"

    @classmethod
    def from_url(cls, url: str) -> "RedisRuntimeCoordinationBackend":
        try:
            from redis import Redis
        except ImportError as exc:
            raise RedisCoordinationError(
                "Redis coordination client is not installed."
            ) from exc
        try:
            client = Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
        except Exception as exc:
            raise RedisCoordinationError(
                "Redis coordination backend is unavailable."
            ) from exc
        return cls(client)

    def close(self) -> None:
        """Release this backend's Redis client after a bounded live probe."""

        self._client.close()

    def try_acquire(self, request: AdmissionRequest) -> AdmissionDecision:
        from uuid import uuid4

        lease_id = str(uuid4())
        result = self._eval(
            _ADMISSION_ACQUIRE_SCRIPT,
            (self._key("leases"), self._key("lease-expiry")),
            self._scope(request.resource, request.subject_fingerprint),
            request.limit,
            self._max_active_leases,
            lease_id,
            request.lease_ttl_ms,
        )
        code, retry_after_ms = self._integers(result, 2)
        if code == 1:
            return AdmissionDecision(
                backend=self.backend_name,
                accepted=True,
                reason=CoordinationReason.ACCEPTED,
                lease_id=lease_id,
            )
        return AdmissionDecision(
            backend=self.backend_name,
            accepted=False,
            reason=(
                CoordinationReason.CAPACITY_EXHAUSTED
                if code == 0
                else CoordinationReason.BACKEND_CAPACITY_EXHAUSTED
            ),
            retry_after_ms=retry_after_ms if code == 0 else None,
        )

    def release_admission(self, lease_id: str) -> CoordinationRelease:
        released = bool(
            self._integer(
                self._eval(
                    _ADMISSION_RELEASE_SCRIPT,
                    (self._key("leases"), self._key("lease-expiry")),
                    lease_id,
                )
            )
        )
        return self._release(released)

    def renew_admission(
        self, lease_id: str, *, lease_ttl_ms: int
    ) -> AdmissionRenewal:
        if lease_ttl_ms < 1 or lease_ttl_ms > 300_000:
            raise ValueError("Admission lease TTL is outside the supported range.")
        renewed = bool(
            self._integer(
                self._eval(
                    _ADMISSION_RENEW_SCRIPT,
                    (self._key("leases"), self._key("lease-expiry")),
                    lease_id,
                    lease_ttl_ms,
                )
            )
        )
        return AdmissionRenewal(
            backend=self.backend_name,
            renewed=renewed,
            reason=(
                CoordinationReason.ACCEPTED
                if renewed
                else CoordinationReason.NOT_FOUND
            ),
        )

    def check_rate_limit(self, request: RateLimitRequest) -> RateLimitDecision:
        result = self._eval(
            _RATE_LIMIT_SCRIPT,
            (self._key("rate-buckets"),),
            self._scope(request.bucket, request.subject_fingerprint),
            request.limit,
            request.window_ms,
            request.cost,
            self._max_rate_buckets,
        )
        code, remaining, retry_after_ms = self._integers(result, 3)
        return RateLimitDecision(
            backend=self.backend_name,
            accepted=code == 1,
            reason=(
                CoordinationReason.ACCEPTED
                if code == 1
                else (
                    CoordinationReason.RATE_LIMITED
                    if code == 0
                    else CoordinationReason.BACKEND_CAPACITY_EXHAUSTED
                )
            ),
            remaining=remaining,
            retry_after_ms=retry_after_ms if code == 0 else None,
        )

    def claim_duplicate(
        self, request: DeduplicationRequest
    ) -> DeduplicationDecision:
        from uuid import uuid4

        claim_id = str(uuid4())
        result = self._eval(
            _DEDUP_CLAIM_SCRIPT,
            (
                self._key("claims"),
                self._key("claim-scopes"),
                self._key("claim-expiry"),
            ),
            self._scope(request.namespace, request.key_fingerprint),
            self._max_deduplication_claims,
            claim_id,
            request.ttl_ms,
        )
        code, retry_after_ms = self._integers(result, 2)
        if code == 1:
            return DeduplicationDecision(
                backend=self.backend_name,
                acquired=True,
                reason=CoordinationReason.ACCEPTED,
                claim_id=claim_id,
            )
        return DeduplicationDecision(
            backend=self.backend_name,
            acquired=False,
            reason=(
                CoordinationReason.DUPLICATE
                if code == 0
                else CoordinationReason.BACKEND_CAPACITY_EXHAUSTED
            ),
            retry_after_ms=retry_after_ms if code == 0 else None,
        )

    def forget_duplicate(self, claim_id: str) -> CoordinationRelease:
        released = bool(
            self._integer(
                self._eval(
                    _DEDUP_RELEASE_SCRIPT,
                    (
                        self._key("claims"),
                        self._key("claim-scopes"),
                        self._key("claim-expiry"),
                    ),
                    claim_id,
                )
            )
        )
        return self._release(released)

    def get_cache(self, key: CacheKey) -> CacheLookup:
        result = self._eval(
            _CACHE_GET_SCRIPT,
            (
                self._key("cache-values"),
                self._key("cache-expiry"),
                self._key("cache-recency"),
                self._key("cache-recency-sequence"),
            ),
            self._scope(key.namespace, key.key_fingerprint),
        )
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise RedisCoordinationError("Redis coordination returned invalid data.")
        if self._integer(result[0]) == 0:
            return CacheLookup(
                backend=self.backend_name,
                hit=False,
                reason=CoordinationReason.CACHE_MISS,
            )
        try:
            value = json.loads(self._text(result[1]))
        except (TypeError, ValueError) as exc:
            raise RedisCoordinationError(
                "Redis coordination returned invalid cache data."
            ) from exc
        if not isinstance(value, dict):
            raise RedisCoordinationError(
                "Redis coordination returned invalid cache data."
            )
        return CacheLookup(
            backend=self.backend_name,
            hit=True,
            reason=CoordinationReason.CACHE_HIT,
            value=value,
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
        self._eval(
            _CACHE_PUT_SCRIPT,
            (
                self._key("cache-values"),
                self._key("cache-expiry"),
                self._key("cache-recency"),
                self._key("cache-recency-sequence"),
            ),
            self._scope(request.namespace, request.key_fingerprint),
            encoded.decode("utf-8"),
            request.ttl_ms,
            self._max_cache_entries,
        )
        return CacheStoreDecision(
            backend=self.backend_name,
            stored=True,
            reason=CoordinationReason.STORED,
        )

    def invalidate_cache(self, key: CacheKey) -> CoordinationRelease:
        released = bool(
            self._integer(
                self._eval(
                    _CACHE_INVALIDATE_SCRIPT,
                    (
                        self._key("cache-values"),
                        self._key("cache-expiry"),
                        self._key("cache-recency"),
                    ),
                    self._scope(key.namespace, key.key_fingerprint),
                )
            )
        )
        return self._release(released)

    def _eval(
        self,
        script: str,
        keys: tuple[str, ...],
        *arguments: Any,
    ) -> Any:
        try:
            return self._client.eval(script, len(keys), *keys, *arguments)
        except RedisCoordinationError:
            raise
        except Exception as exc:
            raise RedisCoordinationError(
                "Redis coordination operation failed."
            ) from exc

    def _release(self, released: bool) -> CoordinationRelease:
        return CoordinationRelease(
            backend=self.backend_name,
            released=released,
            reason=(
                CoordinationReason.INVALIDATED
                if released
                else CoordinationReason.NOT_FOUND
            ),
        )

    @staticmethod
    def _scope(namespace: str, fingerprint: str) -> str:
        return f"{namespace}:{fingerprint}"

    def _key(self, name: str) -> str:
        return f"{self._key_prefix}:{name}"

    @classmethod
    def _integers(cls, value: Any, length: int) -> tuple[int, ...]:
        if not isinstance(value, (list, tuple)) or len(value) != length:
            raise RedisCoordinationError("Redis coordination returned invalid data.")
        return tuple(cls._integer(item) for item in value)

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise RedisCoordinationError(
                "Redis coordination returned invalid data."
            ) from exc

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if isinstance(value, str):
            return value
        raise RedisCoordinationError("Redis coordination returned invalid data.")


__all__ = [
    "RedisCoordinationError",
    "RedisRuntimeCoordinationBackend",
    "RedisScriptClient",
]
