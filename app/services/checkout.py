"""Read-only Checkout Preview service."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.checkout.tokens import (
    CheckoutPriceLine,
    build_cart_fingerprint,
    create_checkout_token,
)
from app.core.settings import Settings
from app.repositories.shopmind_cart import _to_view, list_cart_catalog_rows
from app.schemas.checkout import CheckoutPreview, CheckoutPreviewItem, CheckoutWarning


class CheckoutServiceError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 503, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def preview_checkout(session: Session, *, user_id: str, settings: Settings) -> CheckoutPreview:
    if settings.shopmind_checkout_signing_secret is None:
        raise CheckoutServiceError(
            "checkout_unavailable",
            "Checkout is not configured on this server.",
            status_code=503,
        )
    rows = list_cart_catalog_rows(session, user_id=user_id, stable_sku_order=True)
    if not rows:
        return CheckoutPreview(
            items=[],
            item_count=0,
            total_quantity=0,
            warnings=[CheckoutWarning(code="cart_empty", message="Cart is empty.")],
            can_create_order=False,
            revalidation_required=True,
        )

    items = [_to_view(item, sku, product, inventory) for item, sku, product, inventory in rows]
    warnings: list[CheckoutWarning] = []
    for item in items:
        reason = item.availability.reason_code
        if reason in {"product_inactive", "sku_inactive", "inventory_missing", "out_of_stock"}:
            warnings.append(
                CheckoutWarning(
                    code=reason,
                    cart_item_id=item.cart_item_id,
                    sku_id=item.sku_id,
                    message=f"Checkout blocked: {reason}.",
                )
            )
        elif item.availability.available_quantity < item.quantity:
            warnings.append(
                CheckoutWarning(
                    code="insufficient_inventory",
                    cart_item_id=item.cart_item_id,
                    sku_id=item.sku_id,
                    message="Available inventory is below the cart quantity.",
                )
            )
    currencies = {item.unit_money.currency for item in items}
    if len(currencies) != 1:
        warnings.append(CheckoutWarning(code="mixed_currency", message="Cart contains mixed currencies."))
        currency = None
        subtotal = None
    else:
        currency = next(iter(currencies))
        total = sum((Decimal(item.subtotal_money.amount) for item in items), Decimal("0.00"))
        subtotal = Decimal(total).quantize(Decimal("0.01"))
    can_create_order = not warnings and currency is not None and subtotal is not None
    token = None
    expires_at = None
    if can_create_order:
        token_now = datetime.now(timezone.utc)
        cart_fingerprint = build_cart_fingerprint(
            {
                "cart_item_id": item.cart_item_id,
                "sku_id": item.sku_id,
                "quantity": item.quantity,
                "version": item.version,
            }
            for item in items
        )
        token = create_checkout_token(
            user_id=user_id,
            cart_fingerprint=cart_fingerprint,
            price_lines=[
                CheckoutPriceLine(
                    sku_id=item.sku_id,
                    unit_price_amount=item.unit_money.amount,
                    currency=item.unit_money.currency,
                )
                for item in items
            ],
            currency=currency,
            subtotal_amount=subtotal,
            secret=settings.shopmind_checkout_signing_secret.get_secret_value(),
            ttl_seconds=settings.shopmind_checkout_token_ttl_seconds,
            now=token_now,
        )
        expires_at = datetime.fromtimestamp(
            int(token_now.timestamp()) + settings.shopmind_checkout_token_ttl_seconds,
            tz=timezone.utc,
        )
    return CheckoutPreview(
        items=[
            CheckoutPreviewItem(
                cart_item_id=item.cart_item_id,
                sku_id=item.sku_id,
                product_name=item.product_name,
                sku_name=item.sku_name,
                quantity=item.quantity,
                unit_money=item.unit_money,
                subtotal_money=item.subtotal_money,
                availability=item.availability,
                version=item.version,
            )
            for item in items
        ],
        item_count=len(items),
        total_quantity=sum(item.quantity for item in items),
        subtotal=(
            None
            if subtotal is None or currency is None
            else {"amount": format(subtotal, ".2f"), "currency": currency}
        ),
        currency=currency,
        warnings=warnings,
        can_create_order=can_create_order,
        checkout_token=token,
        expires_at=expires_at,
        revalidation_required=True,
    )
