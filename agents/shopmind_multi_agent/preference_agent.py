"""Preference read agent for ShopMind V3."""

import re
from typing import Any, Mapping

from tools.preferences import get_user_preferences

from .observability import append_agent_step
from .permissions import guard_tools, tools_by_name
from .state import ShopMindMultiAgentState


PREFERENCE_AGENT_TOOLS = guard_tools("preference_agent", [get_user_preferences])


def _preference_count(text: str) -> int:
    if "暂无" in text or "尚未记录" in text:
        return 0
    numbered_items = re.findall(r"(?:^|\s)\d+\.", text)
    return len(numbered_items)


def _build_preference_summary(result: str, user_id: str) -> dict[str, Any]:
    preference_count = _preference_count(result)
    has_preferences = preference_count > 0
    summary = (
        f"偏好读取完成：记录 {preference_count} 条。"
        if has_preferences
        else "偏好读取完成：暂无已记录偏好。"
    )

    return {
        "summary": summary,
        "source": "get_user_preferences",
        "user_id": user_id,
        "preference_count": preference_count,
        "has_preferences": has_preferences,
        "confidence": "medium" if has_preferences else "low",
        "raw_result_stored": False,
    }


def preference_agent_node(
    state: ShopMindMultiAgentState,
    tools: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tool_map = dict(tools or tools_by_name(PREFERENCE_AGENT_TOOLS))
    user_id = state.get("user_id") or ""
    result = tool_map["get_user_preferences"].invoke({"user_id": user_id})

    tool_calls = list(state.get("tool_calls", []))
    tool_calls.append("get_user_preferences")
    executed_routes = list(state.get("executed_routes", []))
    executed_routes.append("preference_agent")

    return {
        "preference_summary": _build_preference_summary(str(result), user_id),
        "executed_routes": executed_routes,
        "current_route": None,
        "tool_calls": tool_calls,
        "agent_steps": append_agent_step(
            state,
            node="preference_agent",
            event="completed",
            route="preference_agent",
            tool_name="get_user_preferences",
            has_user_id=bool(user_id),
        ),
    }
