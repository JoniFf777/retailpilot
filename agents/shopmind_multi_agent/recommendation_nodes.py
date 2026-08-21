"""Deterministic Phase 1B nodes; they do not add a new autonomous Agent."""

from __future__ import annotations

from typing import Any

from app.recommendation.gate import classify_recommendation_request
from app.recommendation.providers import CatalogCandidateProvider, RecommendationPreferenceProvider
from app.recommendation.rag import (
    RecommendationEvidence,
    RecommendationEvidenceProvider,
    attach_validated_evidence,
)
from app.recommendation.request import parse_recommendation_request
from app.recommendation.service import (
    MONITOR_RANKING_POLICY_VERSION,
    RANKING_POLICY_VERSION,
    build_recommendation,
)
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import LaptopConstraints, RecommendationResult

from .observability import append_agent_step
from .state import ShopMindMultiAgentState
from .supervisor import get_last_user_message


def recommendation_gate_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    decision = classify_recommendation_request(
        get_last_user_message(state), state.get("supervisor_decision")
    )
    output: dict[str, Any] = {"recommendation_gate": decision.model_dump()}
    # Preserve the historical V3 legacy/write trajectory exactly.  The gate is
    # observable as a graph step only when it claims the new structured path.
    if decision.mode not in {"legacy_read", "write_handoff"}:
        output["agent_steps"] = append_agent_step(
            state,
            node="recommendation_gate",
            event="classified",
            mode=decision.mode,
            reason=decision.reason,
        )
    return output


def next_after_recommendation_gate(state: ShopMindMultiAgentState) -> str:
    mode = (state.get("recommendation_gate") or {}).get("mode")
    if mode in {"structured_laptop_recommendation", "structured_monitor_recommendation"}:
        return "catalog_candidates"
    if mode in {"recommendation_clarification", "unsupported_category"}:
        return "recommendation_resolution"
    return "legacy_execution"


def next_graph_path_after_recommendation_gate(state: ShopMindMultiAgentState) -> str:
    """Resolve the legacy planner path only when the gate did not claim the run."""

    mode = next_after_recommendation_gate(state)
    if mode in {"catalog_candidates", "recommendation_resolution"}:
        return mode
    from .graph import next_execution_path

    return next_execution_path(state)


def catalog_candidates_node(
    state: ShopMindMultiAgentState,
    *,
    provider: CatalogCandidateProvider,
) -> dict[str, Any]:
    category = str((state.get("recommendation_gate") or {}).get("category") or "laptop")
    if hasattr(provider, "list_active_skus"):
        candidates = provider.list_active_skus(category)
    else:
        candidates = provider.list_active_laptop_skus()
    return {
        "catalog_candidates": [item.model_dump(mode="json") for item in candidates],
        "agent_steps": append_agent_step(
            state,
            node="catalog_candidates",
            event="retrieved",
            candidate_count=len(candidates),
        ),
    }


def recommendation_preference_node(
    state: ShopMindMultiAgentState,
    *,
    provider: RecommendationPreferenceProvider,
) -> dict[str, Any]:
    """Keep existing preference read output informational and out of ranking."""

    summary = provider.summary_for_user(state.get("user_id"))
    return {
        "preference_summary": summary,
        "recommendation_diagnostics": {
            **(state.get("recommendation_diagnostics") or {}),
            "preference_summary_present": bool(summary),
            "preference_used_for_ranking": False,
        },
        "agent_steps": append_agent_step(
            state,
            node="recommendation_preference",
            event="informational_only",
            preference_summary_present=bool(summary),
        ),
    }


def _clarification(message: str, category: str) -> RecommendationResult:
    request = parse_recommendation_request(message, category)
    return RecommendationResult(
        category=category if category in {"laptop", "monitor"} else "unknown",
        outcome="clarification_required",
        ranking_policy_version=(
            MONITOR_RANKING_POLICY_VERSION
            if category == "monitor"
            else RANKING_POLICY_VERSION
        ),
        request_summary=message,
        structured_constraints=LaptopConstraints(),
        recommendation_request=request,
        category_attributes=request.category_attributes,
        missing_fields=(
            ["budget_or_monitor_attribute"]
            if category == "monitor"
            else ["budget_max_or_primary_use_case"]
        ),
        clarification_question=(
            "请补充显示器预算、尺寸、分辨率或刷新率要求。"
            if category == "monitor"
            else "请补充预算、主要用途或至少一项明确的性能需求。"
        ),
    )


def deterministic_ranking_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    message = get_last_user_message(state)
    gate = state.get("recommendation_gate") or {}
    category = str(gate.get("category") or "laptop")
    request = parse_recommendation_request(message, category)
    candidates = [
        CatalogSkuCandidate.model_validate(item)
        for item in state.get("catalog_candidates", [])
    ]
    has_usable_constraint = bool(request.budget_max or request.generic_preferences) or any(
        value not in (None, "", []) for value in request.category_attributes.values()
    )
    result = build_recommendation(candidates, request, request_summary=message) if has_usable_constraint else _clarification(message, category)
    return {
        "structured_constraints": result.structured_constraints.model_dump(mode="json"),
        "recommendation_result": result.model_dump(mode="json"),
        "recommendation_diagnostics": {
            **(state.get("recommendation_diagnostics") or {}),
            "candidate_count_before_hard_filter": len(candidates),
            "top_k_sku_codes": [
                candidate.sku_code
                for candidate in candidates
                if any(candidate.sku_id == item.sku_id for item in result.recommendations)
            ],
            "category": category,
        },
        "agent_steps": append_agent_step(
            state,
            node="deterministic_ranking",
            event="ranked",
            outcome=result.outcome,
            recommendation_count=len(result.recommendations),
        ),
    }


