"""ShopMind V1 cart and pending action tools.

This module implements a simple confirmation-first cart flow on top of the
existing TechHub SQLite database. It intentionally does not use LangGraph
interrupt/resume yet; pending actions are stored explicitly and can later be
connected to API confirmation endpoints.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import DEFAULT_DB_PATH


PENDING_STATUS = "pending"
CONFIRMED_STATUS = "confirmed"
CANCELLED_STATUS = "cancelled"
ADD_TO_CART_ACTION = "add_to_cart"


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


def ensure_cart_tables() -> None:
    """Ensure cart_items and pending_actions tables exist in the SQLite database."""
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_actions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                thread_id TEXT,
                action_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'cancelled')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_blank(value: Optional[str]) -> bool:
    return value is None or not value.strip()


def _get_product(product_id: str) -> Optional[ProductRow]:
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT product_id, name, category, price, in_stock
            FROM products
            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()

    return dict(row) if row else None


def _get_pending_action(pending_action_id: str) -> Optional[PendingActionRow]:
    ensure_cart_tables()
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT id, user_id, thread_id, action_type, payload_json, status, created_at, updated_at
            FROM pending_actions
            WHERE id = ?
            """,
            (pending_action_id,),
        ).fetchone()

    return dict(row) if row else None


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
    ensure_cart_tables()

    if _is_blank(user_id):
        return "无法准备加入购物车：user_id 不能为空。"
    if _is_blank(product_id):
        return "无法准备加入购物车：product_id 不能为空。"
    if quantity <= 0:
        return "无法准备加入购物车：quantity 必须大于 0。"

    product = _get_product(product_id.strip())
    if not product:
        return f"无法准备加入购物车：商品 {product_id} 不存在，请检查商品 ID。"

    pending_action_id = str(uuid.uuid4())
    now = _now_iso()
    payload = {"product_id": product["product_id"], "quantity": quantity}

    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO pending_actions (
                id, user_id, thread_id, action_type, payload_json, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pending_action_id,
                user_id.strip(),
                thread_id,
                ADD_TO_CART_ACTION,
                json.dumps(payload, ensure_ascii=False),
                PENDING_STATUS,
                now,
                now,
            ),
        )
        connection.commit()

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
    ensure_cart_tables()

    if _is_blank(pending_action_id):
        return "无法确认加入购物车：pending_action_id 不能为空。"
    if _is_blank(user_id):
        return "无法确认加入购物车：user_id 不能为空。"

    action = _get_pending_action(pending_action_id.strip())
    if not action:
        return f"无法确认加入购物车：待确认动作 {pending_action_id} 不存在。"
    if action["user_id"] != user_id.strip():
        return "无法确认加入购物车：用户不匹配，不能确认其他用户的待处理动作。"
    if action["status"] != PENDING_STATUS:
        return f"无法确认加入购物车：该动作当前状态为 {action['status']}，不能重复确认或确认已取消的动作。"
    if action["action_type"] != ADD_TO_CART_ACTION:
        return f"无法确认加入购物车：不支持的动作类型 {action['action_type']}。"

    try:
        payload = json.loads(action["payload_json"])
        product_id = payload["product_id"]
        quantity = int(payload["quantity"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return "无法确认加入购物车：待确认动作的数据格式无效。"

    product = _get_product(product_id)
    if not product:
        return f"无法确认加入购物车：商品 {product_id} 不存在。"

    now = _now_iso()
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO cart_items (user_id, product_id, quantity, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id.strip(), product_id, quantity, now, now),
        )
        connection.execute(
            """
            UPDATE pending_actions
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (CONFIRMED_STATUS, now, pending_action_id.strip()),
        )
        connection.commit()

    return (
        "已确认加入购物车。\n"
        f"{_format_product_snapshot(product, quantity)}\n"
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
    ensure_cart_tables()

    if _is_blank(pending_action_id):
        return "无法取消待确认动作：pending_action_id 不能为空。"
    if _is_blank(user_id):
        return "无法取消待确认动作：user_id 不能为空。"

    action = _get_pending_action(pending_action_id.strip())
    if not action:
        return f"无法取消待确认动作：动作 {pending_action_id} 不存在。"
    if action["user_id"] != user_id.strip():
        return "无法取消待确认动作：用户不匹配，不能取消其他用户的待处理动作。"
    if action["status"] != PENDING_STATUS:
        return f"无法取消待确认动作：该动作当前状态为 {action['status']}，不能取消。"

    now = _now_iso()
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.execute(
            """
            UPDATE pending_actions
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (CANCELLED_STATUS, now, pending_action_id.strip()),
        )
        connection.commit()

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
    ensure_cart_tables()

    if _is_blank(user_id):
        return "无法读取购物车：user_id 不能为空。"

    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                c.product_id,
                p.name,
                c.quantity,
                p.price
            FROM cart_items c
            JOIN products p ON p.product_id = c.product_id
            WHERE c.user_id = ?
            ORDER BY c.id ASC
            """,
            (user_id.strip(),),
        ).fetchall()

    if not rows:
        return f"用户 {user_id} 的购物车暂无商品。"

    lines: List[str] = [f"用户 {user_id} 的购物车："]
    total = 0.0
    for index, row in enumerate(rows, 1):
        subtotal = row["price"] * row["quantity"]
        total += subtotal
        lines.append(
            f"{index}. {row['name']}（{row['product_id']}）\n"
            f"   - 数量：{row['quantity']}\n"
            f"   - 单价：${row['price']:.2f}\n"
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
    ensure_cart_tables()

    if _is_blank(user_id):
        return "无法清理购物车：user_id 不能为空。"

    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        cart_cursor = connection.execute(
            "DELETE FROM cart_items WHERE user_id = ?",
            (user_id.strip(),),
        )
        action_cursor = connection.execute(
            "DELETE FROM pending_actions WHERE user_id = ?",
            (user_id.strip(),),
        )
        connection.commit()

    return (
        f"已清理用户 {user_id} 的测试数据："
        f"删除购物车记录 {cart_cursor.rowcount} 条，"
        f"删除待确认动作 {action_cursor.rowcount} 条。"
    )


__all__ = [
    "ensure_cart_tables",
    "prepare_add_to_cart",
    "confirm_add_to_cart",
    "cancel_pending_action",
    "get_cart_items",
    "clear_cart_items",
]
