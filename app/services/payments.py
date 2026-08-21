"""Phase 5A Mock Payment Attempt lifecycle and local finalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.catalog.models import CatalogInventory
from app.core.time import ensure_utc
from app.orders.models import ShopMindOrder
from app.orders.state import request_hash, validate_idempotency_key
from app.outbox.contracts import build_payment_succeeded_event
from app.outbox.repository import enqueue_event
from app.payments.models import ShopMindPaymentAttempt
from app.payments.providers import PaymentProvider, ProviderChargeRequest, ProviderOutcome
from app.repositories.shopmind_orders import (
    get_order_by_id,
    get_order_item_reservations_for_update,
)
from app.repositories.shopmind_payments import (
    get_active_payment_attempt,
    get_payment_attempt_by_key,
    get_payment_attempt_for_update,
    list_payment_attempts,
)
from app.repositories.inventory_reservations import mark_consumed
from app.schemas.payments import (
    PaymentAttemptRequest,
    PaymentAttemptResponse,
    PaymentAttemptView,
)
from app.services.orders import _order_view


PaymentClaimAction = Literal[
    "charge",
    "reconcile",
    "finalize",
    "replay_failed",
    "replay_succeeded",
]


class PaymentServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        details: dict | None = None,
        idempotent_replay: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.idempotent_replay = idempotent_replay


def _error(
    code: str,
    message: str,
    status_code: int,
    *,
    details: dict | None = None,
    idempotent_replay: bool = False,
) -> PaymentServiceError:
    return PaymentServiceError(
        code,
        message,
        status_code=status_code,
        details=details,
        idempotent_replay=idempotent_replay,
    )


@dataclass(frozen=True)
class PaymentClaim:
    action: PaymentClaimAction
    attempt_id: UUID
    order_id: UUID
    provider: str
    provider_idempotency_key: str
    amount: Decimal
    currency: str
    idempotent_replay: bool
    failure_code: str | None = None


def _claim_from_attempt(
    attempt: ShopMindPaymentAttempt,
    *,
    idempotent_replay: bool,
) -> PaymentClaim:
    action: PaymentClaimAction
    if attempt.status == "failed":
        action = "replay_failed"
    elif attempt.status == "succeeded":
        action = "replay_succeeded"
    elif attempt.status == "provider_succeeded":
        action = "finalize"
    else:
        action = "reconcile"
    return PaymentClaim(
        action=action,
        attempt_id=attempt.id,
        order_id=attempt.order_id,
        provider=attempt.provider,
        provider_idempotency_key=attempt.provider_idempotency_key,
        amount=Decimal(attempt.amount),
        currency=attempt.currency,
        idempotent_replay=idempotent_replay,
        failure_code=attempt.failure_code,
    )


def claim_payment_attempt(
    session: Session,
    *,
    user_id: str,
    order_id: UUID,
    idempotency_key: str,
    request: PaymentAttemptRequest,
) -> PaymentClaim:
    try:
        validate_idempotency_key(idempotency_key)
    except ValueError as exc:
        raise _error("idempotency_key_invalid", str(exc), 422) from exc
    body_hash = request_hash(request)

    # Owner-scoped order lookup is deliberately before any status decision.
    order = get_order_by_id(session, user_id=user_id, order_id=order_id)
    if order is None:
        raise _error("order_not_found", "Order was not found.", 404)

    existing = get_payment_attempt_by_key(
        session,
        user_id=user_id,
        order_id=order_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != body_hash:
            raise _error(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                409,
            )
        if existing.status == "succeeded" and order.status == "pending_payment":
            raise _error(
                "payment_state_inconsistent",
                "Payment state is inconsistent with the Order state.",
                409,
                details={"reason": "succeeded_payment_pending_order"},
                idempotent_replay=True,
            )
        return _claim_from_attempt(existing, idempotent_replay=True)

    # New claims serialize on the Order.  The second key lookup closes the
    # window after a concurrent transaction waited for this Order lock.
    locked_order = get_order_by_id(
        session, user_id=user_id, order_id=order_id, for_update=True
    )
    if locked_order is None:
        raise _error("order_not_found", "Order was not found.", 404)
    existing = get_payment_attempt_by_key(
        session,
        user_id=user_id,
        order_id=order_id,
        idempotency_key=idempotency_key,
        for_update=True,
    )
    if existing is not None:
        if existing.request_hash != body_hash:
            raise _error(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                409,
            )
        if existing.status == "succeeded" and locked_order.status == "pending_payment":
            raise _error(
                "payment_state_inconsistent",
                "Payment state is inconsistent with the Order state.",
                409,
                details={"reason": "succeeded_payment_pending_order"},
                idempotent_replay=True,
            )
        return _claim_from_attempt(existing, idempotent_replay=True)

    if locked_order.status == "paid":
        raise _error("order_already_paid", "The Order has already been paid.", 409)
    if locked_order.status == "expired":
        raise _error("order_expired", "The Order payment deadline has expired.", 409)
    if locked_order.status != "pending_payment":
        raise _error("order_not_payable", "The Order is not payable.", 409)
    if locked_order.expires_at is None:
        raise _error(
            "order_not_payable",
            "The Order has no valid payment deadline.",
            409,
            details={"reason": "expiration_deadline_missing"},
        )
    if datetime.now(timezone.utc) >= ensure_utc(locked_order.expires_at):
        raise _error("order_expired", "The Order payment deadline has expired.", 409)
    active = get_active_payment_attempt(
        session, order_id=locked_order.id, for_update=True
    )
    if active is not None:
        raise _error("payment_in_progress", "Payment is already in progress for this Order.", 409)

    attempt_id = uuid4()
    now = datetime.now(timezone.utc)
    attempt = ShopMindPaymentAttempt(
        id=attempt_id,
        order_id=locked_order.id,
        user_id=user_id,
        provider=request.provider,
        provider_idempotency_key=f"shopmind-payment-{attempt_id}",
        status="processing",
        amount=Decimal(locked_order.total_amount).quantize(Decimal("0.01")),
        currency=locked_order.currency,
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        created_at=now,
        updated_at=now,
    )
    session.add(attempt)
    session.flush()
    return _claim_from_attempt(attempt, idempotent_replay=False)


def provider_request(
    claim: PaymentClaim, request: PaymentAttemptRequest
) -> ProviderChargeRequest:
    return ProviderChargeRequest(
        provider_idempotency_key=claim.provider_idempotency_key,
        amount=format(claim.amount, ".2f"),
        currency=claim.currency,
        payment_method_ref=request.payment_method_ref,
    )


def resolve_provider_outcome(
    provider: PaymentProvider,
    *,
    claim: PaymentClaim,
    request: PaymentAttemptRequest,
) -> ProviderOutcome:
    if claim.action == "charge":
        return provider.charge(provider_request(claim, request))
    if claim.action == "reconcile":
        outcome = provider.get_result(claim.provider_idempotency_key)
        if outcome.status == "not_found":
            # The original call may have failed before the provider created
            # its operation. Reuse the same key; this cannot create a second
            # effective payment operation.
            return provider.charge(provider_request(claim, request))
        return outcome
    raise ValueError("Provider outcome is not applicable to this Payment claim.")


def persist_provider_outcome(
    session: Session,
    *,
    attempt_id: UUID,
    outcome: ProviderOutcome,
) -> ShopMindPaymentAttempt:
    attempt = get_payment_attempt_for_update(session, attempt_id=attempt_id)
    if attempt is None:
        raise _error("payment_provider_unavailable", "Payment Attempt was not found.", 503)
    if attempt.status in {"failed", "succeeded"}:
        return attempt
    # Provider success is durable. A late timeout or decline from an older
    # request may not downgrade it; only local finalization can make it
    # terminally succeeded.
    if attempt.status == "provider_succeeded":
        return attempt
    result_at = outcome.result_at
    if outcome.status == "succeeded":
        attempt.status = "provider_succeeded"
        attempt.provider_payment_id = outcome.provider_payment_id
        attempt.failure_code = None
        attempt.provider_result_at = result_at
        attempt.completed_at = None
    elif outcome.status == "declined":
        attempt.status = "failed"
        attempt.provider_payment_id = outcome.provider_payment_id
        attempt.failure_code = outcome.failure_code or "payment_declined"
        attempt.provider_result_at = result_at
        attempt.completed_at = result_at
    else:
        attempt.status = "unknown"
        attempt.provider_payment_id = outcome.provider_payment_id
        attempt.failure_code = outcome.failure_code or "provider_timeout"
        attempt.provider_result_at = result_at
        attempt.completed_at = None
    attempt.updated_at = datetime.now(timezone.utc)
    session.flush()
    return attempt


def finalize_payment(
    session: Session, *, user_id: str, order_id: UUID, attempt_id: UUID
) -> None:
    # Order is always locked before PaymentAttempt, matching Claim and Cancel.
    order = session.scalar(
        select(ShopMindOrder)
        .where(ShopMindOrder.id == order_id, ShopMindOrder.user_id == user_id)
        .with_for_update()
    )
    if order is None:
        raise _error("order_not_found", "Order was not found.", 404)
    attempt = get_payment_attempt_for_update(session, attempt_id=attempt_id)
    if attempt is None or attempt.order_id != order.id or attempt.user_id != user_id:
        raise _error("order_not_found", "Order was not found.", 404)
    if attempt.status == "succeeded":
        return
    if attempt.status != "provider_succeeded":
        raise _error(
            "payment_finalization_pending",
            "Payment finalization is not ready.",
            503,
            details={"reason": attempt.status},
            idempotent_replay=True,
        )
    if order.status != "pending_payment":
        raise _error(
            "payment_finalization_pending",
            "Payment finalization is pending because the Order is not payable.",
            503,
            details={"reason": "order_not_pending_payment"},
            idempotent_replay=True,
        )

    rows = get_order_item_reservations_for_update(session, order_id=order.id)
    if not rows or any(reservation is None for _, reservation in rows):
        raise _finalization_error("reservation_missing")
    reservations = [reservation for _, reservation in rows]
    for item, reservation in rows:
        if (
            reservation.sku_id != item.sku_id
            or reservation.quantity != item.quantity
            or reservation.status != "active"
        ):
            raise _finalization_error("reservation_inconsistent")

    sku_ids = sorted({reservation.sku_id for reservation in reservations}, key=str)
    inventories = list(
        session.scalars(
            select(CatalogInventory)
            .where(CatalogInventory.sku_id.in_(sku_ids))
            .order_by(CatalogInventory.sku_id.asc())
            .with_for_update()
        ).all()
    )
    inventory_by_sku = {inventory.sku_id: inventory for inventory in inventories}
    if set(inventory_by_sku) != set(sku_ids):
        raise _finalization_error("inventory_missing")
    for reservation in sorted(reservations, key=lambda row: str(row.sku_id)):
        updated = session.execute(
            update(CatalogInventory)
            .where(
                CatalogInventory.sku_id == reservation.sku_id,
                CatalogInventory.reserved_quantity >= reservation.quantity,
                CatalogInventory.on_hand_quantity >= reservation.quantity,
            )
            .values(
                on_hand_quantity=CatalogInventory.on_hand_quantity - reservation.quantity,
                reserved_quantity=CatalogInventory.reserved_quantity - reservation.quantity,
                version=CatalogInventory.version + 1,
                updated_at=datetime.now(timezone.utc),
            )
            .returning(CatalogInventory.sku_id)
        ).scalar_one_or_none()
        if updated is None:
            raise _finalization_error("inventory_conditional_consume_failed")

    for reservation in reservations:
        mark_consumed(session, reservation)
    now = datetime.now(timezone.utc)
    order.status = "paid"
    order.version += 1
    order.updated_at = now
    attempt.status = "succeeded"
    attempt.completed_at = now
    attempt.updated_at = now
    session.flush()
    enqueue_event(session, build_payment_succeeded_event(order, attempt, occurred_at=now))


def _finalization_error(reason: str) -> PaymentServiceError:
    return _error(
        "payment_finalization_pending",
        "Payment was accepted by the Provider but local finalization is pending.",
        503,
        details={"reason": reason},
        idempotent_replay=True,
    )


def payment_response(
    session: Session,
    *,
    user_id: str,
    order_id: UUID,
    attempt_id: UUID,
    idempotent_replay: bool,
) -> PaymentAttemptResponse:
    order = get_order_by_id(session, user_id=user_id, order_id=order_id)
    if order is None:
        raise _error("order_not_found", "Order was not found.", 404)
    attempt = session.scalar(
        select(ShopMindPaymentAttempt).where(
            ShopMindPaymentAttempt.id == attempt_id,
            ShopMindPaymentAttempt.order_id == order.id,
            ShopMindPaymentAttempt.user_id == user_id,
        )
    )
    if attempt is None:
        raise _error("order_not_found", "Order was not found.", 404)
    return PaymentAttemptResponse(
        payment_attempt=_attempt_view(attempt),
        order=_order_view(order),
        idempotent_replay=idempotent_replay,
    )


def list_user_payment_attempts(
    session: Session, *, user_id: str, order_id: UUID
) -> list[PaymentAttemptView]:
    order = get_order_by_id(session, user_id=user_id, order_id=order_id)
    if order is None:
        raise _error("order_not_found", "Order was not found.", 404)
    return [_attempt_view(attempt) for attempt in list_payment_attempts(session, user_id=user_id, order_id=order_id)]


def _attempt_view(attempt: ShopMindPaymentAttempt) -> PaymentAttemptView:
    return PaymentAttemptView(
        attempt_id=attempt.id,
        order_id=attempt.order_id,
        provider="mock",
        status=attempt.status,
        amount={"amount": format(Decimal(attempt.amount).quantize(Decimal("0.01")), ".2f"), "currency": attempt.currency},
        failure_code=attempt.failure_code,
        provider_result_at=attempt.provider_result_at,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
        completed_at=attempt.completed_at,
    )


__all__ = [
    "PaymentClaim",
    "PaymentServiceError",
    "claim_payment_attempt",
    "finalize_payment",
    "list_user_payment_attempts",
    "payment_response",
    "persist_provider_outcome",
    "resolve_provider_outcome",
]
