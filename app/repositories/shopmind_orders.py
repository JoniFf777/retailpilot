"""Flush-only persistence helpers for Phase 4A Orders."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.payments.models import PAYMENT_ACTIVE_STATUSES, ShopMindPaymentAttempt
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder, ShopMindOrderItem


def get_order_by_id(
    session: Session, *, user_id: str, order_id: UUID, for_update: bool = False
) -> ShopMindOrder | None:
    query = (
        select(ShopMindOrder)
        .options(selectinload(ShopMindOrder.items))
        .where(ShopMindOrder.id == order_id, ShopMindOrder.user_id == user_id)
    )
    if for_update:
        query = query.with_for_update(of=ShopMindOrder)
    return session.scalar(query)


def get_order_by_idempotency_key(
    session: Session, *, user_id: str, idempotency_key: str, for_update: bool = False
) -> ShopMindOrder | None:
    query = (
        select(ShopMindOrder)
        .options(selectinload(ShopMindOrder.items))
        .where(ShopMindOrder.user_id == user_id, ShopMindOrder.idempotency_key == idempotency_key)
    )
    if for_update:
        query = query.with_for_update(of=ShopMindOrder)
    return session.scalar(query)


def list_orders(
    session: Session,
    *,
    user_id: str,
    limit: int,
    cursor: tuple[datetime, str] | None = None,
) -> list[ShopMindOrder]:
    query = (
        select(ShopMindOrder)
        .options(selectinload(ShopMindOrder.items))
        .where(ShopMindOrder.user_id == user_id)
    )
    if cursor is not None:
        cursor_created_at, cursor_id = cursor
        query = query.where(
            or_(
                ShopMindOrder.created_at < cursor_created_at,
                and_(ShopMindOrder.created_at == cursor_created_at, ShopMindOrder.id < UUID(cursor_id)),
            )
        )
    return list(
        session.scalars(
            query.order_by(ShopMindOrder.created_at.desc(), ShopMindOrder.id.desc()).limit(limit + 1)
        ).all()
    )


def get_order_item_reservations_for_update(
    session: Session, *, order_id: UUID
) -> list[tuple[ShopMindOrderItem, ShopMindInventoryReservation]]:
    items = list(
        session.scalars(
            select(ShopMindOrderItem)
            .where(ShopMindOrderItem.order_id == order_id)
            .order_by(ShopMindOrderItem.sku_id.asc(), ShopMindOrderItem.id.asc())
            .with_for_update()
        ).all()
    )
    if not items:
        return []
    reservations = {
        reservation.order_item_id: reservation
        for reservation in session.scalars(
            select(ShopMindInventoryReservation)
            .where(
                ShopMindInventoryReservation.order_item_id.in_(
                    [item.id for item in items]
                )
            )
            .with_for_update()
        ).all()
    }
    return [(item, reservations.get(item.id)) for item in items]


def has_active_payment_attempt(
    session: Session, *, order_id: UUID, for_update: bool = False
) -> bool:
    query = (
        select(ShopMindPaymentAttempt.id)
        .where(
            ShopMindPaymentAttempt.order_id == order_id,
            ShopMindPaymentAttempt.status.in_(PAYMENT_ACTIVE_STATUSES),
        )
        .order_by(ShopMindPaymentAttempt.created_at.asc(), ShopMindPaymentAttempt.id.asc())
        .limit(1)
    )
    if for_update:
        query = query.with_for_update()
    return session.scalar(query) is not None
