"""Transactional confirmation boundary for shopping task actions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cart.constants import MAX_CART_ITEM_QUANTITY
from app.cart.models import ShopMindCartItem
from app.catalog.models import CatalogInventory, CatalogProduct, CatalogSku
from app.db.models import Order

from .models import AfterSalesDraft, ShoppingTask, ShoppingTaskAction, ShoppingTaskCommand
from .repository import CommandConflict, append_event, find_command


class ShoppingTaskActionError(ValueError):
    def __init__(self, code: str, *, status_code: int = 409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _lock_task(
    session: Session,
    *,
    owner_id: str,
    task_id: UUID,
) -> ShoppingTask | None:
    return session.scalar(
        select(ShoppingTask)
        .where(
            ShoppingTask.id == task_id,
            ShoppingTask.owner_id == owner_id,
            ShoppingTask.deleted_at.is_(None),
        )
        .with_for_update()
    )


def _bundle_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    options = (payload.get("bundle_proposal") or {}).get("options") or []
    option = options[0] if options else None
    if not isinstance(option, dict) or not option.get("items"):
        raise ShoppingTaskActionError("bundle_not_verified")
    aggregated: dict[UUID, dict[str, Any]] = {}
    for value in option.get("items") or []:
        try:
            sku_id = UUID(str(value["sku_id"]))
            quantity = int(value.get("quantity", 1))
            price = Decimal(str(value["price"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ShoppingTaskActionError("bundle_payload_invalid") from exc
        if quantity < 1:
            raise ShoppingTaskActionError("bundle_quantity_invalid")
        if sku_id in aggregated:
            aggregated[sku_id]["quantity"] += quantity
        else:
            aggregated[sku_id] = {
                "sku_id": sku_id,
                "sku_code": str(value.get("sku_code") or sku_id),
                "quantity": quantity,
                "price": price,
            }
    return [aggregated[key] for key in sorted(aggregated, key=str)]


def _confirm_bundle(
    session: Session,
    *,
    owner_id: str,
    payload: dict[str, Any],
) -> list[str]:
    items = _bundle_items(payload)
    sku_ids = [item["sku_id"] for item in items]
    skus = list(
        session.scalars(
            select(CatalogSku)
            .where(CatalogSku.id.in_(sku_ids))
            .order_by(CatalogSku.id.asc())
            .with_for_update()
        ).all()
    )
    by_sku = {sku.id: sku for sku in skus}
    product_ids = sorted({sku.product_id for sku in skus}, key=str)
    products = list(
        session.scalars(
            select(CatalogProduct)
            .where(CatalogProduct.id.in_(product_ids))
            .order_by(CatalogProduct.id.asc())
            .with_for_update()
        ).all()
    )
    by_product = {product.id: product for product in products}
    inventories = list(
        session.scalars(
            select(CatalogInventory)
            .where(CatalogInventory.sku_id.in_(sku_ids))
            .order_by(CatalogInventory.sku_id.asc())
            .with_for_update()
        ).all()
    )
    by_inventory = {inventory.sku_id: inventory for inventory in inventories}
    cart_rows = list(
        session.scalars(
            select(ShopMindCartItem)
            .where(
                ShopMindCartItem.user_id == owner_id,
                ShopMindCartItem.sku_id.in_(sku_ids),
            )
            .order_by(ShopMindCartItem.sku_id.asc())
            .with_for_update()
        ).all()
    )
    by_cart = {row.sku_id: row for row in cart_rows}

    if set(by_sku) != set(sku_ids) or set(by_inventory) != set(sku_ids):
        raise ShoppingTaskActionError("catalog_changed_repreview_required")
    now = datetime.now(timezone.utc)
    for item in items:
        sku = by_sku[item["sku_id"]]
        product = by_product.get(sku.product_id)
        inventory = by_inventory[item["sku_id"]]
        existing = by_cart.get(item["sku_id"])
        merged_quantity = item["quantity"] + (existing.quantity if existing else 0)
        if (
            product is None
            or product.sale_status != "active"
            or sku.sale_status != "active"
            or Decimal(sku.money_amount) != item["price"]
        ):
            raise ShoppingTaskActionError("catalog_changed_repreview_required")
        if merged_quantity > MAX_CART_ITEM_QUANTITY:
            raise ShoppingTaskActionError("cart_quantity_limit_exceeded")
        available = inventory.on_hand_quantity - inventory.reserved_quantity
        if available < merged_quantity:
            raise ShoppingTaskActionError("insufficient_inventory")

    for item in items:
        existing = by_cart.get(item["sku_id"])
        if existing is None:
            session.add(
                ShopMindCartItem(
                    user_id=owner_id,
                    sku_id=item["sku_id"],
                    quantity=item["quantity"],
                    version=1,
                )
            )
        else:
            existing.quantity += item["quantity"]
            existing.version += 1
            existing.updated_at = now
    session.flush()
    return [item["sku_code"] for item in items]


def _confirm_after_sales_draft(
    session: Session,
    *,
    owner_id: str,
    task: ShoppingTask,
    action: ShoppingTaskAction,
) -> AfterSalesDraft:
    order_payload = action.payload_json.get("order") or {}
    order_id = str(order_payload.get("order_id") or "").strip()
    if not order_id:
        raise ShoppingTaskActionError("owned_order_required")
    order = session.scalar(
        select(Order)
        .where(Order.order_id == order_id, Order.customer_id == owner_id)
        .with_for_update()
    )
    if order is None:
        raise ShoppingTaskActionError("owned_order_required")
    draft = AfterSalesDraft(
        action_id=action.id,
        task_id=task.id,
        owner_id=owner_id,
        order_id=order_id,
        payload_json={
            "assessment": action.payload_json.get("assessment") or {},
            "order": order_payload,
            "draft_only": True,
        },
    )
    session.add(draft)
    session.flush()
    return draft


def confirm_task_action(
    session: Session,
    *,
    owner_id: str,
    task_id: UUID,
    action_id: UUID,
    expected_version: int,
    confirmed: bool,
    idempotency_key: str,
) -> dict[str, Any]:
    body = {
        "user_id": owner_id,
        "expected_version": expected_version,
        "confirmed": confirmed,
    }
    operation = f"action:{action_id}:confirm"
    task = _lock_task(session, owner_id=owner_id, task_id=task_id)
    if task is None:
        raise ShoppingTaskActionError("task_not_found", status_code=404)
    try:
        replay = find_command(
            session,
            owner_id=owner_id,
            operation=operation,
            idempotency_key=idempotency_key,
            body=body,
        )
    except CommandConflict as exc:
        raise ShoppingTaskActionError(str(exc)) from exc
    if replay is not None:
        return replay.result_json or {}

    action = session.scalar(
        select(ShoppingTaskAction)
        .where(
            ShoppingTaskAction.id == action_id,
            ShoppingTaskAction.task_id == task_id,
        )
        .with_for_update()
    )
    if action is None:
        raise ShoppingTaskActionError("action_not_found", status_code=404)
    if task.version != expected_version:
        raise ShoppingTaskActionError("task_version_conflict")
    if confirmed and task.status != "awaiting_approval":
        raise ShoppingTaskActionError("task_action_not_available")
    if action.status != "pending" or action.expires_at <= datetime.now(timezone.utc):
        action.status = "expired"
        raise ShoppingTaskActionError("action_expired", status_code=410)

    if not confirmed:
        action.status = "cancelled"
        task.status = "succeeded"
        side_effect: bool | str = False
        extra: dict[str, Any] = {}
    elif action.action_type == "add_bundle_to_cart":
        extra = {
            "cart_items": _confirm_bundle(
                session,
                owner_id=owner_id,
                payload=action.payload_json,
            )
        }
        action.status = "confirmed"
        task.status = "succeeded"
        side_effect = True
    elif action.action_type == "save_after_sales_draft":
        _confirm_after_sales_draft(
            session,
            owner_id=owner_id,
            task=task,
            action=action,
        )
        action.status = "confirmed"
        task.status = "succeeded"
        side_effect = "local_draft_only"
        extra = {"draft_only": True}
    else:
        raise ShoppingTaskActionError("action_type_not_allowed", status_code=400)

    task.version += 1
    result = {
        "schema_version": "shopmind.task-action-resolution.v1",
        "task_id": str(task.id),
        "action_id": str(action.id),
        "action_version": action.action_version,
        "status": action.status,
        "side_effect": side_effect,
        **extra,
    }
    action.result_json = result
    session.add(
        ShoppingTaskCommand(
            owner_id=owner_id,
            task_id=task.id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=_hash_body(body),
            result_json=result,
        )
    )
    append_event(
        session,
        task,
        "action.confirmed" if confirmed else "action.cancelled",
        {"action_id": str(action.id), "status": action.status},
    )
    session.flush()
    return result


def _hash_body(value: Any) -> str:
    from hashlib import sha256
    import json

    return sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


__all__ = ["ShoppingTaskActionError", "confirm_task_action"]
