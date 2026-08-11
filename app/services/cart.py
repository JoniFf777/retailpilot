"""Transaction semantics for direct ShopMind Cart management.

The service owns domain validation and locking order, while API routes own the
transaction boundary (commit/rollback).  Repository functions deliberately
only flush so callers can compose this operation with other work safely.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.cart.constants import MAX_CART_ITEM_QUANTITY
from app.catalog.models import CatalogInventory, CatalogProduct, CatalogSku
from app.repositories.shopmind_cart import (
    clear_cart,
    delete_cart_item,
    get_cart_item_by_id_for_update,
    get_cart_item_view,
    get_cart_response,
    update_cart_item_quantity,
)
from app.schemas.cart import (
    CartErrorDetails,
    CartMutationResponse,
    CartResponse,
)


class CartServiceError(Exception):
    """Stable domain error mapped by the Cart API to a typed response."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        details: dict[str, Any] | CartErrorDetails | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = (
            details
            if isinstance(details, CartErrorDetails)
            else CartErrorDetails.model_validate(details or {})
        )


def get_cart(session: Session, *, user_id: str) -> CartResponse:
    return get_cart_response(session, user_id=user_id)


def update_cart_item(
    session: Session,
    *,
    user_id: str,
    cart_item_id: UUID,
    expected_version: int,
    quantity: int,
) -> CartMutationResponse:
    _validate_quantity(quantity)
    item = get_cart_item_by_id_for_update(
        session, user_id=user_id, cart_item_id=cart_item_id
    )
    if item is None:
        raise CartServiceError(
            "cart_item_not_found",
            "Cart item was not found.",
            status_code=404,
        )
    if item.version != expected_version:
        raise CartServiceError(
            "cart_version_conflict",
            "Cart item version is stale.",
            details={"current_version": item.version},
        )

    product, sku, inventory = _load_catalog_for_update(session, item.sku_id)
    if product is None or sku is None:
        raise CartServiceError(
            "catalog_not_found",
            "Catalog SKU is no longer available.",
        )
    if product.sale_status != "active":
        raise CartServiceError("product_inactive", "Catalog product is no longer active.")
    if sku.sale_status != "active":
        raise CartServiceError("sku_inactive", "Catalog SKU is no longer active.")
    if inventory is None:
        raise CartServiceError(
            "inventory_missing",
            "Inventory information is unavailable.",
        )
    available = _available(inventory)
    if quantity > available:
        raise CartServiceError(
            "insufficient_inventory",
            "Requested quantity is not currently available.",
            details={
                "available_quantity": available,
                "current_quantity": item.quantity,
                "requested_quantity": quantity,
            },
        )

    update_cart_item_quantity(session, item=item, quantity=quantity)
    item_view = get_cart_item_view(session, user_id=user_id, sku_id=item.sku_id)
    if item_view is None:  # pragma: no cover - defensive after owned lock
        raise CartServiceError("cart_item_not_found", "Cart item was not found.", status_code=404)
    return CartMutationResponse(
        item=item_view,
        cart=get_cart_response(session, user_id=user_id),
    )


def delete_cart_item_by_id(
    session: Session, *, user_id: str, cart_item_id: UUID
) -> None:
    item = get_cart_item_by_id_for_update(
        session, user_id=user_id, cart_item_id=cart_item_id
    )
    if item is None:
        return
    delete_cart_item(session, item=item)


def clear_user_cart(session: Session, *, user_id: str) -> None:
    clear_cart(session, user_id=user_id)


def _validate_quantity(quantity: int) -> None:
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise CartServiceError(
            "invalid_quantity",
            "Cart quantity must be a positive integer.",
        )
    if quantity > MAX_CART_ITEM_QUANTITY:
        raise CartServiceError(
            "cart_quantity_limit",
            "Cart quantity exceeds the maximum allowed quantity.",
            details={"max_quantity": MAX_CART_ITEM_QUANTITY},
        )


def _load_catalog_for_update(
    session: Session, sku_id: UUID
) -> tuple[CatalogProduct | None, CatalogSku | None, CatalogInventory | None]:
    # The CartItem lock is the mutation serialization point.  Catalog rows are
    # read here (not reserved or mutated); avoiding a second lock order keeps
    # PATCH compatible with the Phase 2 confirm path, which locks Catalog
    # before its CartItem.
    sku = session.get(CatalogSku, sku_id)
    if sku is None:
        return None, None, None
    product = session.get(CatalogProduct, sku.product_id)
    inventory = session.get(CatalogInventory, sku.id)
    return product, sku, inventory


def _available(inventory: CatalogInventory) -> int:
    return max(0, inventory.on_hand_quantity - inventory.reserved_quantity)
