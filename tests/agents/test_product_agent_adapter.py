from langchain_core.tools import tool

from agents.shopmind_multi_agent.permissions import guard_tool
from agents.shopmind_multi_agent.product_adapter import (
    ProductAgentTaskInput,
    create_product_agent_adapter,
    product_agent_adapter_node,
)
from app.runtime import (
    AgentAdapter,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    RunUsage,
    build_agent_task_idempotency_key,
)


@tool("search_products")
def fake_search_products(query: str, limit: int = 5) -> str:
    """Return a deterministic product result for adapter coverage."""
    return "Found 1 product: Test Keyboard (TECH-KEY-001)"


def test_product_adapter_invokes_existing_specialist_through_typed_task() -> None:
    adapter = create_product_agent_adapter(
        [guard_tool("product_agent", fake_search_products)]
    )
    task = AgentTask(
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
        sender="route_dispatcher",
        recipient="product_agent",
        intent="product_read",
        input_data=ProductAgentTaskInput(
            message="recommend a keyboard",
            tool_calls=[],
            executed_routes=[],
            agent_steps=[],
        ).model_dump(mode="python"),
        trace_id="trace-1",
    )

    result = adapter.invoke(task)

    assert result.output_data["tool_calls"] == ["search_products"]
    assert result.output_data["executed_routes"] == ["product_agent"]
    assert result.output_data["product_summary"]["source"] == "search_products"


def test_product_graph_bridge_accepts_transport_neutral_adapter() -> None:
    captured_tasks: list[AgentTask] = []

    class ProtocolProductAdapter:
        agent_name = "product_agent"

        def invoke(self, task: AgentTask) -> AgentResult:
            captured_tasks.append(task)
            return AgentResult(
                task_id=task.task_id,
                status=AgentTaskStatus.COMPLETED,
                output_data={
                    "product_summary": {"source": "protocol_adapter"},
                    "executed_routes": ["product_agent"],
                    "current_route": "product_agent",
                    "tool_calls": [],
                    "agent_steps": [],
                },
                usage=RunUsage(total_tokens=12),
            )

    adapter = ProtocolProductAdapter()
    output = product_agent_adapter_node(
        {
            "messages": [{"role": "user", "content": "recommend a keyboard"}],
            "user_id": "user-1",
            "thread_id": "thread-1",
            "tool_calls": [],
            "executed_routes": [],
            "agent_steps": [],
        },
        adapter=adapter,
    )

    assert isinstance(adapter, AgentAdapter)
    assert output["product_summary"]["source"] == "protocol_adapter"
    assert output["delegated_usage"][0]["total_tokens"] == 12
    assert len(captured_tasks) == 1
    task = captured_tasks[0]
    assert task.idempotency_key == build_agent_task_idempotency_key(
        task.run_id,
        task.task_id,
    )
    assert task.retry_policy.owner == "disabled"
    assert task.retry_policy.max_attempts == 1
