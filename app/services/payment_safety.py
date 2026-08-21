"""Shared PaymentAttempt history gate for reservation-releasing transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.payments.models import PAYMENT_ACTIVE_STATUSES, ShopMindPaymentAttempt


PaymentSafetyStatus = Literal["allow", "defer", "inconsistent"]

PAYMENT_SAFETY_MATRIX: dict[str, dict[str, PaymentSafetyStatus]] = {
    "pending_payment": {
        "none": "allow",
        "failed": "allow",
        "processing": "defer",
        "unknown": "defer",
        "provider_succeeded": "defer",
        "succeeded": "inconsistent",
    },
    "paid": {"any": "allow"},
    "cancelled": {"any": "allow"},
    "expired": {"any": "allow"},
}


@dataclass(frozen=True)
class PaymentSafetyDecision:
    status: PaymentSafetyStatus
    code: str


def inspect_payment_history(
    session: Session, *, order_id: UUID, for_update: bool = True
) -> PaymentSafetyDecision:
    """Lock and classify the complete PaymentAttempt history for one Order.

    This gate deliberately has no reservation or Order mutation side effects.
    A successful attempt attached to a still-pending Order is fail-closed even
    though it is not part of the active-attempt unique index.
    """

    query = (
        select(ShopMindPaymentAttempt)
        .where(ShopMindPaymentAttempt.order_id == order_id)
        .order_by(
            ShopMindPaymentAttempt.created_at.asc(),
            ShopMindPaymentAttempt.id.asc(),
        )
    )
    if for_update:
        query = query.with_for_update()
    attempts = list(session.scalars(query).all())
    statuses = {attempt.status for attempt in attempts}
    if "succeeded" in statuses:
        return PaymentSafetyDecision(
            status="inconsistent",
            code="payment_state_inconsistent",
        )
    if statuses.intersection(PAYMENT_ACTIVE_STATUSES):
        return PaymentSafetyDecision(status="defer", code="payment_in_progress")
    if statuses.issubset({"failed"}):
        return PaymentSafetyDecision(
            status="allow",
            code="none_or_failed_only",
        )
    return PaymentSafetyDecision(
        status="inconsistent",
        code="payment_state_inconsistent",
    )


__all__ = [
    "PAYMENT_SAFETY_MATRIX",
    "PaymentSafetyDecision",
    "PaymentSafetyStatus",
    "inspect_payment_history",
]
