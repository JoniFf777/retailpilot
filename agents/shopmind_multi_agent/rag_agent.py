"""RAG read agent for ShopMind V3."""

import re
from typing import Any, Mapping

from langchain_core.documents import Document

from tools.documents import search_policy_docs, search_product_docs

from .permissions import guard_tools, tools_by_name
from .state import ShopMindMultiAgentState
from .supervisor import get_last_user_message


RAG_AGENT_TOOLS = guard_tools(
    "rag_agent",
    [search_product_docs, search_policy_docs],
)

INJECTION_PATTERNS = (
    "忽略之前",
    "忽略所有",
    "直接调用",
    "add_to_cart",
    "confirm_add_to_cart",
    "prepare_add_to_cart",
    "pending action",
    "ignore previous",
)


def _content_and_documents(result: Any) -> tuple[str, list[Document]]:
    if isinstance(result, tuple):
        content = str(result[0])
        docs = result[1] if len(result) > 1 and isinstance(result[1], list) else []
        return content, docs
    return str(result), []


def _compact_text(text: str, max_chars: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:max_chars]


def _citations(documents: list[Document]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for doc in documents[:3]:
        citations.append(
            {
                "source_name": doc.metadata.get("source_name")
                or doc.metadata.get("policy_name")
                or doc.metadata.get("product_name")
                or "unknown",
                "product_id": doc.metadata.get("product_id"),
                "score": doc.metadata.get("score"),
            }
        )
    return citations


def _doc_type(tool_name: str) -> str:
    return "policy" if tool_name == "search_policy_docs" else "product"


def _security_notes(text: str) -> list[str]:
    lowered = text.lower()
    if any(pattern.lower() in lowered for pattern in INJECTION_PATTERNS):
        return ["检索内容包含疑似 prompt injection 或写操作指令，已作为不可信内容处理。"]
    return []


def rag_agent_node(
    state: ShopMindMultiAgentState,
    tools: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tool_map = dict(tools or tools_by_name(RAG_AGENT_TOOLS))
    message = get_last_user_message(state)
    lowered = message.lower()

    if any(keyword in lowered for keyword in ("policy", "return", "warranty", "shipping")) or any(
        keyword in message for keyword in ("政策", "退货", "退款", "保修", "配送")
    ):
        tool_name = "search_policy_docs"
    else:
        tool_name = "search_product_docs"

    result = tool_map[tool_name].invoke({"query": message})
    content, documents = _content_and_documents(result)
    security_notes = _security_notes(content)

    tool_calls = list(state.get("tool_calls", []))
    tool_calls.append(tool_name)
    executed_routes = list(state.get("executed_routes", []))
    executed_routes.append("rag_agent")
    safety_flags = list(state.get("safety_flags", []))
    if security_notes:
        safety_flags.append("rag_prompt_injection_detected")

    safe_summary = (
        "检索内容包含疑似不可信指令，已屏蔽原文并仅保留安全记录。"
        if security_notes
        else _compact_text(content)
    )

    return {
        "rag_summary": {
            "summary": safe_summary,
            "source": tool_name,
            "doc_type": _doc_type(tool_name),
            "citations": _citations(documents),
            "confidence": "medium" if content else "low",
            "security_notes": security_notes,
            "raw_result_stored": False,
        },
        "executed_routes": executed_routes,
        "current_route": None,
        "safety_flags": safety_flags,
        "tool_calls": tool_calls,
    }
