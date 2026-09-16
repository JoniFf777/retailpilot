"""Deterministic Phase 1B nodes; they do not add a new autonomous Agent."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.recommendation.categories import CategoryRegistry
from app.recommendation.gate import RecommendationGateDecision, classify_recommendation_request
from app.recommendation.providers import CatalogCandidateProvider, RecommendationPreferenceProvider
from app.recommendation.rag import (
    RecommendationEvidence,
    RecommendationEvidenceProvider,
    attach_validated_evidence,
)
from app.recommendation.executor import (
    RecommendationTaskPlan,
    RecommendationTaskStep,
    StructuredRecommendationExecutor,
)
from app.recommendation.request import parse_recommendation_request
from app.recommendation.session_state import ShoppingSessionState
from app.recommendation.service import (
    RANKING_POLICY_VERSION,
    build_recommendation,
)
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import LaptopConstraints, RecommendationResult

from .observability import append_agent_step
from .state import ShopMindMultiAgentState
from .supervisor import get_last_user_message


def _context_category(
    state: ShopMindMultiAgentState,
    *,
    registry: CategoryRegistry | None = None,
) -> str | None:
    """Find the most recent same-thread category for a terse follow-up."""

    active_registry = registry
    for item in reversed(state.get("context_items", [])):
        provenance = item.get("provenance") or {}
        recommendation_state = provenance.get("recommendation_state")
        if isinstance(recommendation_state, dict) and recommendation_state.get("category"):
            return str(recommendation_state["category"])
        if provenance.get("role") != "user" and provenance.get("source") != "conversation_summary":
            continue
        message = str(item.get("content") or "")
        decision = classify_recommendation_request(
            message,
            {"intent": "read_path", "routes": ["product_agent"]},
            registry=active_registry,
        )
        if decision.category:
            return decision.category
    return None


def _cleared_request_fields(message: str) -> set[str]:
    """Recognize explicit user requests to remove inherited constraints."""

    lowered = message.casefold()
    cleared: set[str] = set()
    if any(token in lowered for token in ("预算不限", "不设预算", "无预算限制", "不限预算")):
        cleared.add("__budget__")
    if any(token in lowered for token in ("不再要求轻薄", "不要求轻薄", "不限重量", "重量不限")):
        cleared.add("weight_max_kg")
    if any(token in lowered for token in ("不再要求内存", "不要求内存", "内存不限")):
        cleared.add("memory_min_gb")
    if any(token in lowered for token in ("不再要求存储", "不要求存储", "存储不限")):
        cleared.add("storage_min_gb")
    if any(token in lowered for token in ("不再要求屏幕", "不要求屏幕", "屏幕不限")):
        cleared.add("screen_inches")
    return cleared


def _needs_document_evidence(message: str) -> bool:
    """Return true for claims that Catalog fields cannot establish."""

    return any(
        term in message.casefold()
        for term in (
            "兼容", "接口", "静音", "噪音", "风扇", "防水", "防泼", "安装",
            "policy", "return", "refund", "warranty", "shipping", "退货", "退款", "保修", "配送", "政策",
        )
    )


def _latest_session_state(
    state: ShopMindMultiAgentState, category: str
) -> ShoppingSessionState | None:
    for item in reversed(state.get("context_items", [])):
        raw = (item.get("provenance") or {}).get("recommendation_state")
        if not isinstance(raw, dict) or raw.get("category") != category:
            continue
        try:
            return ShoppingSessionState.model_validate(raw)
        except Exception:
            continue
    return None


def recommendation_gate_node(
    state: ShopMindMultiAgentState,
    *,
    registry: CategoryRegistry | None = None,
) -> dict[str, Any]:
    decision = classify_recommendation_request(
        get_last_user_message(state), state.get("supervisor_decision"), registry=registry
    )
    current_message = get_last_user_message(state)
    if decision.mode == "legacy_read" and any(
        term in current_message.casefold()
        for term in ("预算", "改成", "其他不变", "保持不变", "换成", "再推荐", "提高", "降低", "轻一点", "重一点", "排除", "去掉")
    ):
        prior_category = _context_category(state, registry=registry)
        if prior_category:
            decision = RecommendationGateDecision(
                mode="structured_recommendation",
                reason="category_inherited_from_thread_context",
                category=prior_category,
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
    if mode == "structured_recommendation":
        return "recommendation_task_executor"
    if mode in {"recommendation_clarification", "unsupported_category"}:
        return "recommendation_resolution"
    return "legacy_execution"


def next_graph_path_after_recommendation_gate(state: ShopMindMultiAgentState) -> str:
    """Resolve the legacy planner path only when the gate did not claim the run."""

    mode = next_after_recommendation_gate(state)
    if mode in {"catalog_candidates", "recommendation_task_executor", "recommendation_resolution"}:
        return mode
    from .graph import next_execution_path

    return next_execution_path(state)


def catalog_candidates_node(
    state: ShopMindMultiAgentState,
    *,
    provider: CatalogCandidateProvider,
) -> dict[str, Any]:
    category = (state.get("recommendation_gate") or {}).get("category")
    if not category:
        return {
            "catalog_candidates": [],
            "agent_steps": append_agent_step(
                state,
                node="catalog_candidates",
                event="rejected_missing_category",
            ),
        }
    candidates = provider.list_active_skus(str(category))
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
    """Load confirmed preferences as bounded, explainable soft ranking inputs."""

    summary = provider.summary_for_user(state.get("user_id"))
    category = (state.get("recommendation_gate") or {}).get("category")
    constraint_reader = getattr(provider, "preference_constraints_for_user", None)
    preference_constraints = (
        constraint_reader(state.get("user_id"), str(category))
        if callable(constraint_reader) and category
        else {}
    )
    serialized_constraints = {
        key: value.model_dump(mode="json")
        if hasattr(value, "model_dump")
        else dict(value)
        for key, value in preference_constraints.items()
    }
    return {
        "preference_summary": summary,
        "preference_constraints": serialized_constraints,
        "recommendation_diagnostics": {
            **(state.get("recommendation_diagnostics") or {}),
            "preference_summary_present": bool(summary),
            "preference_used_for_ranking": bool(serialized_constraints),
        },
        "agent_steps": append_agent_step(
            state,
            node="recommendation_preference",
            event="applied_soft_constraints" if serialized_constraints else "no_applicable_constraints",
            preference_summary_present=bool(summary),
            preference_constraint_count=len(serialized_constraints),
        ),
    }


def deterministic_ranking_node(
    state: ShopMindMultiAgentState,
    *,
    registry: CategoryRegistry | None = None,
) -> dict[str, Any]:
    message = get_last_user_message(state)
    gate = state.get("recommendation_gate") or {}
    category = gate.get("category")
    if not category:
        return recommendation_resolution_node(state)
    request = parse_recommendation_request(message, category, registry=registry)
    current_turn_request = request
    cleared_fields = _cleared_request_fields(message)
    prior_session_state = _latest_session_state(state, str(category))
    prior_user_messages = [
        str(item.get("content") or "")
        for item in state.get("context_items", [])
        if (
            (item.get("provenance") or {}).get("role") == "user"
            or (item.get("provenance") or {}).get("source") == "conversation_summary"
        )
    ]
    # Harness context can include the just-persisted current request as well as
    # earlier turns. Merge in order; repeating the current patch is idempotent.
    has_structured_context = any(
        isinstance((item.get("provenance") or {}).get("recommendation_state"), dict)
        for item in state.get("context_items", [])
    )
    if (prior_user_messages or has_structured_context) and not (
        gate.get("reason") != "category_inherited_from_thread_context"
        and _context_category(state, registry=registry) not in {None, category}
    ):
        inherited_attributes: dict[str, Any] = {}
        inherited_budget_min = None
        inherited_budget = None
        inherited_currency = None
        if prior_session_state is not None:
            inherited_attributes.update(prior_session_state.category_attributes)
            inherited_budget = prior_session_state.budget_max
            inherited_budget_min = prior_session_state.budget_min
            inherited_currency = prior_session_state.budget_currency
        # A validated persisted state is authoritative.  Re-parsing every
        # historical sentence can resurrect a cleared field or leak a laptop
        # constraint into a newly selected monitor category.  The prose
        # fallback is kept only for legacy threads that have no state yet.
        if prior_session_state is None:
            for prior_message in prior_user_messages:
                prior_request = parse_recommendation_request(
                    prior_message, category, registry=registry
                )
                inherited_attributes.update(prior_request.category_attributes)
                inherited_budget = prior_request.budget_max or inherited_budget
                inherited_budget_min = prior_request.budget_min or inherited_budget_min
                inherited_currency = prior_request.budget_currency or inherited_currency
        merged_attributes = dict(inherited_attributes)
        for key in cleared_fields:
            merged_attributes.pop(key, None)
        merged_attributes.update(request.category_attributes)
        inherited_budget = None if "__budget__" in cleared_fields else inherited_budget
        inherited_budget_min = None if "__budget__" in cleared_fields else inherited_budget_min
        inherited_currency = None if "__budget__" in cleared_fields else inherited_currency
        request = request.model_copy(
            update={
                "budget_max": request.budget_max or inherited_budget,
                "budget_min": request.budget_min or inherited_budget_min,
                "budget_currency": request.budget_currency or inherited_currency,
                "category_attributes": merged_attributes,
            }
        )
    # Current-turn constraints win. Persisted preferences are only soft
    # defaults, and therefore fill fields the user did not mention explicitly.
    preference_constraints = state.get("preference_constraints") or {}
    if preference_constraints:
        merged_attributes = {
            key: value
            for key, value in preference_constraints.items()
            if key not in cleared_fields
        }
        merged_attributes.update(request.category_attributes)
        request = request.model_copy(update={"category_attributes": merged_attributes})
    candidates = [
        CatalogSkuCandidate.model_validate(item)
        for item in state.get("catalog_candidates", [])
    ]
    newly_excluded: list[str] = []
    exclusion_match = re.search(r"(?:排除|去掉|移除)\s*(?:第)?(\d+)\s*(?:个|项|款)?", message)
    if prior_session_state is not None and prior_session_state.candidates_are_current and exclusion_match:
        index = int(exclusion_match.group(1)) - 1
        current_candidates = prior_session_state.current_candidate_sku_codes()
        if 0 <= index < len(current_candidates):
            newly_excluded.append(current_candidates[index])
    excluded_sku_codes = list(
        dict.fromkeys(
            (prior_session_state.excluded_sku_codes if prior_session_state else [])
            + newly_excluded
        )
    )
    if excluded_sku_codes:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.sku_code not in set(excluded_sku_codes)
        ]
    result = build_recommendation(
        candidates,
        request,
        request_summary=message,
        enforce_request_minimum=True,
        registry=registry,
    )
    selected_ids = {item.sku_id for item in result.recommendations}
    session_state = ShoppingSessionState(
        owner_id=state.get("user_id") or None,
        thread_id=state.get("thread_id"),
        version=(prior_session_state.version + 1 if prior_session_state else 1),
        updated_at=datetime.now(timezone.utc),
        category=str(category),
        budget_min=request.budget_min,
        budget_max=request.budget_max,
        budget_currency=request.budget_currency,
        category_attributes={
            key: value.model_dump(mode="json")
            if hasattr(value, "model_dump")
            else value
            for key, value in request.category_attributes.items()
        },
        field_sources={
            key: source
            for key, source in {
                **(
                    prior_session_state.field_sources
                    if prior_session_state is not None
                    else {}
                ),
                **{
                    key: "preference"
                    for key in preference_constraints
                    if key not in current_turn_request.category_attributes
                },
                **{
                    key: "user"
                    for key in current_turn_request.category_attributes
                },
            }.items()
            if key in request.category_attributes
        },
        pending_questions=(
            [result.clarification_question]
            if result.clarification_question
            else []
        ),
        candidate_sku_codes=[
            candidate.sku_code
            for candidate in candidates
            if candidate.sku_id in selected_ids
        ],
        excluded_sku_codes=excluded_sku_codes,
        candidate_expires_at=(
            datetime.now(timezone.utc) + timedelta(minutes=30)
            if result.recommendations
            else None
        ),
    )
    return {
        "structured_constraints": result.structured_constraints.model_dump(mode="json"),
        "recommendation_result": result.model_dump(mode="json"),
        "shopping_session_state": session_state.model_dump(mode="json"),
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
            diagnostics={"evidence_unavailable": True, "evidence_status": "unavailable"},
        )
    evidence_status = str(evidence.diagnostics.get("evidence_status") or "unknown")
    if (
        _needs_document_evidence(get_last_user_message(state))
        and evidence_status in {"unknown", "degraded"}
        and top_k
    ):
        # One bounded business recheck is distinct from transport retries. It
        # asks the same server-owned scope for the missing fact, then falls
        # back to the first trusted result if the recheck does not improve it.
        try:
            recheck = provider.retrieve(
                message=f"{get_last_user_message(state)} 请核实必要事实并返回文档引用",
                top_k=top_k,
            )
            recheck_status = str(recheck.diagnostics.get("evidence_status") or "unknown")
            evidence = recheck if recheck_status == "available" else RecommendationEvidence(
                product_evidence=evidence.product_evidence,
                policy_evidence=evidence.policy_evidence,
                diagnostics={
                    **evidence.diagnostics,
                    "business_recheck_attempted": True,
                    "business_recheck_status": recheck_status,
                },
            )
            evidence_status = str(evidence.diagnostics.get("evidence_status") or evidence_status)
        except Exception:
            evidence = RecommendationEvidence(
                product_evidence=evidence.product_evidence,
                policy_evidence=evidence.policy_evidence,
                diagnostics={
                    **evidence.diagnostics,
                    "business_recheck_attempted": True,
                    "business_recheck_status": "unavailable",
                },
            )
    if _needs_document_evidence(get_last_user_message(state)) and evidence_status in {
        "unknown",
        "unavailable",
    }:
        payload = result.model_dump(mode="json")
        payload.update(
            {
                "outcome": "clarification_required",
                "recommendations": [],
                "evidence_status": evidence_status,
                "policy_evidence": [item.model_dump(mode="json") for item in evidence.policy_evidence],
                "error_code": (
                    "evidence_unavailable"
                    if evidence_status == "unavailable"
                    else "evidence_unknown"
                ),
                "missing_fields": ["document_evidence"],
                "clarification_question": "我没有找到能够验证该条件的商品文档，请换一种描述或允许我只依据目录字段推荐。",
            }
        )
        result = RecommendationResult.model_validate(payload)
    validated = attach_validated_evidence(
        result,
        evidence,
        sku_codes_by_id={candidate.sku_id: candidate.sku_code for candidate in top_k},
    )
    validated = validated.model_copy(
        update={
            "evidence_status": evidence_status,
            "policy_evidence": evidence.policy_evidence,
        }
    )
    if _needs_document_evidence(get_last_user_message(state)) and validated.recommendations:
        # For document-dependent requests, supported candidates get a stable
        # evidence-coverage tie-break. Catalog score remains the secondary
        # order, and no new SKU can enter through this enrichment step.
        validated = validated.model_copy(
            update={
                "recommendations": sorted(
                    validated.recommendations,
                    key=lambda item: (
                        -len(item.evidence),
                        -item.score,
                        item.sku_name,
                    ),
                )
            }
        )
    evidence_coverage = {
        item.sku_name: len(item.evidence) for item in validated.recommendations
    }
    return {
        "recommendation": RecommendationResult.model_validate(validated).model_dump(mode="json"),
        "recommendation_diagnostics": {
            **diagnostics,
            **evidence.diagnostics,
            "evidence_status": evidence_status,
            "evidence_coverage": evidence_coverage,
        },
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


def recommendation_task_executor_node(
    state: ShopMindMultiAgentState,
    *,
    catalog_provider: CatalogCandidateProvider,
    preference_provider: RecommendationPreferenceProvider,
    evidence_provider: RecommendationEvidenceProvider,
    registry: CategoryRegistry | None = None,
    cancellation_check: Any | None = None,
) -> dict[str, Any]:
    """Run the structured recommendation stages through one task contract."""

    default_steps = [
        RecommendationTaskStep(step_id="catalog", stage="catalog", depends_on=[]),
        RecommendationTaskStep(step_id="preference", stage="preference", depends_on=["catalog"]),
        RecommendationTaskStep(step_id="ranking", stage="ranking", depends_on=["preference"]),
        RecommendationTaskStep(step_id="evidence", stage="evidence", depends_on=["ranking"]),
        RecommendationTaskStep(step_id="decision", stage="decision", depends_on=["evidence"]),
    ]
    proposed_steps = state.get("recommendation_task_plan")
    try:
        plan = RecommendationTaskPlan(
            plan_id=f"{state.get('thread_id') or 'local'}:recommendation-task-v1",
            steps=(
                [RecommendationTaskStep.model_validate(item) for item in proposed_steps]
                if isinstance(proposed_steps, list)
                else default_steps
            ),
        )
        allowed_stages = {"catalog", "preference", "ranking", "evidence", "decision"}
        if any(step.stage not in allowed_stages for step in plan.steps):
            raise ValueError("recommendation task stage is not allowed")
    except Exception:
        plan = RecommendationTaskPlan(
        plan_id=f"{state.get('thread_id') or 'local'}:recommendation-task-v1",
        steps=default_steps,
        )
    handlers = {
        "catalog": lambda current: catalog_candidates_node(current, provider=catalog_provider),
        "preference": lambda current: recommendation_preference_node(current, provider=preference_provider),
        "ranking": lambda current: deterministic_ranking_node(current, registry=registry),
        "evidence": lambda current: recommendation_evidence_node(current, provider=evidence_provider),
        "decision": recommendation_decision_node,
    }
    execution = StructuredRecommendationExecutor().execute(
        state,
        plan,
        handlers,
        cancellation_check=cancellation_check,
    )
    initial_keys = set(state)
    output = {
        key: value
        for key, value in execution.state.items()
        if key not in initial_keys or key in {
            "catalog_candidates",
            "preference_summary",
            "preference_constraints",
            "structured_constraints",
            "recommendation_result",
            "shopping_session_state",
            "recommendation_diagnostics",
            "top_k_product_evidence",
            "policy_evidence",
            "recommendation",
            "final_response",
            "decision",
        }
    }
    output["recommendation_task"] = execution.result.model_dump(mode="json")
    output["agent_steps"] = execution.state.get("agent_steps", state.get("agent_steps", []))
    return output


def recommendation_decision_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    """Explain the already-fixed result; this node cannot introduce products."""

    recommendation = RecommendationResult.model_validate(
        state.get("recommendation") or state.get("recommendation_result") or {}
    )
    if recommendation.outcome == "recommended":
        names = "、".join(item.product_name for item in recommendation.recommendations)
        answer = f"已按你的硬约束筛选并排序：{names}。"
        if state.get("policy_evidence"):
            refs = [
                str(item.get("ref"))
                for item in state.get("policy_evidence", [])
                if isinstance(item, dict) and item.get("ref")
            ]
            answer += "已结合通用政策资料说明"
            if refs:
                answer += f"（依据：{'、'.join(refs)}）。"
            else:
                answer += "。"
        evidence_status = (state.get("recommendation_diagnostics") or {}).get("evidence_status")
        if evidence_status == "unavailable":
            answer += "文档证据服务本次不可用，以上结论仅依据目录字段。"
        elif evidence_status == "unknown":
            answer += "本次没有找到能够支持额外文档结论的证据。"
    elif recommendation.outcome == "no_match":
        answer = recommendation.no_match_reason or "没有满足硬约束的商品。"
    else:
        answer = recommendation.clarification_question or "请补充推荐条件。"
    return {
        "recommendation": recommendation.model_dump(mode="json"),
        "final_response": answer,
        "decision": {
            "status": "completed",
            "answer_type": "structured_recommendation",
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
        question = "当前暂不支持该品类，请选择一个已注册的商品类别。"
    else:
        question = "你希望推荐哪个商品类别？"
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
