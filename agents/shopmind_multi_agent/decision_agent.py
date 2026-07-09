"""Final read-path decision agent for ShopMind V3."""

from typing import Any

from .state import ShopMindMultiAgentState


DECISION_AGENT_TOOLS: list[Any] = []


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


def decision_agent_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
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
    }
