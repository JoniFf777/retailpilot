"""Final read-path decision agent for ShopMind V3."""

from typing import Any

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


def _summary_line(label: str, summary: dict[str, Any] | None) -> str | None:
    if not summary:
        return None
    text = summary.get("summary")
    if not text:
        return None
    return f"{label}：{text}"


def _used_summaries(state: ShopMindMultiAgentState) -> list[str]:
    used: list[str] = []
    if state.get("product_summary"):
        used.append("product_summary")
    if state.get("rag_summary"):
        used.append("rag_summary")
    if state.get("preference_summary"):
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

    lines = [
        _summary_line("商品信息", state.get("product_summary")),
        _summary_line("文档/政策信息", state.get("rag_summary")),
        _summary_line("用户偏好", state.get("preference_summary")),
    ]
    answer_parts = [line for line in lines if line]

    rag_summary = state.get("rag_summary") or {}
    security_notes = rag_summary.get("security_notes") or []
    if security_notes:
        answer_parts.append("安全提示：" + "；".join(security_notes))

    used_summaries = _used_summaries(state)
    requires_followup = not used_summaries
    followup_reason = (
        "no_read_summary_available"
        if requires_followup
        else None
    )

    final_response = (
        "\n".join(answer_parts)
        if answer_parts
        else "我目前没有检索到足够的信息，请补充商品、政策或偏好相关问题。"
    )

    return {
        "decision": {
            "status": "completed",
            "answer_type": _answer_type(used_summaries, security_notes),
            "used_routes": list(state.get("executed_routes", [])),
            "used_summaries": used_summaries,
            "requires_followup": requires_followup,
            "followup_reason": followup_reason,
            "safety_flags": list(state.get("safety_flags", [])),
            "security_notes": security_notes,
            "tool_calls": list(state.get("tool_calls", [])),
        },
        "final_response": final_response,
        "current_route": None,
        "agent_steps": append_agent_step(
            state,
            node="decision_agent",
            event="completed",
            answer_type=_answer_type(used_summaries, security_notes),
            used_summaries=used_summaries,
            requires_followup=requires_followup,
        ),
    }
