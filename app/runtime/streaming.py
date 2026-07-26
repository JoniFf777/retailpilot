"""SSE serialization helpers for the runtime event contract."""

from __future__ import annotations

import json
from threading import Lock

from .contracts import AgentEvent
from .coordination import (
    AdmissionDecision,
    AdmissionRenewal,
    AdmissionRequest,
    CoordinationRelease,
    RuntimeCoordinationBackend,
    coordination_key_fingerprint,
)
from .coordination_factory import build_runtime_coordination_backend


_STREAM_ADMISSION_SUBJECT = coordination_key_fingerprint(
    "runtime-admission", "global-stream-capacity"
)


class LocalStreamConcurrencyLimiter:
    """Non-blocking in-process admission control for active SSE executions."""

    def __init__(self) -> None:
        self._active = 0
        self._lock = Lock()

    def try_acquire(self, max_concurrency: int) -> bool:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        with self._lock:
            if self._active >= max_concurrency:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self._active <= 0:
                raise RuntimeError("stream concurrency limiter released without an admission")
            self._active -= 1

    @property
    def active_count(self) -> int:
        with self._lock:
            return self._active


STREAM_CONCURRENCY_LIMITER = LocalStreamConcurrencyLimiter()


class StreamAdmissionController:
    """Lease-based stream admission over the selected coordination backend."""

    def __init__(self, backend: RuntimeCoordinationBackend) -> None:
        self._backend = backend

    @property
    def backend_name(self) -> str:
        return self._backend.backend_name

    def try_acquire(
        self,
        max_concurrency: int,
        *,
        lease_ttl_ms: int,
    ) -> AdmissionDecision:
        return self._backend.try_acquire(
            AdmissionRequest(
                resource="runtime.stream",
                subject_fingerprint=_STREAM_ADMISSION_SUBJECT,
                limit=max_concurrency,
                lease_ttl_ms=lease_ttl_ms,
            )
        )

    def renew(self, lease_id: str, *, lease_ttl_ms: int) -> AdmissionRenewal:
        return self._backend.renew_admission(
            lease_id,
            lease_ttl_ms=lease_ttl_ms,
        )

    def release(self, lease_id: str) -> CoordinationRelease:
        return self._backend.release_admission(lease_id)


STREAM_ADMISSION_CONTROLLER = StreamAdmissionController(
    build_runtime_coordination_backend()
)


def encode_sse_event(event: AgentEvent) -> str:
    """Encode one ordered AgentEvent as a standard SSE frame."""

    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f"event: {event.event_type}\nid: {event.sequence}\ndata: {payload}\n\n"
