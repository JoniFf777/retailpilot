"""Product read agent for ShopMind V3."""

import re
from typing import Any, Mapping

from tools.products import compare_products, get_product_detail, search_products

from .permissions import guard_tools, tools_by_name
from .state import ShopMindMultiAgentState
from .supervisor import get_last_user_message


PRODUCT_AGENT_TOOLS = guard_tools(
    "product_agent",
    [search_products, get_product_detail, compare_products],
)


def _content_from_tool_result(result: Any) -> str:
    if isinstance(result, tuple):
        return str(result[0])
    return str(result)


def _compact_text(text: str, max_chars: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:max_chars]


def _product_ids(text: str) -> list[str]:
    return re.findall(r"TECH-[A-Z]{3}-\d{3}", text.upper())


def product_agent_node(
    state: ShopMindMultiAgentState,
    tools: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tool_map = dict(tools or tools_by_name(PRODUCT_AGENT_TOOLS))
    message = get_last_user_message(state)
    lowered = message.lower()
    product_ids = _product_ids(message)

    if ("对比" in message or "比较" in message or "compare" in lowered) and product_ids:
        tool_name = "compare_products"
        result = tool_map[tool_name].invoke({"product_identifiers": product_ids})
    elif product_ids and ("详情" in message or "detail" in lowered or "价格" in message):
        tool_name = "get_product_detail"
        result = tool_map[tool_name].invoke({"product_identifier": product_ids[0]})
    else:
        tool_name = "search_products"
        result = tool_map[tool_name].invoke({"query": message, "limit": 5})

    tool_calls = list(state.get("tool_calls", []))
    tool_calls.append(tool_name)
    executed_routes = list(state.get("executed_routes", []))
    executed_routes.append("product_agent")

    return {
        "product_summary": {
            "summary": _compact_text(_content_from_tool_result(result)),
            "source": tool_name,
            "raw_result_stored": False,
        },
        "executed_routes": executed_routes,
        "current_route": None,
        "tool_calls": tool_calls,
    }
