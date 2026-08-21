"""ShopMind cart and pending action tools.

This module implements a simple confirmation-first cart flow through the V2
repository layer. It intentionally does not use LangGraph interrupt/resume yet;
pending actions are stored explicitly and can later be connected to API
confirmation endpoints.
"""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.repositories import cart as cart_repository
from app.repositories.shopmind_cart import clear_cart, get_cart_response
from app.schemas.pending_actions import CartActionOutcome
from app.services.pending_actions import (
    PendingActionServiceError,
    cancel_pending_action as cancel_canonical_pending_action,
    confirm_add_to_cart as confirm_canonical_add_to_cart,
    confirm_save_preference as confirm_canonical_save_preference,
    prepare_save_preference_pending_action,
    prepare_legacy_add_to_cart,
)


PENDING_STATUS = cart_repository.PENDING_STATUS
CONFIRMED_STATUS = cart_repository.CONFIRMED_STATUS
CANCELLED_STATUS = cart_repository.CANCELLED_STATUS
ADD_TO_CART_ACTION = cart_repository.ADD_TO_CART_ACTION
SAVE_PREFERENCE_ACTION = cart_repository.SAVE_PREFERENCE_ACTION


class PrepareAddToCartInput(BaseModel):
    user_id: str = Field(..., description="用户 ID，不能为空。")
    product_id: str = Field(..., description="要加入购物车的商品 ID，例如 TECH-LAP-001。")
    quantity: int = Field(default=1, description="加入购物车的数量，必须大于 0。")
    thread_id: Optional[str] = Field(default=None, description="可选会话 ID，用于后续把确认动作关联到一次对话。")


class ConfirmAddToCartInput(BaseModel):
    thread_id: Optional[str] = None
    updated_arguments: Optional[dict[str, Any]] = None
    expected_version: Optional[int] = Field(default=None, ge=1)
    pending_action_id: str = Field(..., description="待确认动作 ID。")
    user_id: str = Field(..., description="用户 ID，必须与待确认动作所属用户一致。")


class CancelPendingActionInput(BaseModel):
    thread_id: Optional[str] = None
    pending_action_id: str = Field(..., description="待取消的 pending action ID。")
    user_id: str = Field(..., description="用户 ID，必须与待确认动作所属用户一致。")
    expected_version: Optional[int] = Field(default=None, ge=1)


class PrepareSavePreferenceInput(BaseModel):
    user_id: str = Field(..., min_length=1)
    preference_type: str = Field(..., min_length=1)
    preference_value: str = Field(..., min_length=1)
    thread_id: Optional[str] = None


class ConfirmSavePreferenceInput(BaseModel):
    pending_action_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    thread_id: Optional[str] = None
    expected_version: Optional[int] = Field(default=None, ge=1)
    updated_arguments: Optional[dict[str, Any]] = None


class GetCartItemsInput(BaseModel):
    user_id: str = Field(..., description="用户 ID，用于读取该用户当前购物车。")


class ClearCartItemsInput(BaseModel):
    user_id: str = Field(..., description="用户 ID，用于清理测试购物车和 pending actions。")


ProductRow = Dict[str, Any]
PendingActionRow = Dict[str, Any]


@contextmanager
def _get_cart_session():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def ensure_cart_tables() -> None:
    """Compatibility shim; V2 schema is managed by Alembic migrations."""
    return None


def _is_blank(value: Optional[str]) -> bool:
    return value is None or not value.strip()


def _format_product_snapshot(product: ProductRow, quantity: int) -> str:
    return (
        f"商品：{product['name']}（{product['product_id']}）\n"
        f"- 价格：${product['price']:.2f}\n"
        f"- 数量：{quantity}\n"
        f"- 小计：${product['price'] * quantity:.2f}"
    )


def _outcome_json(outcome: CartActionOutcome) -> str:
    return outcome.model_dump_json()


