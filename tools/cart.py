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


PENDING_STATUS = cart_repository.PENDING_STATUS
CONFIRMED_STATUS = cart_repository.CONFIRMED_STATUS
CANCELLED_STATUS = cart_repository.CANCELLED_STATUS
ADD_TO_CART_ACTION = cart_repository.ADD_TO_CART_ACTION


class PrepareAddToCartInput(BaseModel):
    user_id: str = Field(..., description="用户 ID，不能为空。")
    product_id: str = Field(..., description="要加入购物车的商品 ID，例如 TECH-LAP-001。")
    quantity: int = Field(default=1, description="加入购物车的数量，必须大于 0。")
    thread_id: Optional[str] = Field(default=None, description="可选会话 ID，用于后续把确认动作关联到一次对话。")


class ConfirmAddToCartInput(BaseModel):
    pending_action_id: str = Field(..., description="待确认动作 ID。")
    user_id: str = Field(..., description="用户 ID，必须与待确认动作所属用户一致。")


class CancelPendingActionInput(BaseModel):
    pending_action_id: str = Field(..., description="待取消的 pending action ID。")
    user_id: str = Field(..., description="用户 ID，必须与待确认动作所属用户一致。")


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

    返回内容：
    - 如果校验失败，返回中文错误提示；
    - 如果商品存在，会创建 pending action，并返回 pending_action_id、商品名称、价格、数量和中文确认提示；
    - 注意：本工具不会直接写入 cart_items，必须等待 confirm_add_to_cart 确认。
    """
    if _is_blank(user_id):
        return "无法准备加入购物车：user_id 不能为空。"
    if _is_blank(product_id):
        return "无法准备加入购物车：product_id 不能为空。"
    if quantity <= 0:
        return "无法准备加入购物车：quantity 必须大于 0。"

    with _get_cart_session() as session:
        try:
            result = cart_repository.prepare_add_to_cart(
                session,
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
                thread_id=thread_id,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

    if result["status"] == "error":
        if result["message"] == "product not found":
            return f"无法准备加入购物车：商品 {product_id} 不存在，请检查商品 ID。"
        return f"无法准备加入购物车：{result['message']}。"

    pending_action_id = result["pending_action_id"]
    product = result["product"]

    return (
        "已生成待确认的加入购物车动作。\n"
        f"- pending_action_id：{pending_action_id}\n"
        f"{_format_product_snapshot(product, quantity)}\n"
        "请用户确认后再调用 confirm_add_to_cart，当前尚未写入购物车。"
    )


@tool(args_schema=ConfirmAddToCartInput)
def confirm_add_to_cart(pending_action_id: str, user_id: str) -> str:
    """确认 pending action 并真正把商品写入购物车，适合在用户明确确认加购后调用。

    输入字段含义：
    - pending_action_id：prepare_add_to_cart 返回的待确认动作 ID；
    - user_id：用户 ID，必须与 pending action 所属用户一致。

    返回内容：
    - 成功时写入 cart_items，并将 pending action 状态改为 confirmed；
    - 如果动作不存在、用户不匹配、已确认、已取消或动作类型不支持，返回中文错误提示。
    """
    if _is_blank(pending_action_id):
        return "无法确认加入购物车：pending_action_id 不能为空。"
    if _is_blank(user_id):
        return "无法确认加入购物车：user_id 不能为空。"

    with _get_cart_session() as session:
        try:
            result = cart_repository.confirm_add_to_cart(
                session, pending_action_id, user_id
            )
            if result["status"] == CONFIRMED_STATUS:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise

    if result["status"] == "error":
        message = result["message"]
        if message == "pending action not found":
            return f"无法确认加入购物车：待确认动作 {pending_action_id} 不存在。"
        if message == "user mismatch":
            return "无法确认加入购物车：用户不匹配，不能确认其他用户的待处理动作。"
        if message == "pending action is not confirmable":
            return f"无法确认加入购物车：该动作当前状态为 {result['current_status']}，不能重复确认或确认已取消的动作。"
        if message == "unsupported action type":
            return f"无法确认加入购物车：不支持的动作类型 {result['action_type']}。"
        if message == "invalid pending action payload":
            return "无法确认加入购物车：待确认动作的数据格式无效。"
        if message == "product not found":
            return f"无法确认加入购物车：商品 {result['product_id']} 不存在。"
        return f"无法确认加入购物车：{message}。"

    return (
        "已确认加入购物车。\n"
        f"{_format_product_snapshot(result['product'], result['quantity'])}\n"
        f"pending_action_id：{pending_action_id}"
    )


@tool(args_schema=CancelPendingActionInput)
def cancel_pending_action(pending_action_id: str, user_id: str) -> str:
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

    with _get_cart_session() as session:
        try:
            result = cart_repository.cancel_pending_action(
                session, pending_action_id, user_id
            )
            if result["status"] == CANCELLED_STATUS:
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
        rows = cart_repository.get_cart_items(session, user_id.strip())

    if not rows:
        return f"用户 {user_id} 的购物车暂无商品。"

    lines: List[str] = [f"用户 {user_id} 的购物车："]
    total = 0.0
    for index, row in enumerate(rows, 1):
        product = row["product"]
        subtotal = row["subtotal"]
        total += subtotal
        lines.append(
            f"{index}. {product['name']}（{row['product_id']}）\n"
            f"   - 数量：{row['quantity']}\n"
            f"   - 单价：${row['unit_price']:.2f}\n"
            f"   - 小计：${subtotal:.2f}"
        )
    lines.append(f"购物车合计：${total:.2f}")
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
    "clear_cart_items",
]