def recommendation_evidence_node(
    state: ShopMindMultiAgentState,
    *,
    provider: RecommendationEvidenceProvider,
) -> dict[str, Any]:
    result = RecommendationResult.model_validate(state.get("recommendation_result") or {})
    candidates = [
        CatalogSkuCandidate.model_validate(item)
        for item in state.get("catalog_candidates", [])
    ]
    candidates_by_id = {candidate.sku_id: candidate for candidate in candidates}
    top_k = [
        candidates_by_id[item.sku_id]
        for item in result.recommendations
        if item.sku_id in candidates_by_id
    ]
    diagnostics = dict(state.get("recommendation_diagnostics") or {})
    if not top_k:
        return {
            "recommendation": result.model_dump(mode="json"),
            "recommendation_diagnostics": {**diagnostics, "evidence_skipped": "no_top_k"},
            "top_k_product_evidence": {},
            "policy_evidence": [],
        }
    try:
        evidence = provider.retrieve(message=get_last_user_message(state), top_k=top_k)
    except Exception:
        # Evidence is enrichment after deterministic catalog ranking. A local
        # embedding/document failure must not discard an otherwise valid
        # recommendation or leave the SSE client without run.result.
        evidence = RecommendationEvidence(
            product_evidence={candidate.sku_code: [] for candidate in top_k},
            policy_evidence=[],
            diagnostics={"evidence_unavailable": True},
        )
    validated = attach_validated_evidence(
        result,
        evidence,
        sku_codes_by_id={candidate.sku_id: candidate.sku_code for candidate in top_k},
    )
    return {
        "recommendation": RecommendationResult.model_validate(validated).model_dump(mode="json"),
        "recommendation_diagnostics": {**diagnostics, **evidence.diagnostics},
        "top_k_product_evidence": {
            sku_code: [item.model_dump(mode="json") for item in items]
            for sku_code, items in evidence.product_evidence.items()
        },
        "policy_evidence": [item.model_dump(mode="json") for item in evidence.policy_evidence],
        "agent_steps": append_agent_step(
            state,
            node="recommendation_evidence",
            event="validated",
            top_k_count=len(top_k),
            product_evidence_sku_count=len(evidence.product_evidence),
            policy_evidence_count=len(evidence.policy_evidence),
        ),
    }


def recommendation_decision_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    """Explain the already-fixed result; this node cannot introduce products."""

    recommendation = RecommendationResult.model_validate(
        state.get("recommendation") or state.get("recommendation_result") or {}
    )
    if recommendation.outcome == "recommended":
        names = "、".join(item.product_name for item in recommendation.recommendations)
        answer = f"已按你的硬约束筛选并排序：{names}。"
        if state.get("policy_evidence"):
            answer += "已结合已验证的通用政策资料说明。"
    elif recommendation.outcome == "no_match":
        answer = recommendation.no_match_reason or "没有满足硬约束的商品。"
    else:
        answer = recommendation.clarification_question or "请补充推荐条件。"
    category = str((state.get("recommendation_gate") or {}).get("category") or recommendation.category)
    return {
        "recommendation": recommendation.model_dump(mode="json"),
        "final_response": answer,
        "decision": {
            "status": "completed",
            "answer_type": f"structured_{category}_recommendation",
            "used_routes": ["catalog_candidates", "deterministic_ranking", "recommendation_evidence"],
            "recommendation_outcome": recommendation.outcome,
            "recommendation_count": len(recommendation.recommendations),
        },
        "agent_steps": append_agent_step(
            state,
            node="recommendation_decision",
            event="explained",
            outcome=recommendation.outcome,
            recommendation_count=len(recommendation.recommendations),
        ),
    }


def recommendation_resolution_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    """Turn ambiguous/unsupported category resolution into typed structured output."""

    gate = state.get("recommendation_gate") or {}
    code = str(gate.get("code") or "category_ambiguous")
    if code == "unsupported_category":
        question = "当前暂不支持该品类，请选择笔记本或显示器。"
    else:
        question = "你希望推荐笔记本还是显示器？"
    result = RecommendationResult(
        category="unknown",
        outcome="clarification_required",
        error_code=code,
        ranking_policy_version=RANKING_POLICY_VERSION,
        request_summary=get_last_user_message(state),
        structured_constraints=LaptopConstraints(),
        missing_fields=["category"],
        clarification_question=question,
    )
    return {
        "recommendation": result.model_dump(mode="json"),
        "final_response": question,
        "recommendation_diagnostics": {
            **(state.get("recommendation_diagnostics") or {}),
            "category_resolution": code,
        },
        "decision": {
            "status": "completed",
            "answer_type": "category_resolution",
            "recommendation_outcome": result.outcome,
            "recommendation_count": 0,
        },
    }
