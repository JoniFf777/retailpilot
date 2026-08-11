"""Closed deterministic gate between supervisor routing and recommendation flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RecommendationMode = Literal[
    "legacy_read", "structured_laptop_recommendation", "write_handoff"
]


@dataclass(frozen=True)
class RecommendationGateDecision:
    mode: RecommendationMode
    reason: str

    def model_dump(self) -> dict[str, str]:
        return {"mode": self.mode, "reason": self.reason}


_LAPTOP_TERMS = ("laptop", "notebook", "笔记本", "电脑", "电脑")
_RECOMMENDATION_TERMS = (
    "recommend", "recommendation", "推荐", "预算", "内存", "java", "开发", "剪视频", "轻",
)


def classify_recommendation_request(
    message: str,
    supervisor_decision: dict[str, object] | None = None,
) -> RecommendationGateDecision:
    """Classify only after the supervisor's write-intent guard has run."""

    decision = supervisor_decision or {}
    if decision.get("intent") == "write_path_unsupported":
        return RecommendationGateDecision("write_handoff", "supervisor_write_handoff")
    lowered = message.lower()
    is_laptop = any(term in lowered or term in message for term in _LAPTOP_TERMS)
    is_recommendation = any(term in lowered or term in message for term in _RECOMMENDATION_TERMS)
    if is_laptop and is_recommendation:
        return RecommendationGateDecision(
            "structured_laptop_recommendation", "closed_laptop_recommendation_vocabulary"
        )
    return RecommendationGateDecision("legacy_read", "outside_structured_laptop_scope")
