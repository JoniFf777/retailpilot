import httpx
import pytest

from agents.shopmind_multi_agent import (
    create_shopmind_agent_adapter_registry,
    create_shopmind_multi_agent_graph,
)
from agents.shopmind_multi_agent.rag_adapter import RagAgentTaskOutput
from app.core.settings import Settings
from app.runtime import (
    AgentAdapterError,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    DelegationBudgetGuard,
    HttpAgentAdapter,
    InProcessAgentAdapter,
    PolicyEnforcedAgentAdapter,
)


ENDPOINT = "https://rag.internal.example/v1/tasks"


class RagOnlyRouter:
    def route(self, message: str, user_id: str | None = None) -> dict:
        return {
            "intent": "read_path",
            "routes": ["rag_agent"],
            "routing_reasons": {"rag_agent": "forced_remote_rag_test"},
            "confidence": "high",
            "fallback_used": False,
            "requires_user_id_for_preferences": False,
            "router_type": "test",
        }


def remote_settings(**overrides) -> Settings:
    values = {
        "shopmind_rag_agent_transport": "http",
        "shopmind_rag_agent_http_endpoint": ENDPOINT,
        "shopmind_rag_agent_http_allowed_hosts": frozenset(
            {"rag.internal.example"}
        ),
        "shopmind_rag_agent_http_bearer_token": "server-token",
    }
    values.update(overrides)
    return Settings(**values)


def remote_result(task: AgentTask) -> AgentResult:
    output = RagAgentTaskOutput(
        rag_summary={
            "response": "Return policy: 30 days.",
            "citations": [],
            "safety_flags": [],
        },
        executed_routes=["rag_agent"],
        current_route=None,
        safety_flags=[],
        tool_calls=["search_policy_docs"],
        agent_steps=[
            {
                "index": 2,
                "node": "rag_agent",
                "event": "completed",
                "route": "rag_agent",
            }
        ],
    )
    return AgentResult(
        task_id=task.task_id,
        status=AgentTaskStatus.COMPLETED,
        output_data=output.model_dump(mode="python"),
        metadata={"adapter": "http", "agent": "rag_agent"},
    )


def test_registry_defaults_all_specialists_to_in_process() -> None:
    registry = create_shopmind_agent_adapter_registry(
        product_tools=None,
        rag_tools=None,
        preference_tools=None,
        delegation_guard=DelegationBudgetGuard(),
        settings=Settings(),
    )

    for recipient in registry.registered_agents:
        adapter = registry.resolve(recipient)
        assert isinstance(adapter, PolicyEnforcedAgentAdapter)
        assert isinstance(adapter.adapter, InProcessAgentAdapter)


def test_remote_rag_configuration_fails_closed_when_incomplete() -> None:
    with pytest.raises(AgentAdapterError, match="configuration is incomplete"):
        create_shopmind_agent_adapter_registry(
            product_tools=None,
            rag_tools=None,
            preference_tools=None,
            delegation_guard=DelegationBudgetGuard(),
            settings=Settings(shopmind_rag_agent_transport="http"),
        )


def test_registry_selects_only_remote_rag_and_preserves_policy_wrapper() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        task = AgentTask.model_validate_json(request.content)
        return httpx.Response(
            200,
            content=remote_result(task).model_dump_json().encode("utf-8"),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    registry = create_shopmind_agent_adapter_registry(
        product_tools=None,
        rag_tools=None,
        preference_tools=None,
        delegation_guard=DelegationBudgetGuard(),
        settings=remote_settings(),
        rag_http_client=client,
    )

    assert registry.policy_required is True
    assert isinstance(
        registry.resolve("product_agent").adapter,
        InProcessAgentAdapter,
    )
    assert isinstance(registry.resolve("rag_agent").adapter, HttpAgentAdapter)
    assert isinstance(
        registry.resolve("preference_agent").adapter,
        InProcessAgentAdapter,
    )
    assert "server-token" not in repr(registry.resolve("rag_agent").adapter)
    client.close()


def test_graph_uses_remote_rag_without_supervisor_or_state_contract_changes() -> None:
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(request.headers)
        task = AgentTask.model_validate_json(request.content)
        return httpx.Response(
            200,
            content=remote_result(task).model_dump_json().encode("utf-8"),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    graph = create_shopmind_multi_agent_graph(
        supervisor_router=RagOnlyRouter(),
        adapter_settings=remote_settings(),
        rag_http_client=client,
    )

    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "退货政策是什么？"}],
            "user_id": "USER-001",
            "thread_id": "THREAD-001",
            "tool_calls": [],
            "safety_flags": [],
            "agent_steps": [],
        }
    )

    assert result["routes"] == ["rag_agent"]
    assert result["executed_routes"] == ["rag_agent"]
    assert result["rag_summary"]["response"] == "Return policy: 30 days."
    assert result["supervisor_decision"]["router_type"] == "test"
    assert captured_headers["authorization"] == "Bearer server-token"
    assert captured_headers["x-shopmind-task-id"]
    assert captured_headers["x-shopmind-trace-id"]
    client.close()
