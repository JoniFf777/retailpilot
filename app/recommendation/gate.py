"""Closed deterministic gate between supervisor routing and recommendation flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RecommendationMode = Literal[
    "legacy_read",
    "structured_laptop_recommendation",
    "structured_monitor_recommendation",
    "recommendation_clarification",
    "unsupported_category",
    "write_handoff",
]


@dataclass(frozen=True)
class RecommendationGateDecision:
    mode: RecommendationMode
    reason: str
    category: str | None = None
    code: str | None = None

    def model_dump(self) -> dict[str, str | None]:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "category": self.category,
            "code": self.code,
        }


_LAPTOP_TERMS = ("laptop", "notebook", "笔记本", "电脑", "电脑")
_RECOMMENDATION_TERMS = (
    "recommend", "recommendation", "推荐", "预算", "内存", "java", "开发", "剪视频", "轻",
)
_STRUCTURED_LAPTOP_HINTS = ("预算", "内存", "java", "开发", "剪视频", "轻")
_MONITOR_TERMS = ("monitor", "display", "显示器", "电竞屏", "曲面屏")
_UNSUPPORTED_CATEGORY_TERMS = (
    "phone", "smartphone", "手机", "tablet", "平板", "headphone", "耳机",
    "keyboard", "键盘", "accessory", "配件", "audio", "音箱",
)


def classify_recommendation_request(
    message: str,
    supervisor_decision: dict[str, object] | None = None,
) -> RecommendationGateDecision:
    """Classify only after the supervisor's write-intent guard has run."""

    decision = supervisor_decision or {}
    if decision.get("intent") == "write_path_unsupported":
        return RecommendationGateDecision("write_handoff", "supervisor_write_handoff")
    legacy_read_route = decision.get("intent") == "read_path" and bool(
        decision.get("routes")
    )
    lowered = message.lower()
    is_laptop = any(term in lowered or term in message for term in _LAPTOP_TERMS)
    is_monitor = any(term in lowered or term in message for term in _MONITOR_TERMS)
    unsupported = any(
        term in lowered or term in message for term in _UNSUPPORTED_CATEGORY_TERMS
    )
    structured_hint_count = sum(
        term in lowered or term in message for term in _STRUCTURED_LAPTOP_HINTS
    )
    # Users often omit the product noun when they provide a complete laptop
    # brief, e.g. "预算 6000、Java、16GB、尽量轻". Treat that closed set of
    # constraints as a laptop recommendation request as well.
    is_laptop = is_laptop or (
        structured_hint_count >= 3
        and ("预算" in message or "内存" in message)
    )
    is_recommendation = any(term in lowered or term in message for term in _RECOMMENDATION_TERMS)
    if is_laptop and is_monitor and is_recommendation:
        return RecommendationGateDecision(
            "recommendation_clarification",
            "conflicting_category_signals",
            code="category_ambiguous",
        )
    if is_monitor and is_recommendation:
        return RecommendationGateDecision(
            "structured_monitor_recommendation",
            "closed_monitor_recommendation_vocabulary",
            category="monitor",
        )
    if is_laptop and is_recommendation:
        return RecommendationGateDecision(
            "structured_laptop_recommendation",
            "closed_laptop_recommendation_vocabulary",
            category="laptop",
        )
    if unsupported and is_recommendation and not legacy_read_route:
        return RecommendationGateDecision(
            "unsupported_category",
            "category_policy_not_registered",
            code="unsupported_category",
        )
    if (
        is_recommendation
        and not legacy_read_route
        and any(term in message for term in ("商品", "设备", "东西"))
    ):
        return RecommendationGateDecision(
            "recommendation_clarification",
            "category_not_resolved",
            code="category_ambiguous",
        )
    return RecommendationGateDecision("legacy_read", "outside_structured_laptop_scope")
