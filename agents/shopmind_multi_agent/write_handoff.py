"""Native V3 write handoff helpers for confirmation-based actions."""

from __future__ import annotations

import re
from typing import Any

from tools.cart import prepare_add_to_cart


WRITE_HANDOFF_TOOL_CALL = "prepare_add_to_cart"
PRODUCT_ID_PATTERN = re.compile(r"\bTECH-[A-Z]{3}-\d{3}\b", re.IGNORECASE)
PENDING_ACTION_PATTERN = re.compile(r"pending_action_id[：:]\s*([0-9a-fA-F-]+)")
ARABIC_QUANTITY_PATTERNS = (
    re.compile(r"(?:数量|qty|quantity)\s*[：:]?\s*(\d+)", re.IGNORECASE),
    re.compile(r"[xX]\s*(\d+)"),
    re.compile(r"(\d+)\s*(?:个|件|台|把|pcs?|pieces?)", re.IGNORECASE),
)
CHINESE_QUANTITY_PATTERN = re.compile(r"([一二两三四五六七八九十])\s*(?:个|件|台|把)")
CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def extract_product_id(message: str) -> str | None:
    """Extract the first explicit ShopMind product ID from a user message."""

    match = PRODUCT_ID_PATTERN.search(message)
    return match.group(0).upper() if match else None


def extract_quantity(message: str) -> int:
    """Extract a simple explicit quantity, defaulting to one item."""

    for pattern in ARABIC_QUANTITY_PATTERNS:
        match = pattern.search(message)
        if match:
            quantity = int(match.group(1))
            if quantity > 0:
                return quantity

    match = CHINESE_QUANTITY_PATTERN.search(message)
    if match:
        return CHINESE_DIGITS[match.group(1)]

    return 1


def extract_pending_action_id(tool_result: str) -> str | None:
    """Extract a pending action ID from the prepare_add_to_cart tool output."""

    match = PENDING_ACTION_PATTERN.search(tool_result)
    return match.group(1) if match else None


def invoke_write_handoff(
    message: str,
    user_id: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Prepare a confirmation-required write action for explicit V3 requests."""

    if not user_id:
        return {
            "answer": "需要先提供 user_id，才能为你创建待确认的加购动作。",
            "status": "completed",
            "tool_calls": [],
        }

    product_id = extract_product_id(message)
    if product_id is None:
        return {
            "answer": (
                "我可以帮你创建待确认加购动作，但需要明确商品 ID，"
                "例如 TECH-KEY-001。"
            ),
            "status": "completed",
            "tool_calls": [],
        }

    quantity = extract_quantity(message)
    tool_result = prepare_add_to_cart.invoke(
        {
            "user_id": user_id,
            "product_id": product_id,
            "quantity": quantity,
            "thread_id": thread_id,
        }
    )
    pending_action_id = extract_pending_action_id(tool_result)
    if not pending_action_id:
        return {
            "answer": tool_result,
            "status": "failed",
            "tool_calls": [WRITE_HANDOFF_TOOL_CALL],
        }

    return {
        "answer": (
            f"我已为商品 {product_id} 生成待确认加购，数量 {quantity}，"
            "请确认是否加入购物车。"
        ),
        "status": "confirmation_required",
        "tool_calls": [WRITE_HANDOFF_TOOL_CALL],
        "pending_action_id": pending_action_id,
    }
