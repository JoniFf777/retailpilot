"""Transactional Outbox enqueue, claim, completion, and re-drive operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from uuid import UUID, uuid4

from sqlalchemy import case, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.outbox.contracts import OutboxEventEnvelope
from app.outbox.models import ShopMindOutboxEvent
from app.core.logging import log_event, sanitize_error_message


DEFAULT_BASE_BACKOFF_SECONDS = 5
DEFAULT_MAX_BACKOFF_SECONDS = 15 * 60
DEFAULT_MAX_ATTEMPTS = 12
DEFAULT_LEASE_SECONDS = 60
MAX_LAST_ERROR_LENGTH = 1024
DEFAULT_HEALTH_COUNT_CAP = 1000
_SAFE_FAILURE_DIAGNOSTIC = re.compile(
    r"^(?:RocketMQ|Outbox) publish failed \([A-Za-z_][A-Za-z0-9_]{0,63}\)$"
)


@dataclass(frozen=True)
class OutboxClaim:
    event_id: UUID
    lease_owner: UUID
    attempt_count: int
    envelope: OutboxEventEnvelope


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _age_seconds(value: datetime | None) -> float | None:
    if value is None:
        return None
    normalized = value
    if normalized.tzinfo is None or normalized.utcoffset() is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - normalized.astimezone(timezone.utc)).total_seconds())


def _inspection_event(event: ShopMindOutboxEvent) -> dict[str, object | None]:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "aggregate_id": str(event.aggregate_id),
        "aggregate_sequence": event.aggregate_sequence,
        "status": event.status,
        "attempt_count": event.attempt_count,
        "redrive_count": event.redrive_count,
        "available_at": _iso_datetime(event.available_at),
        "lease_until": _iso_datetime(event.lease_until),
        "published_at": _iso_datetime(event.published_at),
        "last_error": (
            sanitize_error_message(event.last_error, limit=256)
            if event.last_error
            else None
        ),
    }


def _safe_failure_diagnostic(value: str) -> str:
    """Persist only the publisher's stable diagnostic contract.

    ``mark_failure`` is also used by tests and operator-facing code, so the
    repository remains fail-closed if a caller accidentally passes an
    arbitrary exception string instead of the publisher-generated message.
    """

    candidate = str(value).replace("\x00", " ")
    if _SAFE_FAILURE_DIAGNOSTIC.fullmatch(candidate):
        return candidate[:MAX_LAST_ERROR_LENGTH]
    return "Outbox publish failed (diagnostic unavailable)"


def get_outbox_operational_snapshot(
    session: Session,
    *,
    recent_limit: int = 10,
) -> dict[str, object]:
    """Return a bounded, payload-free Outbox operational summary."""

    bounded_limit = max(1, min(int(recent_limit), 10))
    current = ShopMindOutboxEvent
    counts = session.execute(
        select(
            func.count(current.id).filter(current.status == "pending"),
            func.count(current.id).filter(current.status == "publishing"),
            func.count(current.id).filter(current.status == "published"),
            func.count(current.id).filter(current.status == "dead_letter"),
        )
    ).one()
    oldest_pending = session.scalar(
        select(func.min(current.created_at)).where(current.status == "pending")
    )
    oldest_lease = session.scalar(
        select(func.min(current.lease_until)).where(current.status == "publishing")
    )
    recent_dead_letters = list(
        session.scalars(
            select(current)
            .where(current.status == "dead_letter")
            .order_by(current.updated_at.desc(), current.id.desc())
            .limit(bounded_limit)
        ).all()
    )
    recent_failures = list(
        session.scalars(
            select(current)
            .where(current.last_error.is_not(None))
            .order_by(current.updated_at.desc(), current.id.desc())
            .limit(bounded_limit)
        ).all()
    )
    return {
        "pending": int(counts[0] or 0),
        "publishing": int(counts[1] or 0),
        "published": int(counts[2] or 0),
        "dead_letter": int(counts[3] or 0),
        "oldest_pending_seconds": _age_seconds(oldest_pending),
        "oldest_publishing_lease_expiry": _iso_datetime(oldest_lease),
        "recent_dead_letters": [_inspection_event(event) for event in recent_dead_letters],
        "recent_publish_failures": [_inspection_event(event) for event in recent_failures],
    }


def get_outbox_health_snapshot(
    session: Session,
    *,
    count_cap: int = DEFAULT_HEALTH_COUNT_CAP,
) -> dict[str, object]:
    """Return only bounded counters for health/readiness requests.

    This deliberately does not load recent rows or Outbox payloads.  Each
    status count is capped by the database subquery at ``count_cap + 1`` so a
    large historical Outbox cannot make readiness enumerate the full table.
    """

    bounded_cap = max(1, min(int(count_cap), DEFAULT_HEALTH_COUNT_CAP))
    current = ShopMindOutboxEvent

    def capped_count(status: str):
        limited = (
            select(current.id)
            .where(current.status == status)
            .limit(bounded_cap + 1)
            .subquery()
        )
        return select(func.count()).select_from(limited).scalar_subquery()

    counts = session.execute(
        select(
            capped_count("pending"),
            capped_count("publishing"),
            capped_count("published"),
            capped_count("dead_letter"),
        )
    ).one()
    oldest_pending = session.scalar(
        select(current.created_at)
        .where(current.status == "pending")
        .order_by(current.created_at.asc(), current.id.asc())
        .limit(1)
    )

    def bounded_value(value: int) -> tuple[int, bool]:
        return min(int(value or 0), bounded_cap), int(value or 0) > bounded_cap

    pending, pending_truncated = bounded_value(counts[0])
    publishing, publishing_truncated = bounded_value(counts[1])
    published, published_truncated = bounded_value(counts[2])
    dead_letter, dead_letter_truncated = bounded_value(counts[3])
    return {
        "pending": pending,
        "publishing": publishing,
        "published": published,
        "dead_letter": dead_letter,
        "oldest_pending_seconds": _age_seconds(oldest_pending),
        "pending_truncated": pending_truncated,
        "publishing_truncated": publishing_truncated,
        "published_truncated": published_truncated,
        "dead_letter_truncated": dead_letter_truncated,
    }


def enqueue_event(session: Session, envelope: OutboxEventEnvelope) -> ShopMindOutboxEvent:
    event = ShopMindOutboxEvent(
        id=envelope.event_id,
        aggregate_type=envelope.aggregate_type,
        aggregate_id=envelope.aggregate_id,
        aggregate_sequence=envelope.aggregate_sequence,
        event_type=envelope.event_type,
        event_version=envelope.event_version,
        payload=envelope.payload,
        occurred_at=envelope.occurred_at,
        status="pending",
        attempt_count=0,
        redrive_count=0,
    )
    session.add(event)
    session.flush()
    return event


def _database_now(session: Session) -> datetime:
    value = session.scalar(select(func.clock_timestamp()))
    if value is None:  # pragma: no cover - database contract failure
        raise RuntimeError("PostgreSQL did not return a database timestamp.")
    return value


def reclaim_expired(
    session: Session,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> int:
    db_now = _database_now(session)
    result = session.execute(
        update(ShopMindOutboxEvent)
        .where(
            ShopMindOutboxEvent.status == "publishing",
            ShopMindOutboxEvent.lease_until <= db_now,
        )
        .values(
            status=case(
                (ShopMindOutboxEvent.attempt_count >= max_attempts, "dead_letter"),
                else_="pending",
            ),
            lease_owner=None,
            lease_until=None,
            available_at=db_now,
            last_error="delivery lease expired before completion",
            updated_at=db_now,
        )
        .execution_options(synchronize_session=False)
    )
    # The worker normally uses a fresh short-lived session, but callers may
    # reuse a session that already loaded the row.  Expire those identities so
    # a following claim cannot mistake a reclaimed pending row for publishing.
    session.expire_all()
    return result.rowcount or 0


def _envelope(event: ShopMindOutboxEvent) -> OutboxEventEnvelope:
    return OutboxEventEnvelope(
        event_id=event.id,
        event_type=event.event_type,
        event_version=event.event_version,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        aggregate_sequence=event.aggregate_sequence,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )


def claim_pending(
    session: Session,
    *,
    batch_size: int,
    lease_seconds: int,
) -> list[OutboxClaim]:
    db_now = _database_now(session)
    current = ShopMindOutboxEvent
    # Alias the inner query so the NOT EXISTS predicate is correlated correctly.
    from sqlalchemy.orm import aliased

    previous = aliased(ShopMindOutboxEvent)
    earlier = select(1).where(
        previous.aggregate_type == current.aggregate_type,
        previous.aggregate_id == current.aggregate_id,
        previous.aggregate_sequence < current.aggregate_sequence,
        previous.status != "published",
    )
    rows = list(
        session.scalars(
            select(current)
            .where(
                current.status == "pending",
                current.available_at <= db_now,
                or_(current.lease_until.is_(None), current.lease_until <= db_now),
                ~exists(earlier),
            )
            .order_by(current.created_at.asc(), current.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
    )
    claims: list[OutboxClaim] = []
    lease_until = db_now + timedelta(seconds=lease_seconds)
    for event in rows:
        owner = uuid4()
        event.status = "publishing"
        event.lease_owner = owner
        event.lease_until = lease_until
        event.attempt_count += 1
        event.updated_at = db_now
        claims.append(
            OutboxClaim(
                event_id=event.id,
                lease_owner=owner,
                attempt_count=event.attempt_count,
                envelope=_envelope(event),
            )
        )
    session.flush()
    return claims


def mark_published(
    session: Session,
    *,
    event_id: UUID,
    lease_owner: UUID,
    broker_message_id: str,
) -> bool:
    db_now = _database_now(session)
    result = session.execute(
        update(ShopMindOutboxEvent)
        .where(
            ShopMindOutboxEvent.id == event_id,
            ShopMindOutboxEvent.status == "publishing",
            ShopMindOutboxEvent.lease_owner == lease_owner,
        )
        .values(
            status="published",
            published_at=db_now,
            broker_message_id=broker_message_id,
            last_error=None,
            lease_owner=None,
            lease_until=None,
            updated_at=db_now,
        )
        .execution_options(synchronize_session=False)
    )
    session.expire_all()
    return (result.rowcount or 0) == 1


def _backoff_seconds(
    attempt_count: int,
    *,
    base_seconds: int = DEFAULT_BASE_BACKOFF_SECONDS,
    max_seconds: int = DEFAULT_MAX_BACKOFF_SECONDS,
) -> int:
    return min(base_seconds * (2 ** max(attempt_count - 1, 0)), max_seconds)


def mark_failure(
    session: Session,
    *,
    event_id: UUID,
    lease_owner: UUID,
    attempt_count: int,
    error: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_backoff_seconds: int = DEFAULT_BASE_BACKOFF_SECONDS,
    max_backoff_seconds: int = DEFAULT_MAX_BACKOFF_SECONDS,
) -> bool:
    db_now = _database_now(session)
    status = "dead_letter" if attempt_count >= max_attempts else "pending"
    available_at = (
        db_now
        if status == "dead_letter"
        else db_now
        + timedelta(
            seconds=_backoff_seconds(
                attempt_count,
                base_seconds=base_backoff_seconds,
                max_seconds=max_backoff_seconds,
            )
        )
    )
    result = session.execute(
        update(ShopMindOutboxEvent)
        .where(
            ShopMindOutboxEvent.id == event_id,
            ShopMindOutboxEvent.status == "publishing",
            ShopMindOutboxEvent.lease_owner == lease_owner,
        )
        .values(
            status=status,
            available_at=available_at,
            lease_owner=None,
            lease_until=None,
            published_at=None,
            broker_message_id=None,
            last_error=_safe_failure_diagnostic(error),
            updated_at=db_now,
        )
        .execution_options(synchronize_session=False)
    )
    session.expire_all()
    return (result.rowcount or 0) == 1


def redrive_event(session: Session, *, event_id: UUID) -> bool:
    db_now = _database_now(session)
    result = session.execute(
        update(ShopMindOutboxEvent)
        .where(
            ShopMindOutboxEvent.id == event_id,
            ShopMindOutboxEvent.status == "dead_letter",
        )
        .values(
            status="pending",
            attempt_count=0,
            redrive_count=ShopMindOutboxEvent.redrive_count + 1,
            available_at=db_now,
            lease_owner=None,
            lease_until=None,
            last_error=None,
            published_at=None,
            broker_message_id=None,
            updated_at=db_now,
        )
        .execution_options(synchronize_session=False)
    )
    session.expire_all()
    updated = (result.rowcount or 0) == 1
    if updated:
        log_event("outbox.redriven", outbox_event_id=event_id, status="pending")
    return updated


__all__ = [
    "DEFAULT_BASE_BACKOFF_SECONDS",
    "DEFAULT_HEALTH_COUNT_CAP",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_BACKOFF_SECONDS",
    "OutboxClaim",
    "claim_pending",
    "enqueue_event",
    "get_outbox_operational_snapshot",
    "get_outbox_health_snapshot",
    "mark_failure",
    "mark_published",
    "reclaim_expired",
    "redrive_event",
]
