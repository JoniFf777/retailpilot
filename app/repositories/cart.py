"""Cart and pending action repository functions backed by SQLAlchemy sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CartItem, PendingAction, Product
from app.repositories import preferences as preference_repository


PENDING_STATUS = "pending"
CONFIRMED_STATUS = "confirmed"
CANCELLED_STATUS = "cancelled"
ADD_TO_CART_ACTION = "add_to_cart"
SAVE_PREFERENCE_ACTION = "save_preference"
EXPIRED_STATUS = "expired"
DEFAULT_PENDING_ACTION_TTL = timedelta(minutes=30)


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
        "risk_class": action.risk_class,
        "preview": action.preview_text,
        "status": action.status,
        "expires_at": action.expires_at,
        "metadata": action.metadata_json,
    }


def _get_pending_action(
    session: Session,
    pending_action_id: str,
    *,
    lock: bool = False,
) -> Optional[PendingAction]:
    statement = select(PendingAction).where(PendingAction.id == pending_action_id)
    if lock:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def resolve_pending_action(
    session: Session,
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve trusted action metadata before registry dispatch.

    The selected transition handler performs the same checks again under a row
    lock, so a state change between resolution and execution still fails closed.
    """

    if _is_blank(pending_action_id):
        return {"status": "error", "message": "pending_action_id is required"}
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}
    action = _get_pending_action(session, pending_action_id.strip())
    if action is None:
        return {"status": "error", "message": "pending action not found"}
    if action.user_id != user_id.strip():
        return {"status": "error", "message": "user mismatch"}
    if (
        action.thread_id is not None
        and thread_id is not None
        and action.thread_id != thread_id
    ):
        return {"status": "error", "message": "thread mismatch"}
    return {
        **_pending_action_to_dict(action),
        "action_status": action.status,
        "status": "resolved",
    }


