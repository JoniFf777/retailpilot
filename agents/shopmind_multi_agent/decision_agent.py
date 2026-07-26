"""Final read-path decision agent for ShopMind V3."""

from typing import Any

from app.runtime import (
    EvidenceConflict,
    EvidenceConflictType,
    EvidenceResolution,
    EvidenceResolutionAction,
)

from .observability import append_agent_step
from .state import ShopMindMultiAgentState
from .supervisor_router import WRITE_INTENT_HANDOFF_REASON, WRITE_INTENT_SAFETY_FLAG


DECISION_AGENT_TOOLS: list[Any] = []
WRITE_PATH_HANDOFF_RESPONSE = (
    "\u5f53\u524d V3 \u591a Agent \u8def\u5f84\u53ea\u652f\u6301"
    "\u53ea\u8bfb\u67e5\u8be2\uff0c\u4e0d\u4f1a\u76f4\u63a5"
    "\u6267\u884c\u52a0\u8d2d\u3001\u786e\u8ba4\u8ba2\u5355\u3001"
    "\u6e05\u7a7a\u8d2d\u7269\u8f66\u6216\u4fdd\u5b58\u504f\u597d\u7b49"
    "\u5199\u64cd\u4f5c\u3002\u53ef\u4ee5\u5148\u5e2e\u4f60\u67e5\u8be2"
    "\u5546\u54c1\u3001\u653f\u7b56\u6216\u504f\u597d\u4fe1\u606f\uff1b"
    "\u5982\u9700\u7ee7\u7eed\u5199\u5165\uff0c\u8bf7\u8f6c\u5230"
    "\u786e\u8ba4/\u5199\u5165\u6d41\u7a0b\u5904\u7406\u3002"
)
PRODUCT_EVIDENCE_SCOPE_MISMATCH_RESPONSE = (
    "\u68c0\u7d22\u5230\u7684\u5546\u54c1\u6587\u6863\u4e0e\u5f53\u524d"
    "\u5019\u9009\u5546\u54c1\u4e0d\u4e00\u81f4\uff0c\u6211\u5df2\u6682\u4e0d"
    "\u91c7\u7528\u8be5\u6587\u6863\u4fe1\u606f\u3002\u8bf7\u786e\u8ba4\u8981"
    "\u67e5\u8be2\u7684\u5546\u54c1\u578b\u53f7\u6216\u5546\u54c1 ID\u3002"
)
INSUFFICIENT_CONTEXT_RESPONSE = (
    "\u6211\u76ee\u524d\u6ca1\u6709\u68c0\u7d22\u5230\u8db3\u591f\u7684"
    "\u4fe1\u606f\uff0c\u8bf7\u8865\u5145\u5546\u54c1\u3001\u653f\u7b56"
    "\u6216\u504f\u597d\u76f8\u5173\u95ee\u9898\u3002"
)


def _summary_line(label: str, summary: dict[str, Any] | None) -> str | None:
    if not summary:
        return None
    text = summary.get("summary")
    if not text:
        return None
    return f"{label}\uff1a{text}"


def _used_summaries(
    state: ShopMindMultiAgentState,
    excluded_summaries: set[str] | None = None,
) -> list[str]:
    excluded = excluded_summaries or set()
    used: list[str] = []
    if state.get("product_summary") and "product_summary" not in excluded:
        used.append("product_summary")
    if state.get("rag_summary") and "rag_summary" not in excluded:
        used.append("rag_summary")
    if state.get("preference_summary") and "preference_summary" not in excluded:
        used.append("preference_summary")
    return used


def _answer_type(used_summaries: list[str], security_notes: list[str]) -> str:
    if security_notes:
        return "safe_read_summary"
    if len(used_summaries) > 1:
        return "combined_read_summary"
    if used_summaries == ["product_summary"]:
        return "product_read_summary"
    if used_summaries == ["rag_summary"]:
        return "rag_read_summary"
    if used_summaries == ["preference_summary"]:
        return "preference_read_summary"
    return "insufficient_context"


def _is_write_path_handoff(state: ShopMindMultiAgentState) -> bool:
    return (
        state.get("intent") == "write_path_unsupported"
        or WRITE_INTENT_SAFETY_FLAG in state.get("safety_flags", [])
    )


def _evidence_conflicts(state: ShopMindMultiAgentState) -> list[EvidenceConflict]:
    """Flag product-document scope mismatches with typed provenance."""

    product_ids = {
        str(product_id)
        for product_id in (state.get("product_summary") or {}).get("product_ids") or []
    }
    rag_summary = state.get("rag_summary") or {}
    if not product_ids or rag_summary.get("doc_type") != "product":
        return []

    evidence_references = [
        reference
        for reference in state.get("evidence_references", [])
        if isinstance(reference, dict)
        and isinstance(reference.get("metadata"), dict)
        and reference["metadata"].get("product_id")
    ]
    evidence_product_ids = {
        str(reference["metadata"]["product_id"])
        for reference in evidence_references
    }
    if not evidence_product_ids or product_ids.intersection(evidence_product_ids):
        return []

    return [
        EvidenceConflict(
            conflict_type=EvidenceConflictType.PRODUCT_SCOPE_MISMATCH,
            product_ids=sorted(product_ids),
            evidence_product_ids=sorted(evidence_product_ids),
            evidence_reference_ids=sorted(
                str(reference["ref_id"])
                for reference in evidence_references
                if reference.get("ref_id")
            ),
        )
    ]


