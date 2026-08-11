"""Flush-only persistence helpers for ShopMind PaymentAttempts."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.payments.models import PAYMENT_ACTIVE_STATUSES, ShopMindPaymentAttempt


def get_payment_attempt_by_key(
    session: Session,
    *,
    user_id: str,
    order_id: UUID,
    idempotency_key: str,
    for_update: bool = False,
) -> ShopMindPaymentAttempt | None:
    query = select(ShopMindPaymentAttempt).where(
        ShopMindPaymentAttempt.user_id == user_id,
        ShopMindPaymentAttempt.order_id == order_id,
        ShopMindPaymentAttempt.idempotency_key == idempotency_key,
    )
    if for_update:
        query = query.with_for_update()
    return session.scalar(query)


def get_payment_attempt_for_update(
    session: Session, *, attempt_id: UUID
) -> ShopMindPaymentAttempt | None:
    return session.scalar(
        select(ShopMindPaymentAttempt)
        .where(ShopMindPaymentAttempt.id == attempt_id)
        .with_for_update()
    )


def get_active_payment_attempt(
    session: Session, *, order_id: UUID, for_update: bool = False
) -> ShopMindPaymentAttempt | None:
    query = (
        select(ShopMindPaymentAttempt)
        .where(
            ShopMindPaymentAttempt.order_id == order_id,
            ShopMindPaymentAttempt.status.in_(PAYMENT_ACTIVE_STATUSES),
        )
        .order_by(ShopMindPaymentAttempt.created_at.asc(), ShopMindPaymentAttempt.id.asc())
        .limit(1)
    )
    if for_update:
        query = query.with_for_update()
    return session.scalar(query)


def list_payment_attempts(
    session: Session, *, user_id: str, order_id: UUID
) -> list[ShopMindPaymentAttempt]:
    return list(
        session.scalars(
            select(ShopMindPaymentAttempt)
            .where(
                ShopMindPaymentAttempt.user_id == user_id,
                ShopMindPaymentAttempt.order_id == order_id,
            )
            .order_by(
                ShopMindPaymentAttempt.created_at.desc(),
                ShopMindPaymentAttempt.id.desc(),
            )
        ).all()
    )
