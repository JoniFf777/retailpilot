"""Versioned, PII-safe ShopMind Outbox event contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.orders.models import ShopMindOrder
from app.payments.models import ShopMindPaymentAttempt


EVENT_VERSION = 1
ORDER_CREATED_EVENT = "shopmind.order.created.v1"
ORDER_CANCELLED_EVENT = "shopmind.order.cancelled.v1"
ORDER_EXPIRED_EVENT = "shopmind.order.expired.v1"
PAYMENT_SUCCEEDED_EVENT = "shopmind.payment.succeeded.v1"
EventType = Literal[
    "shopmind.order.created.v1",
    "shopmind.order.cancelled.v1",
    "shopmind.order.expired.v1",
    "shopmind.payment.succeeded.v1",
]


class OutboxEventEnvelope(BaseModel):
    """The immutable body sent to RocketMQ on every retry."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: EventType
    event_version: Literal[1] = EVENT_VERSION
    aggregate_type: Literal["order"] = "order"
    aggregate_id: UUID
    aggregate_sequence: int = Field(ge=1)
    occurred_at: datetime
    payload: dict[str, Any]


def _money(value: Decimal, currency: str) -> dict[str, str]:
    return {"amount": format(Decimal(value).quantize(Decimal("0.01")), ".2f"), "currency": currency}


def build_order_created_event(
    order: ShopMindOrder, *, occurred_at: datetime | None = None
) -> OutboxEventEnvelope:
    return OutboxEventEnvelope(
        event_id=uuid4(),
        event_type=ORDER_CREATED_EVENT,
        aggregate_id=order.id,
        aggregate_sequence=order.version,
        occurred_at=occurred_at or order.created_at,
        payload={
            "order_id": str(order.id),
            "currency": order.currency,
            "subtotal": _money(order.subtotal_amount, order.currency),
            "total": _money(order.total_amount, order.currency),
            "items": [
                {
                    "item_id": str(item.id),
                    "sku_id": str(item.sku_id),
                    "product_code": item.product_code_snapshot,
                    "product_name": item.product_name_snapshot,
                    "sku_code": item.sku_code_snapshot,
                    "sku_name": item.sku_name_snapshot,
                    "unit_money": _money(item.unit_price_amount, item.currency),
                    "quantity": item.quantity,
                    "subtotal_money": _money(item.line_total_amount, item.currency),
                }
                for item in sorted(order.items, key=lambda row: str(row.id))
            ],
        },
    )


def build_order_cancelled_event(
    order: ShopMindOrder, *, occurred_at: datetime
) -> OutboxEventEnvelope:
    return OutboxEventEnvelope(
        event_id=uuid4(),
        event_type=ORDER_CANCELLED_EVENT,
        aggregate_id=order.id,
        aggregate_sequence=order.version,
        occurred_at=occurred_at,
        payload={"order_id": str(order.id), "status": "cancelled"},
    )


def build_order_expired_event(
    order: ShopMindOrder,
    *,
    occurred_at: datetime,
    reason: str = "payment_deadline",
) -> OutboxEventEnvelope:
    return OutboxEventEnvelope(
        event_id=uuid4(),
        event_type=ORDER_EXPIRED_EVENT,
        aggregate_id=order.id,
        aggregate_sequence=order.version,
        occurred_at=occurred_at,
        payload={
            "order_id": str(order.id),
            "status": "expired",
            "expired_at": occurred_at.isoformat(),
            "reason": reason,
        },
    )


def build_payment_succeeded_event(
    order: ShopMindOrder,
    attempt: ShopMindPaymentAttempt,
    *,
    occurred_at: datetime,
) -> OutboxEventEnvelope:
    return OutboxEventEnvelope(
        event_id=uuid4(),
        event_type=PAYMENT_SUCCEEDED_EVENT,
        aggregate_id=order.id,
        aggregate_sequence=order.version,
        occurred_at=occurred_at,
        payload={
            "order_id": str(order.id),
            "payment_attempt_id": str(attempt.id),
            "provider": attempt.provider,
            "provider_payment_id": attempt.provider_payment_id,
            "amount": _money(attempt.amount, attempt.currency),
            "currency": attempt.currency,
        },
    )