def _evidence_resolution(
    conflicts: list[EvidenceConflict],
) -> EvidenceResolution | None:
    if not conflicts:
        return None
    return EvidenceResolution(
        action=(
            EvidenceResolutionAction.EXCLUDE_EVIDENCE_AND_REQUEST_CLARIFICATION
        ),
        excluded_summaries=["rag_summary"],
        followup_reason=EvidenceConflictType.PRODUCT_SCOPE_MISMATCH,
    )


def _write_path_handoff_decision(state: ShopMindMultiAgentState) -> dict[str, Any]:
    safety_flags = list(state.get("safety_flags", []))
    handoff_reason = state.get("handoff_reason") or WRITE_INTENT_HANDOFF_REASON
    return {
        "decision": {
            "status": "handoff_required",
            "answer_type": "write_path_handoff",
            "used_routes": list(state.get("executed_routes", [])),
            "used_summaries": [],
            "requires_followup": True,
            "followup_reason": handoff_reason,
            "safety_flags": safety_flags,
            "security_notes": [],
            "tool_calls": list(state.get("tool_calls", [])),
        },
        "final_response": WRITE_PATH_HANDOFF_RESPONSE,
        "current_route": None,
        "agent_steps": append_agent_step(
            state,
            node="decision_agent",
            event="handoff_required",
            answer_type="write_path_handoff",
            used_summaries=[],
            requires_followup=True,
            followup_reason=handoff_reason,
            safety_flags=safety_flags,
        ),
    }


def decision_agent_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    if _is_write_path_handoff(state):
        return _write_path_handoff_decision(state)

    evidence_conflicts = _evidence_conflicts(state)
    evidence_resolution = _evidence_resolution(evidence_conflicts)
    excluded_summaries = set(
        evidence_resolution.excluded_summaries if evidence_resolution else []
    )
    lines = [
        _summary_line("\u5546\u54c1\u4fe1\u606f", state.get("product_summary")),
        (
            None
            if "rag_summary" in excluded_summaries
            else _summary_line(
                "\u6587\u6863/\u653f\u7b56\u4fe1\u606f",
                state.get("rag_summary"),
            )
        ),
        _summary_line("\u7528\u6237\u504f\u597d", state.get("preference_summary")),
    ]
    answer_parts = [line for line in lines if line]

    rag_summary = state.get("rag_summary") or {}
    security_notes = rag_summary.get("security_notes") or []
    if security_notes:
        answer_parts.append("\u5b89\u5168\u63d0\u793a\uff1a" + "\uff1b".join(security_notes))
    if evidence_resolution:
        answer_parts.append(PRODUCT_EVIDENCE_SCOPE_MISMATCH_RESPONSE)

    used_summaries = _used_summaries(state, excluded_summaries)
    requires_followup = bool(evidence_resolution) or not used_summaries
    followup_reason = (
        evidence_resolution.followup_reason
        if evidence_resolution
        else ("no_read_summary_available" if requires_followup else None)
    )
    answer_type = (
        "evidence_conflict_followup"
        if evidence_resolution
        else _answer_type(used_summaries, security_notes)
    )
    final_response = "\n".join(answer_parts) if answer_parts else INSUFFICIENT_CONTEXT_RESPONSE

    return {
        "decision": {
            "status": "completed",
            "answer_type": answer_type,
            "used_routes": list(state.get("executed_routes", [])),
            "used_summaries": used_summaries,
            "requires_followup": requires_followup,
            "followup_reason": followup_reason,
            "safety_flags": list(state.get("safety_flags", [])),
            "security_notes": security_notes,
            "evidence_reference_count": len(state.get("evidence_references", [])),
            "evidence_conflicts": [
                conflict.model_dump(mode="python") for conflict in evidence_conflicts
            ],
            "evidence_resolution": (
                evidence_resolution.model_dump(mode="python")
                if evidence_resolution
                else None
            ),
            "tool_calls": list(state.get("tool_calls", [])),
        },
        "final_response": final_response,
        "current_route": None,
        "agent_steps": append_agent_step(
            state,
            node="decision_agent",
            event="completed",
            answer_type=answer_type,
            used_summaries=used_summaries,
            requires_followup=requires_followup,
            followup_reason=followup_reason,
            evidence_conflict_count=len(evidence_conflicts),
            evidence_resolution_action=(
                evidence_resolution.action if evidence_resolution else None
            ),
        ),
    }
