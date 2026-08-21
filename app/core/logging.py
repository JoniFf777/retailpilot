"""PII-safe JSON event logging and request correlation context."""

from __future__ import annotations

import contextvars
import json
import logging
import re
from typing import Any


LOGGER = logging.getLogger("shopmind.observability")
LOGGER.setLevel(logging.INFO)

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "shopmind_correlation_id", default=None
)
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "shopmind_request_id", default=None
)
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "shopmind_trace_id", default=None
)

_SAFE_FIELDS = {
    "correlation_id",
    "request_id",
    "trace_id",
    "run_id",
    "thread_id",
    "pending_action_id",
    "order_id",
    "payment_attempt_id",
    "outbox_event_id",
    "aggregate_id",
    "aggregate_sequence",
    "event",
    "action",
    "status",
    "duration_ms",
    "error_code",
    "error_class",
    "error_message",
    "attempt_count",
    "redrive_count",
    "publisher_enabled",
    "pending",
    "publishing",
    "published",
    "dead_letter",
    "oldest_pending_seconds",
    "lease_until",
}

_SENSITIVE_VALUE = re.compile(
    r"(?i)(?:user[-_]?id|owner[-_]?id|email|phone|payment[-_]?method[-_]?ref|"
    r"checkout[_ -]?token|idempotency[-_]?key|provider[-_]?idempotency[-_]?key|"
    r"request[-_]?hash|authorization|cookie|secret|api[-_]?key|password)"
    r"\s*[\"']?\s*[:=]\s*[\"']?[^,\s}\"']+"
)


def set_request_context(
    *, correlation_id: str, request_id: str, trace_id: str
) -> tuple[contextvars.Token, contextvars.Token, contextvars.Token]:
    """Set request context and return reset tokens for the middleware."""

    return (
        _correlation_id.set(correlation_id),
        _request_id.set(request_id),
        _trace_id.set(trace_id),
    )


def reset_request_context(
    tokens: tuple[contextvars.Token, contextvars.Token, contextvars.Token]
) -> None:
    _correlation_id.reset(tokens[0])
    _request_id.reset(tokens[1])
    _trace_id.reset(tokens[2])


def current_log_context() -> dict[str, str | None]:
    return {
        "correlation_id": _correlation_id.get(),
        "request_id": _request_id.get(),
        "trace_id": _trace_id.get(),
    }


def sanitize_error_message(value: Any, *, limit: int = 256) -> str:
    """Return a short exception message with credential-like values removed."""

    text = str(value).replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    def redact(match: re.Match[str]) -> str:
        raw = match.group(0)
        separators = [position for position in (raw.find("="), raw.find(":")) if position >= 0]
        if not separators:
            return "<redacted>"
        return raw[: min(separators) + 1] + "<redacted>"

    text = _SENSITIVE_VALUE.sub(redact, text)
    return text[:limit]


def log_event(
    event: str,
    *,
    logger: logging.Logger | None = None,
    status: str | int | None = None,
    **fields: Any,
) -> None:
    """Emit one JSON object using only explicitly approved operational fields."""

    payload: dict[str, Any] = {"event": event}
    payload.update({key: value for key, value in current_log_context().items()})
    if status is not None:
        payload["status"] = status
    for key, value in fields.items():
        if key not in _SAFE_FIELDS or value is None:
            continue
        if key == "error_message":
            payload[key] = sanitize_error_message(value)
        elif key in {"event", "action", "status", "error_code", "error_class", "lease_until"}:
            payload[key] = sanitize_error_message(value, limit=128)
        else:
            payload[key] = value
    (logger or LOGGER).info(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
    )


__all__ = [
    "LOGGER",
    "current_log_context",
    "log_event",
    "reset_request_context",
    "sanitize_error_message",
    "set_request_context",
]
