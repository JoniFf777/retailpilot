"""Native V3 write handoff helpers for confirmation-based actions."""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from typing import Any, TypedDict

from app.repositories import products as product_repository
from tools.cart import prepare_add_to_cart


WRITE_HANDOFF_TOOL_CALL = "prepare_add_to_cart"
DEFAULT_CANDIDATE_CONTEXT_TTL_SECONDS = 600
MAX_CANDIDATE_CONTEXTS = 100
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
CANDIDATE_SELECTION_PATTERN = re.compile(
    r"^\s*(?:选|选择|就选|就要|要|第)\s*([1-9])\s*(?:个|号|款|项)?\s*$"
)
BARE_SELECTION_PATTERN = re.compile(r"^\s*([1-9])\s*$")
CANDIDATE_SELECTION_KEYWORDS = (
    "选",
    "选择",
    "就选",
    "就要",
    "第一个",
    "第二个",
    "第三个",
)
CATEGORY_KEYWORDS = (
    ("Keyboards", ("键盘", "keyboard", "keyboards")),
    ("Monitors", ("显示器", "monitor", "monitors")),
    ("Audio", ("耳机", "音频", "headphone", "headphones", "audio")),
    ("Laptops", ("电脑", "笔记本", "laptop", "laptops", "macbook")),
    ("Accessories", ("配件", "线缆", "支架", "扩展坞", "accessory", "accessories")),
)
QUERY_STOPWORDS = {
    "add",
    "cart",
    "to",
    "put",
    "this",
    "that",
    "my",
    "buy",
    "purchase",
    "quantity",
    "qty",
}


class CandidateContext(TypedDict):
    product_ids: list[str]
    quantity: int
    created_at: float


_CANDIDATE_CONTEXTS: dict[tuple[str, str], CandidateContext] = {}
_now = time.monotonic


@contextmanager
def _get_product_session():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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


def _candidate_context_key(
    user_id: str | None,
    thread_id: str | None,
) -> tuple[str, str] | None:
    if not user_id or not thread_id:
        return None
    return (user_id, thread_id)


def _is_candidate_context_expired(
    context: CandidateContext,
    *,
    now: float | None = None,
) -> bool:
    current_time = _now() if now is None else now
    return (
        current_time - context["created_at"]
        > DEFAULT_CANDIDATE_CONTEXT_TTL_SECONDS
    )


def prune_candidate_contexts(*, now: float | None = None) -> None:
    """Remove expired entries and keep the in-process candidate cache bounded."""

    current_time = _now() if now is None else now
    expired_keys = [
        key
        for key, context in _CANDIDATE_CONTEXTS.items()
        if _is_candidate_context_expired(context, now=current_time)
    ]
    for key in expired_keys:
        _CANDIDATE_CONTEXTS.pop(key, None)

    overflow_count = len(_CANDIDATE_CONTEXTS) - MAX_CANDIDATE_CONTEXTS
    if overflow_count <= 0:
        return

    oldest_keys = sorted(
        _CANDIDATE_CONTEXTS,
        key=lambda key: _CANDIDATE_CONTEXTS[key]["created_at"],
    )[:overflow_count]
    for key in oldest_keys:
        _CANDIDATE_CONTEXTS.pop(key, None)


def store_candidate_context(
    *,
    user_id: str | None,
    thread_id: str | None,
    candidates: list[dict[str, Any]],
    quantity: int,
) -> None:
    """Store a short-lived in-process candidate list for same-thread selection."""

    key = _candidate_context_key(user_id, thread_id)
    if key is None or not candidates:
        return

    prune_candidate_contexts()
    _CANDIDATE_CONTEXTS[key] = {
        "product_ids": [str(product["product_id"]) for product in candidates],
        "quantity": quantity,
        "created_at": _now(),
    }
    prune_candidate_contexts()


def get_candidate_context(
    user_id: str | None,
    thread_id: str | None,
) -> CandidateContext | None:
    key = _candidate_context_key(user_id, thread_id)
    if key is None:
        return None

    context = _CANDIDATE_CONTEXTS.get(key)
    if context is None:
        return None
    if _is_candidate_context_expired(context):
        _CANDIDATE_CONTEXTS.pop(key, None)
        return None
    return context


