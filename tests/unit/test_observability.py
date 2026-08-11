"""Bounded Outbox inspection and correlation helpers."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.api.middleware import normalize_correlation_id
from app.outbox.repository import _inspection_event


def test_correlation_helper_replaces_unsafe_values() -> None:
    assert normalize_correlation_id("safe-id_01:alpha") == "safe-id_01:alpha"
    replacement = normalize_correlation_id("unsafe value")
    assert replacement != "unsafe value"
    assert len(replacement) == 36


def test_outbox_inspection_event_is_bounded_and_payload_free() -> None:
    event = SimpleNamespace(
        id=uuid4(),
        event_type="shopmind.payment.succeeded.v1",
        aggregate_id=uuid4(),
        aggregate_sequence=2,
        status="dead_letter",
        attempt_count=12,
        redrive_count=1,
        available_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        lease_until=None,
        published_at=None,
        last_error="provider_idempotency_key=secret-value; " + "x" * 500,
        payload={"order_id": "must-not-appear"},
    )

    summary = _inspection_event(event)

    assert summary["event_id"] == str(event.id)
    assert len(summary["last_error"] or "") <= 256
    assert "secret-value" not in (summary["last_error"] or "")
    assert "payload" not in summary
    assert "must-not-appear" not in str(summary)
