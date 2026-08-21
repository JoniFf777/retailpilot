"""Bounded, independently runnable Order expiration transitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.core.settings import Settings
from app.orders.models import ShopMindOrder
from app.outbox.contracts import build_order_expired_event
from app.outbox.repository import enqueue_event
from app.services.payment_safety import inspect_payment_history
from app.services.reservation_release import (
    ReservationReleaseError,
    release_active_reservations,
)


DEFAULT_EXPIRATION_BATCH_SIZE = 10


@dataclass
class ExpirationSweepSummary:
    attempted: int = 0
    expired: int = 0
    deferred_payment: int = 0
    inconsistent: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {key: int(value) for key, value in asdict(self).items()}


def _candidate_query(
    *,
    now: datetime,
    cursor: tuple[datetime, UUID] | None,
):
    query = select(ShopMindOrder).where(
        ShopMindOrder.status == "pending_payment",
        ShopMindOrder.expires_at <= now,
    )
    if cursor is not None:
        last_expires_at, last_order_id = cursor
        query = query.where(
            or_(
                ShopMindOrder.expires_at > last_expires_at,
                and_(
                    ShopMindOrder.expires_at == last_expires_at,
                    ShopMindOrder.id > last_order_id,
                ),
            )
        )
    return (
        query.order_by(ShopMindOrder.expires_at.asc(), ShopMindOrder.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True, of=ShopMindOrder)
    )


def _log_outcome(event: str, *, status: str, error_code: str | None = None) -> None:
    log_event(
        event,
        action="order_expiration",
        status=status,
        error_code=error_code,
    )


def expire_orders_once(
    session_factory,
    settings: Settings,
    *,
    now: datetime | None = None,
    batch_size: int = DEFAULT_EXPIRATION_BATCH_SIZE,
) -> ExpirationSweepSummary:
    """Attempt at most ``batch_size`` distinct Orders in one invocation.

    Every selected candidate advances the local seek cursor before its
    transaction ends, including deferred, inconsistent, and rolled-back
    outcomes. A later invocation starts with a fresh cursor and may retry it.
    """

    if batch_size < 1:
        raise ValueError("Expiration batch_size must be positive.")
    if batch_size > 100:
        raise ValueError("Expiration batch_size must not exceed 100.")
    sweep_now = now or datetime.now(timezone.utc)
    if sweep_now.tzinfo is None:
        raise ValueError("Expiration clock must be timezone-aware.")

    summary = ExpirationSweepSummary()
    cursor: tuple[datetime, UUID] | None = None
    while summary.attempted < batch_size:
        session: Session = session_factory()
        candidate = None
        try:
            candidate = session.scalar(
                _candidate_query(now=sweep_now, cursor=cursor)
            )
            if candidate is None:
                session.rollback()
                break
            if candidate.expires_at is None:  # defensive; DB CHECK prevents this
                cursor = (sweep_now, candidate.id)
                summary.attempted += 1
                summary.failed += 1
                session.rollback()
                _log_outcome(
                    "order.expiration.failed",
                    status="failed",
                    error_code="order_expiration_deadline_missing",
                )
                continue

            cursor = (candidate.expires_at, candidate.id)
            summary.attempted += 1
            decision = inspect_payment_history(
                session, order_id=candidate.id, for_update=True
            )
            if decision.status == "defer":
                summary.deferred_payment += 1
                session.rollback()
                _log_outcome(
                    "order.expiration.deferred",
                    status="deferred",
                    error_code=decision.code,
                )
                continue
            if decision.status == "inconsistent":
                summary.inconsistent += 1
                session.rollback()
                _log_outcome(
                    "order.expiration.inconsistent",
                    status="inconsistent",
                    error_code=decision.code,
                )
                continue

            transition_at = sweep_now
            try:
                release_active_reservations(
                    session,
                    order_id=candidate.id,
                    released_at=transition_at,
                )
            except ReservationReleaseError as exc:
                raise RuntimeError(exc.code) from exc
            candidate.status = "expired"
            candidate.version += 1
            candidate.updated_at = transition_at
            session.flush()
            enqueue_event(
                session,
                build_order_expired_event(
                    candidate,
                    occurred_at=transition_at,
                    reason="payment_deadline",
                ),
            )
            session.commit()
            summary.expired += 1
        except Exception as exc:
            session.rollback()
            if candidate is not None:
                summary.failed += 1
            _log_outcome(
                "order.expiration.failed",
                status="failed",
                error_code=(
                    "order_expiration_failed"
                    if candidate is not None
                    else "order_expiration_candidate_query_failed"
                ),
            )
            if candidate is None:
                break
        finally:
            session.close()
    return summary


__all__ = [
    "DEFAULT_EXPIRATION_BATCH_SIZE",
    "ExpirationSweepSummary",
    "expire_orders_once",
]
