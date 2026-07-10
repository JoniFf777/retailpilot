"""Supervisor routing adapters for the ShopMind multi-agent graph."""

from collections.abc import Callable
from typing import Any, Literal, NotRequired, Protocol, TypedDict, cast

from langchain.chat_models import init_chat_model

from config import DEFAULT_MODEL


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
WRITE_INTENT_KEYWORDS = (
    "\u52a0\u5165\u8d2d\u7269\u8f66",
    "\u52a0\u8d2d",
    "\u4e0b\u5355",
    "\u8d2d\u4e70",
    "\u4e70\u4e0b",
    "\u786e\u8ba4\u8d2d\u4e70",
    "\u786e\u8ba4\u52a0\u5165",
    "\u6e05\u7a7a\u8d2d\u7269\u8f66",
    "\u4fdd\u5b58\u504f\u597d",
    "\u8bb0\u4f4f",
    "\u4e0d\u8981\u63a8\u8350",
    "\u4ee5\u540e\u522b",
    "add to cart",
    "put it in my cart",
    "put this in my cart",
    "buy it",
    "purchase it",
    "checkout",
    "place order",
    "confirm order",
    "clear cart",
    "save preference",
    "remember that",
    "do not recommend",
    "don't recommend",
    "never recommend",
)
WRITE_INTENT_SAFETY_FLAG = "write_intent_blocked"
WRITE_INTENT_HANDOFF_REASON = "read_only_multi_agent_write_intent"
ReadRoute = Literal["product_agent", "rag_agent", "preference_agent"]
Confidence = Literal["low", "medium", "high"]
SupervisorIntent = Literal["read_path", "write_path_unsupported"]


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
    fallback_router_type: NotRequired[str]
    router_provider: NotRequired[str]
    router_model: NotRequired[str]
    safety_flags: NotRequired[list[str]]
    handoff_reason: NotRequired[str]


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
ROUTER_SYSTEM_PROMPT = """You route ShopMind read-only shopping support requests.

Choose one or more allowed routes:
- product_agent: product search, catalog facts, price, inventory, comparisons
- rag_agent: policies, returns, warranty, shipping, specs, compatibility, docs
- preference_agent: personal preferences or budget, only when user_id is present

Never choose decision_agent or write tools. Return only structured fields."""


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


def is_write_intent(message: str) -> bool:
    """Return True when a request asks the read-only graph to mutate state."""

    from .write_handoff import is_candidate_selection_message

    return (
        _contains_any(message, WRITE_INTENT_KEYWORDS)
        or is_candidate_selection_message(message)
    )


def _write_intent_decision(
    *,
    router_type: str,
    router_provider: str | None = None,
    router_model: str | None = None,
) -> SupervisorRouteDecision:
    decision: SupervisorRouteDecision = {
        "intent": "write_path_unsupported",
        "routes": [],
        "routing_reasons": {},
        "confidence": "high",
        "fallback_used": False,
        "requires_user_id_for_preferences": False,
        "router_type": router_type,
        "safety_flags": [WRITE_INTENT_SAFETY_FLAG],
        "handoff_reason": WRITE_INTENT_HANDOFF_REASON,
    }
    if router_provider:
        decision["router_provider"] = router_provider
    if router_model:
        decision["router_model"] = router_model
    return decision


def _build_langchain_router_messages(
    payload: LLMSupervisorRouterInput,
) -> list[dict[str, str]]:
    allowed_routes = ", ".join(payload["allowed_routes"])
    user_id_status = "present" if payload["user_id"] else "missing"
    return [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Message: {payload['message']}\n"
                f"User ID status: {user_id_status}\n"
                f"Allowed routes: {allowed_routes}"
            ),
        },
    ]


def _coerce_provider_output(output: object) -> LLMSupervisorRouterOutput:
    if hasattr(output, "model_dump"):
        dumped = output.model_dump(exclude_none=True)
        return cast(LLMSupervisorRouterOutput, dumped)
    if isinstance(output, dict):
        return cast(LLMSupervisorRouterOutput, output)
    return {}


def _describe_model(model: Any | None) -> str:
    configured_model = model or DEFAULT_MODEL
    if isinstance(configured_model, str):
        return configured_model
    return configured_model.__class__.__name__


def create_langchain_supervisor_decision_provider(
    model: Any | None = None,
) -> DecisionProvider:
    """Create a lazy LangChain structured-output provider for LLM routing."""

    configured_model = model or DEFAULT_MODEL
    structured_router: Any | None = None

    def provider(payload: LLMSupervisorRouterInput) -> LLMSupervisorRouterOutput:
        nonlocal structured_router
        if structured_router is None:
            llm = (
                init_chat_model(configured_model, configurable_fields=["model"])
                if isinstance(configured_model, str)
                else configured_model
            )
            structured_router = llm.with_structured_output(LLMSupervisorRouterOutput)

        output = structured_router.invoke(_build_langchain_router_messages(payload))
        return _coerce_provider_output(output)

    return provider


class DeterministicSupervisorRouter:
    """Keyword-based router used as the stable default implementation."""

    def route(
        self,
        message: str,
        user_id: str | None = None,
    ) -> SupervisorRouteDecision:
        if is_write_intent(message):
            return _write_intent_decision(router_type="deterministic")

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
    """Structured-output router with deterministic fallback."""

    def __init__(
        self,
        decision_provider: DecisionProvider | None = None,
        fallback_router: SupervisorRouter | None = None,
        provider_type: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.decision_provider = decision_provider
        self.fallback_router = fallback_router or DeterministicSupervisorRouter()
        self.router_provider = provider_type or (
            "callable" if decision_provider is not None else None
        )
        self.router_model = model_name

    def route(
        self,
        message: str,
        user_id: str | None = None,
    ) -> SupervisorRouteDecision:
        if is_write_intent(message):
            return _write_intent_decision(
                router_type="llm_guardrail",
                router_provider=self.router_provider,
                router_model=self.router_model,
            )

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
        fallback_router_type = decision.get("router_type")
        decision["router_type"] = "llm_fallback"
        decision["fallback_reason"] = reason
        if fallback_router_type:
            decision["fallback_router_type"] = str(fallback_router_type)
        if self.router_provider:
            decision["router_provider"] = self.router_provider
        if self.router_model:
            decision["router_model"] = self.router_model
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

        normalized_decision: SupervisorRouteDecision = {
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
        if self.router_provider:
            normalized_decision["router_provider"] = self.router_provider
        if self.router_model:
            normalized_decision["router_model"] = self.router_model
        return normalized_decision


def create_supervisor_router(
    router_mode: str | None = None,
    *,
    model: Any | None = None,
    decision_provider: DecisionProvider | None = None,
) -> SupervisorRouter:
    normalized = (router_mode or "deterministic").strip().lower()
    if normalized == "llm":
        return LLMSupervisorRouter(
            decision_provider=decision_provider
            or create_langchain_supervisor_decision_provider(model=model),
            provider_type=(
                "custom_callable"
                if decision_provider is not None
                else "langchain_structured_output"
            ),
            model_name=None if decision_provider is not None else _describe_model(model),
        )
    return DeterministicSupervisorRouter()
