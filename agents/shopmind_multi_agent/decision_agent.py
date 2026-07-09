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

    final_response = (
        "\n".join(answer_parts)
        if answer_parts
        else "我目前没有检索到足够的信息，请补充商品、政策或偏好相关问题。"
    )

    return {
        "decision": {
            "status": "completed",
            "used_routes": list(state.get("executed_routes", [])),
            "safety_flags": list(state.get("safety_flags", [])),
        },
        "final_response": final_response,
        "current_route": None,
    }
