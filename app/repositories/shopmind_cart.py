"""Repository for the isolated SKU cart. Callers own commit/rollback."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.cart.models import MAX_CART_ITEM_QUANTITY, ShopMindCartItem
from app.catalog.models import CatalogInventory, CatalogProduct, CatalogSku
from app.schemas.cart import CartItemView, CartResponse, CartWarning
from app.schemas.recommendation import AvailabilityView, Money


def get_cart_item_for_update(
    session: Session, *, user_id: str, sku_id: UUID
) -> ShopMindCartItem | None:
    return session.scalar(
        select(ShopMindCartItem)
        .where(ShopMindCartItem.user_id == user_id, ShopMindCartItem.sku_id == sku_id)
        .with_for_update()
    )


def get_cart_item_by_id_for_update(
    session: Session, *, user_id: str, cart_item_id: UUID
) -> ShopMindCartItem | None:
    return session.scalar(
        select(ShopMindCartItem)
        .where(ShopMindCartItem.id == cart_item_id, ShopMindCartItem.user_id == user_id)
        .with_for_update()
    )


def update_cart_item_quantity(
    session: Session, *, item: ShopMindCartItem, quantity: int
) -> ShopMindCartItem:
    if not 1 <= quantity <= MAX_CART_ITEM_QUANTITY:
        raise ValueError("cart quantity is out of bounds")
    item.quantity = quantity
    item.version += 1
    item.updated_at = datetime.now(timezone.utc)
    session.flush()
    return item


def delete_cart_item(session: Session, *, item: ShopMindCartItem) -> None:
    session.delete(item)
    session.flush()


def clear_cart(session: Session, *, user_id: str) -> int:
    result = session.execute(
        delete(ShopMindCartItem).where(ShopMindCartItem.user_id == user_id)
    )
    session.flush()
    return int(result.rowcount or 0)


def upsert_cart_item(
    session: Session,
    *,
    user_id: str,
    sku_id: UUID,
    quantity: int,
) -> ShopMindCartItem:
    if not 1 <= quantity <= MAX_CART_ITEM_QUANTITY:
        raise ValueError("cart quantity is out of bounds")
    item = get_cart_item_for_update(session, user_id=user_id, sku_id=sku_id)
    if item is None:
        item = ShopMindCartItem(user_id=user_id, sku_id=sku_id, quantity=quantity, version=1)
        session.add(item)
    else:
        item.quantity = quantity
        item.version += 1
        item.updated_at = datetime.now(timezone.utc)
    session.flush()
    return item


def list_cart_items(session: Session, *, user_id: str) -> list[CartItemView]:
    rows = list_cart_catalog_rows(session, user_id=user_id)
    return [_to_view(item, sku, product, inventory) for item, sku, product, inventory in rows]


def list_cart_catalog_rows(
    session: Session,
    *,
    user_id: str,
    for_update: bool = False,
    stable_sku_order: bool = False,
) -> list[tuple[ShopMindCartItem, CatalogSku, CatalogProduct, CatalogInventory | None]]:
    query = (
        select(ShopMindCartItem, CatalogSku, CatalogProduct, CatalogInventory)
        .join(CatalogSku, ShopMindCartItem.sku_id == CatalogSku.id)
        .join(CatalogProduct, CatalogSku.product_id == CatalogProduct.id)
        .outerjoin(CatalogInventory, CatalogInventory.sku_id == CatalogSku.id)
        .where(ShopMindCartItem.user_id == user_id)
    )
    if stable_sku_order:
        query = query.order_by(ShopMindCartItem.sku_id.asc(), ShopMindCartItem.id.asc())
    else:
        query = query.order_by(ShopMindCartItem.updated_at.asc(), ShopMindCartItem.id.asc())
    if for_update:
        query = query.with_for_update(of=ShopMindCartItem)
    return list(session.execute(query).all())


def list_cart_rows_for_update(session: Session, *, user_id: str) -> list[ShopMindCartItem]:
    return list(
        session.scalars(
            select(ShopMindCartItem)
            .where(ShopMindCartItem.user_id == user_id)
            .order_by(ShopMindCartItem.id.asc())
            .with_for_update()
        ).all()
    )


def delete_cart_item_exact(
    session: Session,
    *,
    user_id: str,
    cart_item_id,
    sku_id,
    quantity: int,
    version: int,
) -> int:
    result = session.execute(
        delete(ShopMindCartItem).where(
            ShopMindCartItem.user_id == user_id,
            ShopMindCartItem.id == cart_item_id,
            ShopMindCartItem.sku_id == sku_id,
            ShopMindCartItem.quantity == quantity,
            ShopMindCartItem.version == version,
        )
    )
    session.flush()
    return int(result.rowcount or 0)


def get_cart_response(session: Session, *, user_id: str) -> CartResponse:
    items = list_cart_items(session, user_id=user_id)
    warnings: list[CartWarning] = []
    currencies = {item.unit_money.currency for item in items}
    for item in items:
        reason = item.availability.reason_code
        if reason in {"product_inactive", "sku_inactive", "inventory_missing", "out_of_stock"}:
            warnings.append(
                CartWarning(
                    code=reason,
                    cart_item_id=item.cart_item_id,
                    sku_id=item.sku_id,
                    message=_warning_message(reason),
                )
            )
        elif item.availability.available_quantity < item.quantity:
            warnings.append(
                CartWarning(
                    code="insufficient_inventory",
                    cart_item_id=item.cart_item_id,
                    sku_id=item.sku_id,
                    message="当前库存不足以满足购物车数量。",
                )
            )
    subtotal = None
    currency = None
    if len(currencies) == 1:
        currency = next(iter(currencies))
        total = sum(
            (Decimal(item.subtotal_money.amount) for item in items),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        if items:
            subtotal = Money(amount=format(total, ".2f"), currency=currency)
    elif len(currencies) > 1:
        warnings.append(
            CartWarning(
                code="mixed_currency",
                message="购物车包含多种币种，暂不进行跨币种汇总。",
            )
        )
    return CartResponse(
        items=items,
        item_count=len(items),
        total_quantity=sum(item.quantity for item in items),
        subtotal=subtotal,
        currency=currency,
        warnings=warnings,
    )


def get_cart_item_view(
    session: Session, *, user_id: str, sku_id: UUID
) -> CartItemView | None:
    row = session.execute(
        select(ShopMindCartItem, CatalogSku, CatalogProduct, CatalogInventory)
        .join(CatalogSku, ShopMindCartItem.sku_id == CatalogSku.id)
        .join(CatalogProduct, CatalogSku.product_id == CatalogProduct.id)
        .outerjoin(CatalogInventory, CatalogInventory.sku_id == CatalogSku.id)
        .where(ShopMindCartItem.user_id == user_id, ShopMindCartItem.sku_id == sku_id)
    ).first()
    if row is None:
        return None
    return _to_view(*row)


def _to_view(
    item: ShopMindCartItem,
    sku: CatalogSku,
    product: CatalogProduct,
    inventory: CatalogInventory | None,
) -> CartItemView:
    available = 0 if inventory is None else max(0, inventory.on_hand_quantity - inventory.reserved_quantity)
    product_active = product.sale_status == "active"
    sku_active = sku.sale_status == "active"
    if product_active and sku_active:
        effective_status = "active"
    elif product.sale_status == "inactive" or sku.sale_status == "inactive":
        effective_status = "inactive"
    else:
        effective_status = "draft"
    reason = None
    if inventory is None:
        reason = "inventory_missing"
    elif not product_active:
        reason = "product_inactive"
    elif not sku_active:
        reason = "sku_inactive"
    elif available <= 0:
        reason = "out_of_stock"
    availability = AvailabilityView(
        sale_status=effective_status,
        available_quantity=available,
        in_stock=effective_status == "active" and available > 0,
        reason_code=reason,
    )
    amount = Decimal(sku.money_amount).quantize(Decimal("0.01"))
    return CartItemView(
        cart_item_id=item.id,
        sku_id=sku.id,
        sku_code=sku.sku_code,
        product_id=product.id,
        product_code=product.product_code,
        product_name=product.name,
        sku_name=sku.name,
        quantity=item.quantity,
        unit_money=Money(amount=format(amount, ".2f"), currency=sku.currency),
        subtotal_money=Money(
            amount=format((amount * item.quantity).quantize(Decimal("0.01")), ".2f"),
            currency=sku.currency,
        ),
        product_sale_status=product.sale_status,
        sku_sale_status=sku.sale_status,
        effective_sale_status=effective_status,
        availability=availability,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version=item.version,
    )


def _warning_message(code: str) -> str:
    return {
        "product_inactive": "商品当前不可售。",
        "sku_inactive": "SKU 当前不可售。",
        "inventory_missing": "库存信息暂不可用。",
        "out_of_stock": "当前无可用库存。",
    }.get(code, "购物车状态需要关注。")
