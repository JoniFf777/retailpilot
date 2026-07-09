"""Supervisor node for V3 read-only routing."""

from typing import Any

from .state import ShopMindMultiAgentState


SUPERVISOR_TOOLS: list[Any] = []

PRODUCT_KEYWORDS = (
    "商品",
    "推荐",
    "搜索",
    "找",
    "价格",
    "库存",
    "对比",
    "比较",
    "键盘",
    "显示器",
    "耳机",
    "电脑",
    "laptop",
    "monitor",
    "keyboard",
    "headphone",
    "product",
    "compare",
    "price",
)
RAG_KEYWORDS = (
    "政策",
    "退货",
    "退款",
    "保修",
    "配送",
    "规格",
    "兼容",
    "安装",
    "说明",
    "文档",
    "policy",
    "return",
    "warranty",
    "shipping",
    "spec",
)
PREFERENCE_KEYWORDS = (
    "偏好",
    "我的",
    "适合我",
    "个性化",
    "预算",
    "不喜欢",
    "喜欢",
    "preference",
    "personal",
    "budget",
)


def get_last_user_message(state: ShopMindMultiAgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    if isinstance(last_message, dict):
        return str(last_message.get("content") or "")
    return str(getattr(last_message, "content", last_message))


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def determine_routes(message: str, user_id: str | None = None) -> list[str]:
    routes: list[str] = []

    if _contains_any(message, PRODUCT_KEYWORDS):
        routes.append("product_agent")
    if _contains_any(message, RAG_KEYWORDS):
        routes.append("rag_agent")
    if user_id and _contains_any(message, PREFERENCE_KEYWORDS):
        routes.append("preference_agent")

    if not routes:
        routes.append("product_agent")

    return routes


def supervisor_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    message = get_last_user_message(state)
    user_id = state.get("user_id")
    routes = determine_routes(message, user_id=user_id)

    return {
        "intent": "read_path",
        "routes": routes,
        "executed_routes": [],
        "current_route": None,
        "safety_flags": list(state.get("safety_flags", [])),
        "tool_calls": list(state.get("tool_calls", [])),
    }
