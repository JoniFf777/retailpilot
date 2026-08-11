"""Deterministic Phase 1B nodes; they do not add a new autonomous Agent."""

from __future__ import annotations

from typing import Any

from app.recommendation.constraints import parse_laptop_constraints
from app.recommendation.gate import classify_recommendation_request
from app.recommendation.providers import CatalogCandidateProvider, RecommendationPreferenceProvider
from app.recommendation.rag import (
    RecommendationEvidenceProvider,
    attach_validated_evidence,
)
from app.recommendation.service import RANKING_POLICY_VERSION, build_laptop_recommendation
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import RecommendationResult

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
    if decision.mode == "structured_laptop_recommendation":
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
    if mode == "structured_laptop_recommendation":
        return "catalog_candidates"
    return "legacy_execution"


def next_graph_path_after_recommendation_gate(state: ShopMindMultiAgentState) -> str:
    """Resolve the legacy planner path only when the gate did not claim the run."""

    mode = next_after_recommendation_gate(state)
    if mode == "catalog_candidates":
        return mode
    from .graph import next_execution_path

    return next_execution_path(state)


def catalog_candidates_node(
    state: ShopMindMultiAgentState,
    *,
    provider: CatalogCandidateProvider,
) -> dict[str, Any]:
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


def _clarification(message: str) -> RecommendationResult:
    return RecommendationResult(
        outcome="clarification_required",
        ranking_policy_version=RANKING_POLICY_VERSION,
        request_summary=message,
        structured_constraints=parse_laptop_constraints(message),
        missing_fields=["budget_max_or_primary_use_case"],
        clarification_question="请补充预算、主要用途或至少一项明确的性能需求。",
    )


def deterministic_ranking_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    message = get_last_user_message(state)
    constraints = parse_laptop_constraints(message)
    candidates = [
        CatalogSkuCandidate.model_validate(item)
        for item in state.get("catalog_candidates", [])
    ]
    has_usable_constraint = any(
        (
            constraints.budget_max is not None,
            constraints.memory_min_gb is not None,
            constraints.storage_min_gb is not None,
            constraints.cpu_tier_min is not None,
            constraints.gpu_tier_min is not None,
            bool(constraints.primary_use_cases),
        )
    )
    result = (
        build_laptop_recommendation(candidates, constraints, request_summary=message)
        if has_usable_constraint
        else _clarification(message)
    )
    return {
        "structured_constraints": constraints.model_dump(mode="json"),
        "recommendation_result": result.model_dump(mode="json"),
        "recommendation_diagnostics": {
            **(state.get("recommendation_diagnostics") or {}),
            "candidate_count_before_hard_filter": len(candidates),
            "top_k_sku_codes": [
                candidate.sku_code
                for candidate in candidates
                if any(candidate.sku_id == item.sku_id for item in result.recommendations)
            ],
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
    evidence = provider.retrieve(message=get_last_user_message(state), top_k=top_k)
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
    return {
        "recommendation": recommendation.model_dump(mode="json"),
        "final_response": answer,
        "decision": {
            "status": "completed",
            "answer_type": "structured_laptop_recommendation",
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
