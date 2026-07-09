"""Preference read agent for ShopMind V3."""

import re
from typing import Any, Mapping

from tools.preferences import get_user_preferences

from .permissions import guard_tools, tools_by_name
from .state import ShopMindMultiAgentState


PREFERENCE_AGENT_TOOLS = guard_tools("preference_agent", [get_user_preferences])


def _compact_text(text: str, max_chars: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:max_chars]


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
        "preference_summary": {
            "summary": _compact_text(str(result)),
            "source": "get_user_preferences",
            "raw_result_stored": False,
        },
        "executed_routes": executed_routes,
        "current_route": None,
        "tool_calls": tool_calls,
    }
