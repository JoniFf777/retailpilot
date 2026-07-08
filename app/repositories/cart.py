"""Cart and pending action repository functions backed by SQLAlchemy sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CartItem, PendingAction, Product


PENDING_STATUS = "pending"
CONFIRMED_STATUS = "confirmed"
CANCELLED_STATUS = "cancelled"
ADD_TO_CART_ACTION = "add_to_cart"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_blank(value: Optional[str]) -> bool:
    return value is None or not value.strip()


def _money_to_float(value: Decimal | float | int) -> float:
    return float(value)


def _product_to_dict(product: Product) -> dict[str, Any]:
    return {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category,
        "price": _money_to_float(product.price),
        "in_stock": bool(product.in_stock),
    }


def _pending_action_to_dict(action: PendingAction) -> dict[str, Any]:
    return {
        "pending_action_id": action.id,
        "user_id": action.user_id,
        "thread_id": action.thread_id,
        "action_type": action.action_type,
        "payload": action.payload_json,
        "status": action.status,
    }


def prepare_add_to_cart(
    session: Session,
    user_id: str,
    product_id: str,
    quantity: int = 1,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}
    if _is_blank(product_id):
        return {"status": "error", "message": "product_id is required"}
    if quantity <= 0:
        return {"status": "error", "message": "quantity must be greater than 0"}

    product = session.get(Product, product_id.strip())
    if product is None:
        return {
            "status": "error",
            "message": "product not found",
            "product_id": product_id,
        }

    pending_action_id = str(uuid.uuid4())
    now = _now()
    payload = {"product_id": product.product_id, "quantity": quantity}
    action = PendingAction(
        id=pending_action_id,
        user_id=user_id.strip(),
        thread_id=thread_id,
        action_type=ADD_TO_CART_ACTION,
        payload_json=payload,
        status=PENDING_STATUS,
        created_at=now,
        updated_at=now,
    )
    session.add(action)
    session.flush()

    return {
        "status": PENDING_STATUS,
        "message": "pending action created",
        "pending_action_id": pending_action_id,
        "product": _product_to_dict(product),
        "quantity": quantity,
    }


def confirm_add_to_cart(
    session: Session, pending_action_id: str, user_id: str
) -> dict[str, Any]:
    if _is_blank(pending_action_id):
        return {"status": "error", "message": "pending_action_id is required"}
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}

    action = session.get(PendingAction, pending_action_id.strip())
    if action is None:
        return {"status": "error", "message": "pending action not found"}
    if action.user_id != user_id.strip():
        return {"status": "error", "message": "user mismatch"}
    if action.status != PENDING_STATUS:
        return {
            "status": "error",
            "message": "pending action is not confirmable",
            "current_status": action.status,
        }
    if action.action_type != ADD_TO_CART_ACTION:
        return {
            "status": "error",
            "message": "unsupported action type",
            "action_type": action.action_type,
        }

    payload = action.payload_json or {}
    product_id = payload.get("product_id")
    quantity = int(payload.get("quantity", 0))
    if not product_id or quantity <= 0:
        return {"status": "error", "message": "invalid pending action payload"}

    product = session.get(Product, product_id)
    if product is None:
        return {"status": "error", "message": "product not found", "product_id": product_id}

    now = _now()
    cart_item = CartItem(
        user_id=user_id.strip(),
        product_id=product_id,
        quantity=quantity,
        created_at=now,
        updated_at=now,
    )
    session.add(cart_item)
    action.status = CONFIRMED_STATUS
    action.updated_at = now
    session.flush()

    return {
        "status": CONFIRMED_STATUS,
        "message": "cart item added",
        "pending_action_id": action.id,
        "cart_item_id": cart_item.id,
        "product": _product_to_dict(product),
        "quantity": quantity,
    }


def cancel_pending_action(
    session: Session, pending_action_id: str, user_id: str
) -> dict[str, Any]:
    if _is_blank(pending_action_id):
        return {"status": "error", "message": "pending_action_id is required"}
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}

    action = session.get(PendingAction, pending_action_id.strip())
    if action is None:
        return {"status": "error", "message": "pending action not found"}
    if action.user_id != user_id.strip():
        return {"status": "error", "message": "user mismatch"}
    if action.status != PENDING_STATUS:
        return {
            "status": "error",
            "message": "pending action is not cancellable",
            "current_status": action.status,
        }

    action.status = CANCELLED_STATUS
    action.updated_at = _now()
    session.flush()
    return {
        "status": CANCELLED_STATUS,
        "message": "pending action cancelled",
        "pending_action_id": action.id,
    }


def get_cart_items(session: Session, user_id: str) -> list[dict[str, Any]]:
    statement = (
        select(CartItem, Product)
        .join(Product, Product.product_id == CartItem.product_id)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.id.asc())
    )
    items: list[dict[str, Any]] = []
    for cart_item, product in session.execute(statement).all():
        product_dict = _product_to_dict(product)
        items.append(
            {
                "id": cart_item.id,
                "user_id": cart_item.user_id,
                "product_id": cart_item.product_id,
                "quantity": cart_item.quantity,
                "unit_price": product_dict["price"],
                "subtotal": product_dict["price"] * cart_item.quantity,
                "product": product_dict,
            }
        )
    return items


def clear_cart_items(session: Session, user_id: str) -> dict[str, Any]:
    cart_result = session.execute(delete(CartItem).where(CartItem.user_id == user_id))
    action_result = session.execute(
        delete(PendingAction).where(PendingAction.user_id == user_id)
    )
    session.flush()
    return {
        "user_id": user_id,
        "deleted_cart_items": cart_result.rowcount or 0,
        "deleted_pending_actions": action_result.rowcount or 0,
    }