def format_cart_action_outcome(outcome: CartActionOutcome) -> str:
    """Format a typed Cart outcome only after business classification."""

    messages = {
        "catalog_not_found": "无法找到对应的 ShopMind 商品或 SKU，请重新选择商品。",
        "catalog_identifier_ambiguous": "商品标识存在冲突，请提供明确的 SKU 编码。",
        "sku_ambiguous": "该商品有多个规格，请先明确要购买的具体规格。",
        "product_inactive": "商品当前不可售。",
        "sku_inactive": "该 SKU 当前不可售。",
        "insufficient_inventory": "当前库存不足，无法完成加购。",
        "invalid_quantity": "加购数量无效。",
        "cart_quantity_limit": "购物车数量超过限制。",
        "expected_version_required": "待确认动作信息已过期，请重新加载后再确认。",
        "version_conflict": "待确认动作版本已变化，请重新加载后再确认。",
        "unsupported_action_schema": "该历史待确认动作已无法继续，请重新发起加购。",
        "action_expired": "待确认动作已过期，请重新发起加购。",
        "pending_action_not_found": "待确认动作不存在或不属于当前用户/会话。",
    }
    if outcome.status == "clarification_required":
        return messages.get(outcome.code or "sku_ambiguous", "请先明确要购买的具体规格。")
    if outcome.status == "failed":
        return messages.get(outcome.code or "", "无法处理加购动作，请稍后重试。")
    if outcome.status == "prepared" and outcome.pending_action is not None:
        preview = outcome.pending_action.preview
        if hasattr(preview, "product_name"):
            sku_code = getattr(preview, "sku_code", None) or ""
            return (
                f"已生成待确认的加入购物车动作：{preview.product_name}"
                f"（{sku_code}），数量 {preview.requested_quantity}。"
            )
        return "已生成待确认的加入购物车动作。"
    if outcome.status == "confirmed":
        if outcome.cart_item is not None:
            return f"已确认加入购物车：{outcome.cart_item.product_name}，数量 {outcome.cart_item.quantity}。"
        return "已确认加入购物车。"
    if outcome.status == "cancelled":
        return "已取消待确认动作。"
    return "无法处理加购动作，请稍后重试。"


def format_preference_action_outcome(outcome: CartActionOutcome) -> str:
    messages = {
        "expected_version_required": "待确认偏好动作缺少版本，请重新加载后再确认。",
        "version_conflict": "待确认偏好动作版本已变化，请重新加载后再确认。",
        "unsupported_action_schema": "该历史偏好动作已无法继续，请重新发起保存偏好。",
        "action_expired": "待确认偏好动作已过期，请重新发起保存偏好。",
        "pending_action_not_found": "待确认偏好动作不存在或不属于当前用户/会话。",
        "invalid_action_payload": "待确认偏好动作内容无效，请重新发起保存偏好。",
        "invalid_updated_fields": "偏好修改字段无效，请重新编辑后再确认。",
    }
    if outcome.status == "prepared":
        return "已生成待确认的保存偏好动作。"
    if outcome.status == "confirmed":
        return "已确认保存购物偏好。"
    if outcome.status == "cancelled":
        return "已取消保存购物偏好。"
    return messages.get(outcome.code or "", "无法处理保存偏好动作，请稍后重试。")


