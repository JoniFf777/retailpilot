"""HTTP middleware for safe request correlation."""

from __future__ import annotations

import re
import time
from uuid import uuid4

from app.core.logging import (
    log_event,
    reset_request_context,
    set_request_context,
)


CORRELATION_HEADER = b"x-correlation-id"
CORRELATION_RESPONSE_HEADER = b"X-Correlation-ID"
MAX_CORRELATION_ID_LENGTH = 128
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def normalize_correlation_id(raw_value: str | None) -> str:
    """Keep only bounded opaque IDs; invalid input is safely replaced."""

    if raw_value is not None and len(raw_value) <= MAX_CORRELATION_ID_LENGTH:
        candidate = raw_value.strip()
        if _SAFE_CORRELATION_ID.fullmatch(candidate):
            return candidate
    return str(uuid4())


class CorrelationIdMiddleware:
    """Pure ASGI middleware that also covers framework-generated error responses."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or ())
        raw_value = headers.get(CORRELATION_HEADER)
        try:
            decoded = raw_value.decode("ascii") if raw_value is not None else None
        except UnicodeDecodeError:
            decoded = None
        correlation_id = normalize_correlation_id(decoded)
        request_id = str(uuid4())
        trace_id = str(uuid4())
        tokens = set_request_context(
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
        )
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        scope["state"]["request_id"] = request_id
        scope["state"]["trace_id"] = trace_id
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_correlation(message) -> None:
            nonlocal status_code, response_started
            if message.get("type") == "http.response.start":
                response_started = True
                status_code = int(message.get("status", 500))
                response_headers = list(message.get("headers") or ())
                if not any(
                    key.lower() == CORRELATION_RESPONSE_HEADER.lower()
                    for key, _value in response_headers
                ):
                    response_headers.append((CORRELATION_RESPONSE_HEADER, correlation_id.encode("ascii")))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        except Exception as exc:
            log_event(
                "http.request.failed",
                status=status_code,
                error_code="unexpected_http_error",
                error_class=type(exc).__name__,
                error_message="Unexpected HTTP request failure.",
            )
            raise
        finally:
            log_event(
                "http.request.completed",
                status=status_code if response_started else 500,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            reset_request_context(tokens)


__all__ = [
    "CORRELATION_RESPONSE_HEADER",
    "CorrelationIdMiddleware",
    "MAX_CORRELATION_ID_LENGTH",
    "normalize_correlation_id",
]