def clear_candidate_context(user_id: str | None, thread_id: str | None) -> None:
    key = _candidate_context_key(user_id, thread_id)
    if key:
        _CANDIDATE_CONTEXTS.pop(key, None)


def extract_candidate_selection(message: str) -> int | None:
    """Extract a 1-based candidate selection index from a short follow-up."""

    match = CANDIDATE_SELECTION_PATTERN.fullmatch(message)
    if match:
        return int(match.group(1))

    match = BARE_SELECTION_PATTERN.fullmatch(message)
    if match:
        return int(match.group(1))

    for index, text in enumerate(("第一个", "第二个", "第三个"), 1):
        if text in message:
            return index
    return None


def is_candidate_selection_message(message: str) -> bool:
    """Return True for short messages that likely choose a prior candidate."""

    stripped = message.strip()
    if extract_candidate_selection(stripped) is not None:
        return True
    return any(keyword == stripped for keyword in CANDIDATE_SELECTION_KEYWORDS)


def resolve_candidate_selection(
    message: str,
    user_id: str | None,
    thread_id: str | None,
) -> tuple[str, int] | None:
    selection = extract_candidate_selection(message)
    context = get_candidate_context(user_id, thread_id)
    if selection is None or context is None:
        return None

    product_ids = context["product_ids"]
    if selection < 1 or selection > len(product_ids):
        return None

    quantity = extract_quantity(message)
    if quantity == 1:
        quantity = context["quantity"]
    return product_ids[selection - 1], quantity


def infer_product_category(message: str) -> str | None:
    """Infer a catalog category from common Chinese/English product words."""

    lowered = message.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return category
    return None


def extract_product_query(message: str) -> str | None:
    """Extract a conservative English product keyword for catalog lookup."""

    tokens = [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", message)
        if token.lower() not in QUERY_STOPWORDS
        and not PRODUCT_ID_PATTERN.fullmatch(token)
    ]
    return " ".join(tokens[:3]) if tokens else None


def find_product_candidates(message: str, limit: int = 3) -> list[dict[str, Any]]:
    """Find read-only product candidates for ambiguous write handoff requests."""

    category = infer_product_category(message)
    query = None if category else extract_product_query(message)
    if not category and not query:
        return []

    with _get_product_session() as session:
        return product_repository.search_products(
            session,
            query=query,
            category=category,
            in_stock_only=True,
            limit=limit,
        )


def _format_candidate_line(product: dict[str, Any], index: int) -> str:
    return (
        f"{index}. {product['name']}（{product['product_id']}）"
        f" - ${product['price']:.2f}"
    )


def _format_product_id_clarification(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return (
            "我可以帮你创建待确认加购动作，但需要明确商品 ID，"
            "例如 TECH-KEY-001。"
        )

    lines = [
        _format_candidate_line(product, index)
        for index, product in enumerate(candidates, 1)
    ]
    return (
        "我还不能确定要加入购物车的具体商品。请回复要加购的商品 ID，"
        "可从这些候选中选择：\n"
        + "\n".join(lines)
    )


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

    selected_candidate = resolve_candidate_selection(message, user_id, thread_id)
    product_id = extract_product_id(message)
    quantity = extract_quantity(message)
    if selected_candidate:
        product_id, quantity = selected_candidate

    if product_id is None:
        candidates = find_product_candidates(message)
        store_candidate_context(
            user_id=user_id,
            thread_id=thread_id,
            candidates=candidates,
            quantity=quantity,
        )
        return {
            "answer": _format_product_id_clarification(candidates),
            "status": "completed",
            "tool_calls": [],
        }

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

    clear_candidate_context(user_id, thread_id)
    return {
        "answer": (
            f"我已为商品 {product_id} 生成待确认加购，数量 {quantity}，"
            "请确认是否加入购物车。"
        ),
        "status": "confirmation_required",
        "tool_calls": [WRITE_HANDOFF_TOOL_CALL],
        "pending_action_id": pending_action_id,
    }
