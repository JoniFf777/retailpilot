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
    return sorted(set(re.findall(r"TECH-[A-Z]{3}-\d{3}", text.upper())))


def _product_count(text: str, product_ids: list[str]) -> int:
    match = re.search(r"找到\s+(\d+)\s+个", text)
    if match:
        return int(match.group(1))
    if "没有找到" in text:
        return 0
    return len(product_ids)


def _confidence(product_count: int, product_ids: list[str]) -> str:
    if product_count > 0 and product_ids:
        return "high"
    if product_count > 0:
        return "medium"
    return "low"


def _build_product_summary(
    content: str,
    tool_name: str,
    query: str,
) -> dict[str, Any]:
    product_ids = _product_ids(content)
    product_count = _product_count(content, product_ids)

    if product_count == 0:
        summary = "商品读取完成：未找到匹配商品。"
    else:
        id_part = f"；商品 ID {', '.join(product_ids[:5])}" if product_ids else ""
        summary = f"商品读取完成：匹配商品数量 {product_count}{id_part}。"

    return {
        "summary": summary,
        "source": tool_name,
        "query": _compact_text(query, max_chars=160),
        "product_count": product_count,
        "product_ids": product_ids[:5],
        "confidence": _confidence(product_count, product_ids),
        "raw_result_stored": False,
    }


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
        "product_summary": _build_product_summary(
            _content_from_tool_result(result),
            tool_name,
            message,
        ),
        "executed_routes": executed_routes,
        "current_route": None,
        "tool_calls": tool_calls,
    }
