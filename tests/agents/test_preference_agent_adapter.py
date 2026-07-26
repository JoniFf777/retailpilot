from langchain_core.tools import tool

from agents.shopmind_multi_agent.permissions import guard_tool, tools_by_name
from agents.shopmind_multi_agent.preference_adapter import (
    PreferenceAgentTaskInput,
    create_preference_agent_adapter,
)
from app.runtime import AgentTask


@tool("get_user_preferences")
def fake_get_user_preferences(user_id: str) -> str:
    """Return the requested user ID so scope propagation is testable."""
    return f"preferences for {user_id}"


def test_preference_adapter_preserves_task_user_scope() -> None:
    adapter = create_preference_agent_adapter(
        tools_by_name([guard_tool("preference_agent", fake_get_user_preferences)])
    )
    task = AgentTask(
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
        sender="route_dispatcher",
        recipient="preference_agent",
        intent="preference_read",
        input_data=PreferenceAgentTaskInput(
            message="show my preferences",
            tool_calls=[],
            executed_routes=[],
            agent_steps=[],
        ).model_dump(mode="python"),
        trace_id="trace-1",
    )

    result = adapter.invoke(task)

    assert result.output_data["tool_calls"] == ["get_user_preferences"]
    assert result.output_data["executed_routes"] == ["preference_agent"]
    assert result.output_data["preference_summary"]["user_id"] == "user-1"
