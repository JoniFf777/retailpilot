"""RAG read agent for ShopMind V3."""

import re
from typing import Any, Literal, Mapping

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field, model_validator

from tools.documents import search_policy_docs, search_product_docs

from .observability import append_agent_step
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

RagSummaryStatus = Literal["success", "degraded"]
RagDegradedReason = Literal[
    "rag_tool_not_configured",
    "rag_unavailable_before_invocation",
]


class RagSummary(BaseModel):
    """Typed direct-RAG status without introducing a global task status."""

    model_config = ConfigDict(extra="allow")

    status: RagSummaryStatus = "success"
    reason_code: RagDegradedReason | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_semantics(self) -> "RagSummary":
        if self.status == "degraded":
            if self.reason_code is None:
                raise ValueError("Degraded RAG summaries require a bounded reason.")
            if self.citations:
                raise ValueError("Degraded RAG summaries cannot contain citations.")
        elif self.reason_code is not None:
            raise ValueError("Successful RAG summaries cannot contain a degraded reason.")
        return self


class RagToolResultError(ValueError):
    """Raised when an invoked RAG tool returns an invalid result shape."""


def _content_and_documents(result: Any) -> tuple[str, list[Document]]:
    if isinstance(result, tuple):
        if len(result) != 2 or not isinstance(result[0], str) or not isinstance(result[1], list):
            raise RagToolResultError("RAG tool returned an invalid result shape.")
        content = result[0]
        docs = result[1]
        return content, docs
    if isinstance(result, str):
        return result, []
    raise RagToolResultError("RAG tool returned an invalid result shape.")


def _compact_text(text: str, max_chars: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:max_chars]


def _citations(documents: list[Document]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for doc in documents[:3]:
        citations.append(
            {
                "document_id": doc.metadata.get("id"),
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
    if tools is None:
        tool_map = tools_by_name(RAG_AGENT_TOOLS)
    elif isinstance(tools, Mapping):
        tool_map = dict(tools)
    else:
        tool_map = tools_by_name(tools)
    message = get_last_user_message(state)
    lowered = message.lower()

    if any(keyword in lowered for keyword in ("policy", "return", "warranty", "shipping")) or any(
        keyword in message for keyword in ("政策", "退货", "退款", "保修", "配送")
    ):
        tool_name = "search_policy_docs"
    else:
        tool_name = "search_product_docs"

    tool = tool_map.get(tool_name)
    degraded_reason: RagDegradedReason | None = None
    if tool is None:
        # Local development intentionally permits the graph to run without a
        # downloaded embedding model. Catalog facts remain available through
        # the product path; document evidence is optional enrichment.
        content, documents = "本地开发未启用文档检索，已跳过 embedding 证据。", []
        degraded_reason = "rag_tool_not_configured"
    else:
        # Once invocation begins, failures must reach the typed adapter/plan
        # boundary. They are not optional degradation and must not look like a
        # completed specialist result.
        result = tool.invoke({"query": message})
        content, documents = _content_and_documents(result)
    security_notes = _security_notes(content)

    tool_calls = list(state.get("tool_calls", []))
    if tool is not None:
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

    summary = RagSummary(
        status="degraded" if degraded_reason is not None else "success",
        reason_code=degraded_reason,
        summary=safe_summary,
        source=tool_name,
        doc_type=_doc_type(tool_name),
        citations=_citations(documents),
        confidence="medium" if content else "low",
        security_notes=security_notes,
        raw_result_stored=False,
    )
    return {
        "rag_summary": summary.model_dump(mode="python"),
        "executed_routes": executed_routes,
        "current_route": None,
        "safety_flags": safety_flags,
        "tool_calls": tool_calls,
        "agent_steps": append_agent_step(
            state,
            node="rag_agent",
            event="degraded" if degraded_reason is not None else "completed",
            route="rag_agent",
            tool_name=tool_name,
            doc_type=_doc_type(tool_name),
            security_note_count=len(security_notes),
        ),
    }
