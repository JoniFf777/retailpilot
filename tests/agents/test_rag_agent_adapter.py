from langchain_core.documents import Document

from agents.shopmind_multi_agent.permissions import guard_tool, tools_by_name
from agents.shopmind_multi_agent.rag_adapter import (
    RagAgentTaskInput,
    create_rag_agent_adapter,
)
from app.runtime import AgentTask


class FakeRagTool:
    name = "search_product_docs"

    def invoke(self, arguments: dict[str, str]):
        return (
            "Keyboard documentation",
            [
                Document(
                    page_content="Keyboard documentation",
                    metadata={
                        "id": 42,
                        "source_name": "keyboard-guide",
                        "product_id": "TECH-KEY-001",
                        "score": 0.91,
                    },
                )
            ],
        )


def test_rag_adapter_returns_typed_document_evidence() -> None:
    adapter = create_rag_agent_adapter(
        tools_by_name([guard_tool("rag_agent", FakeRagTool())])
    )
    task = AgentTask(
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
        sender="route_dispatcher",
        recipient="rag_agent",
        intent="document_retrieval",
        input_data=RagAgentTaskInput(
            message="keyboard documentation",
            tool_calls=[],
            executed_routes=[],
            safety_flags=[],
            agent_steps=[],
        ).model_dump(mode="python"),
        trace_id="trace-1",
    )

    result = adapter.invoke(task)

    assert result.output_data["tool_calls"] == ["search_product_docs"]
    assert result.evidence_references[0].ref_id == "42"
    assert result.evidence_references[0].metadata["source_name"] == "keyboard-guide"