def resolve_pending_action(
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """Read server-owned action metadata for confirmation dispatch."""

    with _get_cart_session() as session:
        return cart_repository.resolve_pending_action(
            session,
            pending_action_id=pending_action_id,
            user_id=user_id,
            thread_id=thread_id,
        )


@tool(args_schema=PrepareSavePreferenceInput)
def prepare_save_preference(
    user_id: str,
    preference_type: str,
    preference_value: str,
    thread_id: Optional[str] = None,
) -> str:
    """创建保存用户偏好的待确认动作，确认前不会写入长期偏好。"""

    with _get_cart_session() as session:
        try:
            pending_action = prepare_save_preference_pending_action(
                session,
                user_id=user_id,
                preference_type=preference_type,
                preference_value=preference_value,
                thread_id=thread_id,
            )
            session.commit()
            outcome = CartActionOutcome(
                status="prepared",
                pending_action_id=pending_action.pending_action_id,
                pending_action=pending_action,
            )
        except PendingActionServiceError as exc:
            session.rollback()
            outcome = CartActionOutcome(
                status="failed",
                code=exc.code,
                details=exc.details,
            )
        except Exception:
            session.rollback()
            raise
    return _outcome_json(outcome)


@tool(args_schema=PrepareAddToCartInput)
def prepare_add_to_cart(
    user_id: str,
    product_id: str,
    quantity: int = 1,
    thread_id: Optional[str] = None,
) -> str:
    """准备把商品加入购物车，适合在用户明确想加购某个商品时调用，但需要二次确认。

    输入字段含义：
    - user_id：用户 ID，不能为空；
    - product_id：商品 ID，必须存在于商品数据库；
    - quantity：数量，必须大于 0；
    - thread_id：可选会话 ID，用于后续确认动作关联。

    返回紧凑的 machine-readable CartActionOutcome；调用方在读取 typed
    status/code 后再生成用户展示文案。
    """
    if _is_blank(user_id):
        return _outcome_json(CartActionOutcome(status="failed", code="invalid_action_payload"))
    if _is_blank(product_id):
        return _outcome_json(CartActionOutcome(status="failed", code="catalog_not_found"))

    with _get_cart_session() as session:
        try:
            outcome = prepare_legacy_add_to_cart(
                session,
                user_id=user_id.strip(),
                identifier=product_id.strip(),
                quantity=quantity,
                thread_id=thread_id,
            )
            if outcome.status == "prepared":
                session.commit()
            else:
                session.rollback()
        except PendingActionServiceError as exc:
            session.rollback()
            outcome = CartActionOutcome(status="failed", code=exc.code, details=exc.details)
    return _outcome_json(outcome)


@tool(args_schema=ConfirmAddToCartInput)
def confirm_add_to_cart(
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
    expected_version: Optional[int] = None,
    updated_arguments: Optional[dict[str, Any]] = None,
) -> str:
    """确认 canonical SKU PendingAction 并返回 machine-readable outcome。

    输入字段含义：
    - pending_action_id：prepare_add_to_cart 返回的待确认动作 ID；
    - user_id：用户 ID，必须与 pending action 所属用户一致。

    用户展示文案由调用边界在读取 typed status/code 后生成。
    """
    if _is_blank(pending_action_id):
        return _outcome_json(CartActionOutcome(status="failed", code="invalid_action_payload"))
    if _is_blank(user_id):
        return _outcome_json(CartActionOutcome(status="failed", code="invalid_action_payload"))

    with _get_cart_session() as session:
        try:
            result = confirm_canonical_add_to_cart(
                session,
                pending_action_id=pending_action_id,
                user_id=user_id.strip(),
                thread_id=thread_id,
                expected_version=expected_version,
                updated_fields=updated_arguments,
            )
            session.commit()
            outcome = CartActionOutcome(
                status="confirmed",
                pending_action_id=result.pending_action.pending_action_id,
                pending_action=result.pending_action,
                cart_item=result.cart_item,
                price_changed=result.price_changed,
                requested_quantity=result.requested_quantity,
                cart_quantity=result.cart_quantity,
                idempotent_replay=result.idempotent_replay,
            )
        except PendingActionServiceError as exc:
            if exc.persisted_terminal:
                session.commit()
            else:
                session.rollback()
            outcome = CartActionOutcome(
                status="failed",
                code=exc.code,
                pending_action=(exc.resolution_record.pending_action if exc.resolution_record else None),
                pending_action_id=(exc.resolution_record.pending_action.pending_action_id if exc.resolution_record else pending_action_id),
                details=exc.details,
                idempotent_replay=exc.idempotent_replay,
            )
        except Exception:
            session.rollback()
            raise
    return _outcome_json(outcome)


@tool(args_schema=ConfirmSavePreferenceInput)
def confirm_save_preference(
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
    expected_version: Optional[int] = None,
    updated_arguments: Optional[dict[str, Any]] = None,
) -> str:
    """确认 canonical preference PendingAction through the deterministic service."""

    with _get_cart_session() as session:
        try:
            result = confirm_canonical_save_preference(
                session,
                pending_action_id=pending_action_id,
                user_id=user_id,
                thread_id=thread_id,
                expected_version=expected_version,
                updated_fields=updated_arguments,
            )
            session.commit()
            outcome = CartActionOutcome(
                status="confirmed",
                pending_action_id=result.pending_action.pending_action_id,
                pending_action=result.pending_action,
                idempotent_replay=result.idempotent_replay,
            )
        except PendingActionServiceError as exc:
            if exc.persisted_terminal:
                session.commit()
            else:
                session.rollback()
            outcome = CartActionOutcome(
                status="failed",
                code=exc.code,
                pending_action_id=(
                    exc.resolution_record.pending_action.pending_action_id
                    if exc.resolution_record else pending_action_id
                ),
                pending_action=(
                    exc.resolution_record.pending_action if exc.resolution_record else None
                ),
                details=exc.details,
                idempotent_replay=exc.idempotent_replay,
            )
        except Exception:
            session.rollback()
            raise
    return _outcome_json(outcome)


@tool(args_schema=CancelPendingActionInput)
def cancel_pending_action(
    pending_action_id: str,
    user_id: str,
    thread_id: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> str:
    """取消待确认动作，适合在用户拒绝或放弃某个 pending action 时调用。

    输入字段含义：
    - pending_action_id：待取消的动作 ID；
    - user_id：用户 ID，必须与 pending action 所属用户一致。

    返回内容：
    - 成功时将 pending action 状态改为 cancelled；
    - 如果动作不存在、用户不匹配或不是 pending 状态，返回中文提示。
    """
    if _is_blank(pending_action_id):
        return "无法取消待确认动作：pending_action_id 不能为空。"
    if _is_blank(user_id):
        return "无法取消待确认动作：user_id 不能为空。"

    if expected_version is not None:
        with _get_cart_session() as session:
            try:
                result = cancel_canonical_pending_action(
                    session,
                    pending_action_id=pending_action_id,
                    user_id=user_id,
                    thread_id=thread_id or "",
                    expected_version=expected_version,
                )
                session.commit()
                outcome = CartActionOutcome(
                    status="cancelled",
                    pending_action_id=result.pending_action.pending_action_id,
                    pending_action=result.pending_action,
                    idempotent_replay=result.idempotent_replay,
                )
            except PendingActionServiceError as exc:
                if exc.persisted_terminal:
                    session.commit()
                else:
                    session.rollback()
                outcome = CartActionOutcome(
                    status="failed",
                    code=exc.code,
                    pending_action_id=(
                        exc.resolution_record.pending_action.pending_action_id
                        if exc.resolution_record else pending_action_id
                    ),
                    pending_action=(
                        exc.resolution_record.pending_action if exc.resolution_record else None
                    ),
                    details=exc.details,
                    idempotent_replay=exc.idempotent_replay,
                )
            except Exception:
                session.rollback()
                raise
        return _outcome_json(outcome)

    with _get_cart_session() as session:
        try:
            result = cart_repository.cancel_pending_action(
                session,
                pending_action_id,
                user_id,
                thread_id=thread_id,
            )
            if result["status"] == CANCELLED_STATUS or result.get("message") == "pending action expired":
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise

    if result["status"] == "error":
        message = result["message"]
        if message == "pending action not found":
            return f"无法取消待确认动作：动作 {pending_action_id} 不存在。"
        if message == "user mismatch":
            return "无法取消待确认动作：用户不匹配，不能取消其他用户的待处理动作。"
        if message == "pending action is not cancellable":
            return f"无法取消待确认动作：该动作当前状态为 {result['current_status']}，不能取消。"
        return f"无法取消待确认动作：{message}。"

    return f"已取消待确认动作 {pending_action_id}。"


@tool(args_schema=GetCartItemsInput)
def get_cart_items(user_id: str) -> str:
    """读取用户当前购物车，适合在用户询问购物车内容、确认已加购商品时调用。

    输入字段含义：
    - user_id：用户 ID。

    返回内容：
    - 返回购物车商品列表，包括 product_id、商品名称、数量、单价和小计；
    - 如果购物车为空，返回中文提示。
    """
    if _is_blank(user_id):
        return "无法读取购物车：user_id 不能为空。"

    with _get_cart_session() as session:
        cart = get_cart_response(session, user_id=user_id.strip())

    if not cart.items:
        return f"用户 {user_id} 的购物车暂无商品。"

    lines: List[str] = [f"用户 {user_id} 的购物车："]
    for index, item in enumerate(cart.items, 1):
        lines.append(
            f"{index}. {item.product_name}（{item.sku_code}）\n"
            f"   - 数量：{item.quantity}\n"
            f"   - 单价：{item.unit_money.amount} {item.unit_money.currency}\n"
            f"   - 小计：{item.subtotal_money.amount} {item.subtotal_money.currency}"
        )
    if cart.subtotal is not None:
        lines.append(f"购物车合计：{cart.subtotal.amount} {cart.subtotal.currency}")
    return "\n".join(lines)


@tool(args_schema=ClearCartItemsInput)
def clear_cart_items(user_id: str) -> str:
    """清理指定用户的购物车和待确认动作，主要用于测试或维护，不建议暴露给 Agent。

    输入字段含义：
    - user_id：用户 ID。

    返回内容：
    - 返回中文清理结果，说明删除的购物车记录和 pending action 记录数量。
    """
    if _is_blank(user_id):
        return "无法清理购物车：user_id 不能为空。"

    with _get_cart_session() as session:
        try:
            result = cart_repository.clear_cart_items(session, user_id.strip())
            result["deleted_cart_items"] += clear_cart(session, user_id=user_id.strip())
            session.commit()
        except Exception:
            session.rollback()
            raise

    return (
        f"已清理用户 {user_id} 的测试数据："
        f"删除购物车记录 {result['deleted_cart_items']} 条，"
        f"删除待确认动作 {result['deleted_pending_actions']} 条。"
    )


__all__ = [
    "ensure_cart_tables",
    "prepare_add_to_cart",
    "confirm_add_to_cart",
    "cancel_pending_action",
    "get_cart_items",
    "prepare_save_preference",
    "confirm_save_preference",
    "format_preference_action_outcome",
    "resolve_pending_action",
    "clear_cart_items",
]
