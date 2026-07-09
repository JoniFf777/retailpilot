"""Supervisor routing adapters for the ShopMind multi-agent graph."""

from collections.abc import Callable
from typing import Literal, NotRequired, Protocol, TypedDict, cast


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
ReadRoute = Literal["product_agent", "rag_agent", "preference_agent"]
Confidence = Literal["low", "medium", "high"]
SupervisorIntent = Literal["read_path"]


class LLMSupervisorRouterInput(TypedDict):
    """Payload passed to a structured LLM router provider."""

    message: str
    user_id: str | None
    allowed_routes: list[ReadRoute]


class LLMSupervisorRouterOutput(TypedDict, total=False):
    """Structured decision returned by an LLM router provider."""

    routes: list[ReadRoute]
    routing_reasons: dict[str, str]
    confidence: Confidence
    requires_user_id_for_preferences: bool


class SupervisorRouteDecision(TypedDict):
    """Normalized supervisor decision consumed by the graph."""

    intent: SupervisorIntent
    routes: list[ReadRoute]
    routing_reasons: dict[str, str]
    confidence: Confidence
    fallback_used: bool
    requires_user_id_for_preferences: bool
    router_type: str
    fallback_reason: NotRequired[str]


ALLOWED_READ_ROUTES: set[ReadRoute] = {
    "product_agent",
    "rag_agent",
    "preference_agent",
}
SORTED_ALLOWED_READ_ROUTES: list[ReadRoute] = [
    "preference_agent",
    "product_agent",
    "rag_agent",
]


DecisionProvider = Callable[[LLMSupervisorRouterInput], LLMSupervisorRouterOutput]


class SupervisorRouter(Protocol):
    """Adapter interface for deterministic or future LLM-backed routing."""

    def route(
        self,
        message: str,
        user_id: str | None = None,
    ) -> SupervisorRouteDecision:
        """Return a structured supervisor decision."""


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


class DeterministicSupervisorRouter:
    """Keyword-based router used as the stable default implementation."""

    def route(
        self,
        message: str,
        user_id: str | None = None,
    ) -> SupervisorRouteDecision:
        routes: list[ReadRoute] = []
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


class LLMSupervisorRouter:
    """Structured-output router shell with deterministic fallback.

    The provider is intentionally a callable for now so tests can exercise the
    contract without invoking a real model. A future implementation can pass a
    LangChain structured-output model here.
    """

    def __init__(
        self,
        decision_provider: DecisionProvider | None = None,
        fallback_router: SupervisorRouter | None = None,
    ) -> None:
        self.decision_provider = decision_provider
        self.fallback_router = fallback_router or DeterministicSupervisorRouter()

    def route(
        self,
        message: str,
        user_id: str | None = None,
    ) -> SupervisorRouteDecision:
        if self.decision_provider is None:
            return self._fallback(message, user_id, reason="provider_not_configured")

        try:
            payload: LLMSupervisorRouterInput = {
                "message": message,
                "user_id": user_id,
                "allowed_routes": SORTED_ALLOWED_READ_ROUTES,
            }
            decision = self.decision_provider(payload)
            return self._normalize_decision(decision, message, user_id)
        except Exception:
            return self._fallback(message, user_id, reason="provider_error")

    def _fallback(
        self,
        message: str,
        user_id: str | None,
        *,
        reason: str,
    ) -> SupervisorRouteDecision:
        decision = dict(self.fallback_router.route(message, user_id=user_id))
        decision["router_type"] = "llm_fallback"
        decision["fallback_reason"] = reason
        return cast(SupervisorRouteDecision, decision)

    def _normalize_decision(
        self,
        decision: LLMSupervisorRouterOutput,
        message: str,
        user_id: str | None,
    ) -> SupervisorRouteDecision:
        routes = list(decision.get("routes") or [])
        if not routes or any(route not in ALLOWED_READ_ROUTES for route in routes):
            return self._fallback(message, user_id, reason="invalid_routes")

        routing_reasons = dict(decision.get("routing_reasons") or {})
        for route in routes:
            routing_reasons.setdefault(route, "llm_selected_route")

        confidence = str(decision.get("confidence") or "medium")
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        normalized_confidence = cast(Confidence, confidence)

        return {
            "intent": "read_path",
            "routes": routes,
            "routing_reasons": routing_reasons,
            "confidence": normalized_confidence,
            "fallback_used": False,
            "requires_user_id_for_preferences": bool(
                decision.get("requires_user_id_for_preferences", False)
            ),
            "router_type": "llm",
        }


def create_supervisor_router(router_mode: str | None = None) -> SupervisorRouter:
    normalized = (router_mode or "deterministic").strip().lower()
    if normalized == "llm":
        return LLMSupervisorRouter()
    return DeterministicSupervisorRouter()
