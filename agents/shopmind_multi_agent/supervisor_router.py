"""Supervisor routing adapters for the ShopMind multi-agent graph."""

from typing import Any, Protocol


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


class SupervisorRouter(Protocol):
    """Adapter interface for deterministic or future LLM-backed routing."""

    def route(self, message: str, user_id: str | None = None) -> dict[str, Any]:
        """Return a structured supervisor decision."""


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


class DeterministicSupervisorRouter:
    """Keyword-based router used as the stable default implementation."""

    def route(self, message: str, user_id: str | None = None) -> dict[str, Any]:
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
            routing_reasons["preference_agent"] = (
                "matched_preference_keywords_with_user_id"
            )

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
            "router_type": "deterministic",
        }
