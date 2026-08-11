"""Phase 4A Order Create, list, detail, and cancellation services."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.models import CatalogInventory, CatalogProduct, CatalogSku
from app.checkout.tokens import CheckoutTokenError, verify_checkout_token
from app.core.settings import Settings
from app.repositories.inventory_reservations import mark_released
from app.repositories.shopmind_cart import (
    delete_cart_item_exact,
    list_cart_rows_for_update,
)
from app.repositories.shopmind_orders import (
    get_order_by_id,
    get_order_by_idempotency_key,
    get_order_item_reservations_for_update,
    has_active_payment_attempt,
    list_orders,
)
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder, ShopMindOrderItem
from app.outbox.contracts import build_order_cancelled_event, build_order_created_event
from app.outbox.repository import enqueue_event
from app.orders.state import (
    decode_order_cursor,
    encode_order_cursor,
    request_hash,
    validate_idempotency_key,
)
from app.schemas.orders import (
    CancelOrderResponse,
    CreateOrderRequest,
    CreateOrderResponse,
    OrderItemView,
    OrderListResponse,
    OrderView,
)


class OrderServiceError(ValueError):
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


def _error(code: str, message: str, status_code: int, **details) -> OrderServiceError:
    return OrderServiceError(code, message, status_code=status_code, details=details)


def _amount(value: Decimal | str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _money(value: Decimal | str, currency: str) -> dict[str, str]:
    return {"amount": format(_amount(value), ".2f"), "currency": currency}


def _order_view(order: ShopMindOrder) -> OrderView:
    return OrderView(
        order_id=order.id,
        status=order.status,
        currency=order.currency,
        subtotal=_money(order.subtotal_amount, order.currency),
        total=_money(order.total_amount, order.currency),
        items=[
            OrderItemView(
                item_id=item.id,
                sku_id=item.sku_id,
                product_code=item.product_code_snapshot,
                product_name=item.product_name_snapshot,
                sku_code=item.sku_code_snapshot,
                sku_name=item.sku_name_snapshot,
                unit_money=_money(item.unit_price_amount, item.currency),
                quantity=item.quantity,
                subtotal_money=_money(item.line_total_amount, item.currency),
            )
            for item in order.items
        ],
        version=order.version,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _response(order: ShopMindOrder, *, replay: bool) -> CreateOrderResponse:
    return CreateOrderResponse(order=_order_view(order), idempotent_replay=replay)


def _is_idempotency_unique(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(constraint_name, "constraint_name", None) == "uq_shopmind_orders_user_idempotency"


def create_order(
    session: Session,
    *,
    user_id: str,
    idempotency_key: str,
    request: CreateOrderRequest,
    settings: Settings,
) -> CreateOrderResponse:
    try:
        validate_idempotency_key(idempotency_key)
    except ValueError as exc:
        raise _error("idempotency_key_invalid", str(exc), 422) from exc
    body_hash = request_hash(request)

    existing = get_order_by_idempotency_key(
        session, user_id=user_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        if existing.request_hash != body_hash:
            raise _error(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                409,
            )
        return _response(existing, replay=True)

    try:
        verified = verify_checkout_token(
            request.checkout_token,
            user_id=user_id,
            secret=(
                settings.shopmind_checkout_signing_secret.get_secret_value()
                if settings.shopmind_checkout_signing_secret is not None
                else None
            ),
        )
    except CheckoutTokenError as exc:
        status_code = {
            "checkout_expired": 410,
            "checkout_unavailable": 503,
        }.get(exc.code, 409)
        raise _error(exc.code, exc.message, status_code) from exc

    payload = verified.payload
    now = datetime.now(timezone.utc)
    candidate = ShopMindOrder(
        user_id=user_id,
        status="pending_payment",
        currency=payload.currency,
        subtotal_amount=_amount(payload.subtotal_amount),
        total_amount=_amount(payload.subtotal_amount),
        checkout_cart_fingerprint=payload.cart_fingerprint,
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        version=1,
        created_at=now,
        updated_at=now,
    )
    try:
        with session.begin_nested():
            session.add(candidate)
            session.flush()
    except IntegrityError as exc:
        if not _is_idempotency_unique(exc):
            raise
        winner = get_order_by_idempotency_key(
            session, user_id=user_id, idempotency_key=idempotency_key
        )
        if winner is None:
            raise
        if winner.request_hash != body_hash:
            raise _error(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                409,
            )
        return _response(winner, replay=True)

    sku_ids = sorted((line.sku_id for line in payload.price_lines), key=str)
    skus = list(
        session.scalars(
            select(CatalogSku)
            .where(CatalogSku.id.in_(sku_ids))
            .order_by(CatalogSku.id.asc())
            .with_for_update()
        ).all()
    )
    sku_by_id = {sku.id: sku for sku in skus}
    product_ids = sorted({sku.product_id for sku in skus}, key=str)
    products = list(
        session.scalars(
            select(CatalogProduct)
            .where(CatalogProduct.id.in_(product_ids))
            .order_by(CatalogProduct.id.asc())
            .with_for_update()
        ).all()
    )
    product_by_id = {product.id: product for product in products}
    inventories = list(
        session.scalars(
            select(CatalogInventory)
            .where(CatalogInventory.sku_id.in_(sku_ids))
            .order_by(CatalogInventory.sku_id.asc())
            .with_for_update()
        ).all()
    )
    inventory_by_sku = {inventory.sku_id: inventory for inventory in inventories}
    cart_rows = list_cart_rows_for_update(session, user_id=user_id)
    cart_by_sku = {item.sku_id: item for item in cart_rows}
    if build_current_cart_fingerprint(cart_rows) != payload.cart_fingerprint:
        raise _error("cart_changed", "Cart changed after the Checkout Preview.", 409)
    if set(cart_by_sku) != set(sku_ids):
        raise _error("cart_changed", "Cart changed after the Checkout Preview.", 409)

    price_by_sku = {line.sku_id: line for line in payload.price_lines}
    currencies: set[str] = set()
    line_total = Decimal("0.00")
    for sku_id in sku_ids:
        sku = sku_by_id.get(sku_id)
        if sku is None:
            raise _error("price_changed", "A SKU in the Checkout token no longer exists.", 409)
        product = product_by_id.get(sku.product_id)
        if product is None:
            raise _error("price_changed", "A product in the Checkout token no longer exists.", 409)
        if product.sale_status != "active":
            raise _error("product_inactive", "A product is no longer active.", 409)
        if sku.sale_status != "active":
            raise _error("sku_inactive", "A SKU is no longer active.", 409)
        inventory = inventory_by_sku.get(sku_id)
        if inventory is None:
            raise _error("inventory_missing", "Inventory is not available for a SKU.", 409)
        currencies.add(sku.currency)
        quantity = cart_by_sku[sku_id].quantity
        available = inventory.on_hand_quantity - inventory.reserved_quantity
        if available < quantity:
            raise _error(
                "insufficient_inventory",
                "Inventory is insufficient for the requested cart quantity.",
                409,
                available_quantity=available,
                requested_quantity=quantity,
            )
    if len(currencies) != 1:
        raise _error("mixed_currency", "Order creation requires a single currency.", 409)
    for sku_id in sku_ids:
        sku = sku_by_id[sku_id]
        signed_line = price_by_sku[sku_id]
        current_amount = _amount(sku.money_amount)
        if current_amount != _amount(signed_line.unit_price_amount) or sku.currency != signed_line.currency:
            raise _error("price_changed", "A catalog price changed after the Checkout Preview.", 409)
        line_total += current_amount * cart_by_sku[sku_id].quantity
    if next(iter(currencies)) != payload.currency or line_total.quantize(Decimal("0.01")) != _amount(payload.subtotal_amount):
        raise _error("price_changed", "The Checkout total changed after the Preview.", 409)

    order_items: list[ShopMindOrderItem] = []
    for sku_id in sku_ids:
        sku = sku_by_id[sku_id]
        product = product_by_id[sku.product_id]
        quantity = cart_by_sku[sku_id].quantity
        unit_amount = _amount(sku.money_amount)
        order_item = ShopMindOrderItem(
            order_id=candidate.id,
            sku_id=sku_id,
            product_code_snapshot=product.product_code,
            product_name_snapshot=product.name,
            sku_code_snapshot=sku.sku_code,
            sku_name_snapshot=sku.name,
            unit_price_amount=unit_amount,
            currency=sku.currency,
            quantity=quantity,
            line_total_amount=(unit_amount * quantity).quantize(Decimal("0.01")),
            created_at=now,
        )
        session.add(order_item)
        order_items.append(order_item)
    session.flush()

    for order_item in order_items:
        updated = session.execute(
            update(CatalogInventory)
            .where(
                CatalogInventory.sku_id == order_item.sku_id,
                CatalogInventory.reserved_quantity + order_item.quantity
                <= CatalogInventory.on_hand_quantity,
            )
            .values(
                reserved_quantity=CatalogInventory.reserved_quantity + order_item.quantity,
                version=CatalogInventory.version + 1,
                updated_at=func.now(),
            )
            .returning(CatalogInventory.sku_id)
        ).scalar_one_or_none()
        if updated is None:
            raise _error("insufficient_inventory", "Inventory is insufficient for the requested cart quantity.", 409)
        session.add(
            ShopMindInventoryReservation(
                order_item_id=order_item.id,
                sku_id=order_item.sku_id,
                quantity=order_item.quantity,
                status="active",
                created_at=now,
            )
        )
    for cart_item in cart_rows:
        affected = delete_cart_item_exact(
            session,
            user_id=user_id,
            cart_item_id=cart_item.id,
            sku_id=cart_item.sku_id,
            quantity=cart_item.quantity,
            version=cart_item.version,
        )
        if affected != 1:
            raise _error("cart_changed", "Cart changed while creating the Order.", 409)
    candidate.items = order_items
    session.flush()
    enqueue_event(session, build_order_created_event(candidate, occurred_at=now))
    return _response(candidate, replay=False)


def build_current_cart_fingerprint(cart_rows) -> str:
    from app.checkout.tokens import build_cart_fingerprint

    return build_cart_fingerprint(
        {
            "cart_item_id": item.id,
            "sku_id": item.sku_id,
            "quantity": item.quantity,
            "version": item.version,
        }
        for item in cart_rows
    )


def list_user_orders(
    session: Session, *, user_id: str, limit: int, cursor: str | None
) -> OrderListResponse:
    try:
        decoded_cursor = decode_order_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise _error("cursor_invalid", "Order cursor is invalid.", 422) from exc
    orders = list_orders(session, user_id=user_id, limit=limit, cursor=decoded_cursor)
    next_cursor = None
    if len(orders) > limit:
        page = orders[:limit]
        last = page[-1]
        next_cursor = encode_order_cursor(last.created_at, last.id)
        orders = page
    return OrderListResponse(items=[_order_view(order) for order in orders], next_cursor=next_cursor)


def get_user_order(session: Session, *, user_id: str, order_id: UUID) -> OrderView:
    order = get_order_by_id(session, user_id=user_id, order_id=order_id)
    if order is None:
        raise _error("order_not_found", "Order was not found.", 404)
    return _order_view(order)


def cancel_order(session: Session, *, user_id: str, order_id: UUID) -> CancelOrderResponse:
    order = get_order_by_id(session, user_id=user_id, order_id=order_id, for_update=True)
    if order is None:
        raise _error("order_not_found", "Order was not found.", 404)
    if order.status == "cancelled":
        return CancelOrderResponse(order=_order_view(order), idempotent_replay=True)
    if order.status == "paid":
        raise _error("order_not_cancellable", "A paid Order cannot be cancelled.", 409)
    if has_active_payment_attempt(session, order_id=order.id):
        raise _error("payment_in_progress", "Payment is still in progress for this Order.", 409)
    rows = get_order_item_reservations_for_update(session, order_id=order.id)
    if not rows or any(reservation is None for _, reservation in rows):
        raise _error("reservation_inconsistent", "Order reservations are inconsistent.", 409)
    reservations = [reservation for _, reservation in rows]
    for item, reservation in rows:
        if (
            reservation.sku_id != item.sku_id
            or reservation.quantity != item.quantity
            or reservation.status != "active"
        ):
            raise _error("reservation_inconsistent", "Order reservations are inconsistent.", 409)
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
        raise _error("reservation_inconsistent", "Inventory is missing for an Order reservation.", 409)
    for reservation in sorted(reservations, key=lambda row: str(row.sku_id)):
        updated = session.execute(
            update(CatalogInventory)
            .where(
                CatalogInventory.sku_id == reservation.sku_id,
                CatalogInventory.reserved_quantity >= reservation.quantity,
            )
            .values(
                reserved_quantity=CatalogInventory.reserved_quantity - reservation.quantity,
                version=CatalogInventory.version + 1,
                updated_at=func.now(),
            )
            .returning(CatalogInventory.sku_id)
        ).scalar_one_or_none()
        if updated is None:
            raise _error("reservation_inconsistent", "Inventory reservation state is inconsistent.", 409)
    for reservation in reservations:
        mark_released(session, reservation)
    order.status = "cancelled"
    order.version += 1
    now = datetime.now(timezone.utc)
    order.updated_at = now
    session.flush()
    enqueue_event(session, build_order_cancelled_event(order, occurred_at=now))
    return CancelOrderResponse(order=_order_view(order), idempotent_replay=False)