def _validate_add_to_cart_updates(
    updated_arguments: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if updated_arguments is None:
        return None, None
    if not updated_arguments or set(updated_arguments) != {"quantity"}:
        return None, "invalid updated arguments"
    quantity = updated_arguments.get("quantity")
    if type(quantity) is not int or quantity <= 0:
        return None, "invalid updated arguments"
    return {"quantity": quantity}, None


def _validate_save_preference_updates(
    updated_arguments: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if updated_arguments is None:
        return None, None
    allowed = {"preference_type", "preference_value"}
    if not updated_arguments or not set(updated_arguments).issubset(allowed):
        return None, "invalid updated arguments"
    validated: dict[str, Any] = {}
    if "preference_type" in updated_arguments:
        preference_type = updated_arguments["preference_type"]
        if not isinstance(preference_type, str):
            return None, "invalid updated arguments"
        normalized_type, was_invalid = (
            preference_repository._normalize_preference_type(preference_type)
        )
        if was_invalid:
            return None, "invalid updated arguments"
        validated["preference_type"] = normalized_type
    if "preference_value" in updated_arguments:
        preference_value = updated_arguments["preference_value"]
        if not isinstance(preference_value, str) or not preference_value.strip():
            return None, "invalid updated arguments"
        validated["preference_value"] = preference_value.strip()
    return validated, None


def _is_expired(action: PendingAction, now: datetime) -> bool:
    if action.expires_at is None:
        return False
    expires_at = action.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= now


def prepare_add_to_cart(
    session: Session,
    user_id: str,
    product_id: str,
    quantity: int = 1,
    thread_id: Optional[str] = None,
    risk_class: str = "high",
    expires_at: Optional[datetime] = None,
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
    action_expires_at = expires_at or now + DEFAULT_PENDING_ACTION_TTL
    preview_text = (
        f"Add {quantity} x {product.name} ({product.product_id}) "
        f"for ${_money_to_float(product.price) * quantity:.2f}"
    )
    action = PendingAction(
        id=pending_action_id,
        user_id=user_id.strip(),
        thread_id=thread_id,
        action_type=ADD_TO_CART_ACTION,
        payload_json=payload,
        risk_class=risk_class,
        preview_text=preview_text,
        status=PENDING_STATUS,
        expires_at=action_expires_at,
        metadata_json={},
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


def prepare_save_preference(
    session: Session,
    user_id: str,
    preference_type: str,
    preference_value: str,
    thread_id: Optional[str] = None,
    risk_class: str = "medium",
    expires_at: Optional[datetime] = None,
) -> dict[str, Any]:
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}
    if _is_blank(preference_type):
        return {"status": "error", "message": "preference_type is required"}
    if _is_blank(preference_value):
        return {"status": "error", "message": "preference_value is required"}

    normalized_type, was_invalid_type = (
        preference_repository._normalize_preference_type(preference_type)
    )
    now = _now()
    action = PendingAction(
        id=str(uuid.uuid4()),
        user_id=user_id.strip(),
        thread_id=thread_id,
        action_type=SAVE_PREFERENCE_ACTION,
        payload_json={
            "preference_type": normalized_type,
            "preference_value": preference_value.strip(),
        },
        risk_class=risk_class,
        preview_text=(
            f"Save {normalized_type} preference: {preference_value.strip()}"
        ),
        status=PENDING_STATUS,
        expires_at=expires_at or now + DEFAULT_PENDING_ACTION_TTL,
        metadata_json={"preference_type_normalized": was_invalid_type},
        created_at=now,
        updated_at=now,
    )
    session.add(action)
    session.flush()
    return {
        "status": PENDING_STATUS,
        "message": "pending action created",
        "pending_action_id": action.id,
        "preference_type": normalized_type,
        "preference_value": preference_value.strip(),
    }


def confirm_add_to_cart(
    session: Session,
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
    updated_arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _is_blank(pending_action_id):
        return {"status": "error", "message": "pending_action_id is required"}
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}

    action = _get_pending_action(session, pending_action_id.strip(), lock=True)
    if action is None:
        return {"status": "error", "message": "pending action not found"}
    if action.user_id != user_id.strip():
        return {"status": "error", "message": "user mismatch"}
    if (
        action.thread_id is not None
        and thread_id is not None
        and action.thread_id != thread_id
    ):
        return {"status": "error", "message": "thread mismatch"}
    if action.status != PENDING_STATUS:
        return {
            "status": "error",
            "message": "pending action is not confirmable",
            "current_status": action.status,
        }
    if _is_expired(action, _now()):
        action.status = EXPIRED_STATUS
        action.updated_at = _now()
        session.flush()
        return {"status": "error", "message": "pending action expired"}
    if action.action_type != ADD_TO_CART_ACTION:
        return {
            "status": "error",
            "message": "unsupported action type",
            "action_type": action.action_type,
        }

    validated_updates, update_error = _validate_add_to_cart_updates(
        updated_arguments
    )
    if update_error is not None:
        return {"status": "error", "message": update_error}

    payload = dict(action.payload_json or {})
    if validated_updates is not None:
        payload.update(validated_updates)
    product_id = payload.get("product_id")
    quantity = int(payload.get("quantity", 0))
    if not product_id or quantity <= 0:
        return {"status": "error", "message": "invalid pending action payload"}

    product = session.get(Product, product_id)
    if product is None:
        return {"status": "error", "message": "product not found", "product_id": product_id}

    now = _now()
    if validated_updates is not None:
        action.payload_json = payload
        action.preview_text = (
            f"Add {quantity} x {product.name} ({product.product_id}) "
            f"for ${_money_to_float(product.price) * quantity:.2f}"
        )
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
        "updated_arguments": validated_updates,
    }


def confirm_save_preference(
    session: Session,
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
    updated_arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _is_blank(pending_action_id):
        return {"status": "error", "message": "pending_action_id is required"}
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}

    action = _get_pending_action(session, pending_action_id.strip(), lock=True)
    if action is None:
        return {"status": "error", "message": "pending action not found"}
    if action.user_id != user_id.strip():
        return {"status": "error", "message": "user mismatch"}
    if (
        action.thread_id is not None
        and thread_id is not None
        and action.thread_id != thread_id
    ):
        return {"status": "error", "message": "thread mismatch"}
    if action.status != PENDING_STATUS:
        return {
            "status": "error",
            "message": "pending action is not confirmable",
            "current_status": action.status,
        }
    if _is_expired(action, _now()):
        action.status = EXPIRED_STATUS
        action.updated_at = _now()
        session.flush()
        return {"status": "error", "message": "pending action expired"}
    if action.action_type != SAVE_PREFERENCE_ACTION:
        return {
            "status": "error",
            "message": "unsupported action type",
            "action_type": action.action_type,
        }

    validated_updates, update_error = _validate_save_preference_updates(
        updated_arguments
    )
    if update_error is not None:
        return {"status": "error", "message": update_error}

    payload = dict(action.payload_json or {})
    if validated_updates is not None:
        payload.update(validated_updates)
    preference_type = payload.get("preference_type")
    preference_value = payload.get("preference_value")
    if not preference_type or not preference_value:
        return {"status": "error", "message": "invalid pending action payload"}

    preference = preference_repository.add_user_preference(
        session,
        user_id=user_id.strip(),
        preference_type=str(preference_type),
        preference_value=str(preference_value),
    )
    if validated_updates is not None:
        action.payload_json = payload
        action.preview_text = (
            f"Save {preference_type} preference: {preference_value}"
        )
    action.status = CONFIRMED_STATUS
    action.updated_at = _now()
    session.flush()
    return {
        "status": CONFIRMED_STATUS,
        "message": "preference saved",
        "pending_action_id": action.id,
        "preference": preference,
        "updated_arguments": validated_updates,
    }


def cancel_pending_action(
    session: Session,
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    if _is_blank(pending_action_id):
        return {"status": "error", "message": "pending_action_id is required"}
    if _is_blank(user_id):
        return {"status": "error", "message": "user_id is required"}

    action = _get_pending_action(session, pending_action_id.strip(), lock=True)
    if action is None:
        return {"status": "error", "message": "pending action not found"}
    if action.user_id != user_id.strip():
        return {"status": "error", "message": "user mismatch"}
    if (
        action.thread_id is not None
        and thread_id is not None
        and action.thread_id != thread_id
    ):
        return {"status": "error", "message": "thread mismatch"}
    if action.status != PENDING_STATUS:
        return {
            "status": "error",
            "message": "pending action is not cancellable",
            "current_status": action.status,
        }
    if _is_expired(action, _now()):
        action.status = EXPIRED_STATUS
        action.updated_at = _now()
        session.flush()
        return {"status": "error", "message": "pending action expired"}

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
