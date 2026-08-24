"""Closed write-safe gate backed by the trusted category registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.recommendation.categories import CategoryRegistry, default_category_registry
from app.recommendation.categories.models import StructuredRecommendationExtraction
from app.recommendation.request import infer_explicit_category_token


RecommendationMode = Literal[
    "legacy_read",
    "structured_recommendation",
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


_RECOMMENDATION_TERMS = (
    "recommend",
    "recommendation",
    "推荐",
    "预算",
    "想买",
    "需要",
    "求购",
)


def _is_recommendation(message: str) -> bool:
    lowered = message.casefold()
    return any(term.casefold() in lowered or term in message for term in _RECOMMENDATION_TERMS)


def classify_recommendation_request(
    message: str,
    supervisor_decision: dict[str, object] | None = None,
    *,
    registry: CategoryRegistry | None = None,
    structured_extraction: StructuredRecommendationExtraction | None = None,
) -> RecommendationGateDecision:
    """Resolve only a validated canonical category; never choose a fallback."""

    decision = supervisor_decision or {}
    if decision.get("intent") == "write_path_unsupported":
        return RecommendationGateDecision("write_handoff", "supervisor_write_handoff")
    legacy_read_route = decision.get("intent") == "read_path" and bool(decision.get("routes"))
    if not _is_recommendation(message):
        return RecommendationGateDecision("legacy_read", "outside_structured_recommendation_scope")
    active_registry = registry or default_category_registry()
    if structured_extraction is not None:
        resolved = {
            active_registry.resolve_code_or_alias(candidate.code) or candidate.code
            for candidate in structured_extraction.category_candidates
            if candidate.confidence > 0
        }
        if len(resolved) > 1 or not resolved:
            return RecommendationGateDecision(
                "recommendation_clarification",
                "structured_category_ambiguous",
                code="category_ambiguous",
            )
        category = next(iter(resolved))
        if active_registry.resolve_code_or_alias(category) is None:
            return RecommendationGateDecision(
                "unsupported_category",
                "structured_category_not_registered",
                code="unsupported_category",
            )
        return RecommendationGateDecision(
            "structured_recommendation",
            "structured_category_resolved",
            category=category,
        )
    candidates = set(active_registry.match_message(message))
    candidates.update(active_registry.match_attribute_categories(message))
    token = infer_explicit_category_token(message)
    if token:
        resolved = active_registry.resolve_code_or_alias(token)
        if resolved:
            candidates.add(resolved)
        elif not legacy_read_route:
            return RecommendationGateDecision(
                "unsupported_category",
                "explicit_category_not_registered",
                code="unsupported_category",
            )
    if len(candidates) > 1:
        return RecommendationGateDecision(
            "recommendation_clarification",
            "conflicting_category_signals",
            code="category_ambiguous",
        )
    if len(candidates) == 1:
        category = sorted(candidates)[0]
        return RecommendationGateDecision(
            "structured_recommendation",
            "registry_category_resolved",
            category=category,
        )
    if not legacy_read_route:
        return RecommendationGateDecision(
            "recommendation_clarification",
            "category_not_resolved",
            code="category_ambiguous",
        )
    return RecommendationGateDecision("legacy_read", "read_route_outside_structured_recommendation")
