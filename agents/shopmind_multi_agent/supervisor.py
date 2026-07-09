"""Supervisor node for V3 read-only routing."""

from typing import Any

from .observability import append_agent_step
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


def build_supervisor_decision(
    message: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    routes: list[str] = []
    routing_reasons: dict[str, str] = {}
    fallback_used = False

    if _contains_any(message, PRODUCT_KEYWORDS):
        routes.append("product_agent")
        routing_reasons["product_agent"] = "matched_product_keywords"
    if _contains_any(message, RAG_KEYWORDS):
        routes.append("rag_agent")
        routing_reasons["rag_agent"] = "matched_document_or_policy_keywords"
    if user_id and _contains_any(message, PREFERENCE_KEYWORDS):
        routes.append("preference_agent")
        routing_reasons["preference_agent"] = "matched_preference_keywords_with_user_id"

    if not routes:
        routes.append("product_agent")
        routing_reasons["product_agent"] = "fallback_to_product_read"
        fallback_used = True

    return {
        "intent": "read_path",
        "routes": routes,
        "routing_reasons": routing_reasons,
        "confidence": "medium" if fallback_used else "high",
        "fallback_used": fallback_used,
        "requires_user_id_for_preferences": (
            not user_id and _contains_any(message, PREFERENCE_KEYWORDS)
        ),
    }


def determine_routes(message: str, user_id: str | None = None) -> list[str]:
    return list(build_supervisor_decision(message, user_id=user_id)["routes"])


def supervisor_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    message = get_last_user_message(state)
    user_id = state.get("user_id")
    supervisor_decision = build_supervisor_decision(message, user_id=user_id)
    routes = list(supervisor_decision["routes"])

    return {
        "intent": supervisor_decision["intent"],
        "supervisor_decision": supervisor_decision,
        "routes": routes,
        "executed_routes": [],
        "current_route": None,
        "safety_flags": list(state.get("safety_flags", [])),
        "tool_calls": list(state.get("tool_calls", [])),
        "agent_steps": append_agent_step(
            state,
            node="supervisor",
            event="routed",
            routes=routes,
            intent=supervisor_decision["intent"],
            confidence=supervisor_decision["confidence"],
            fallback_used=supervisor_decision["fallback_used"],
        ),
    }
