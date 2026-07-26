from threading import Event

import pytest
from langchain_core.tools import tool

from agents.shopmind_multi_agent import (
    ValidatedProviderPlanner,
    create_shopmind_multi_agent_graph,
)
from agents.shopmind_multi_agent.permissions import guard_tool, tools_by_name
from agents.shopmind_multi_agent.rag_adapter import create_rag_agent_adapter
from app.runtime import (
    AgentResult,
    AgentTaskStatus,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTransportError,
    AgentTransportFailureCode,
    PolicyEnforcedAgentAdapter,
    RunBudget,
    RunContext,
    RunRequest,
    RunUsage,
    RuntimePolicy,
)


MESSAGE = "recommend a keyboard with return policy based on my preference"


@tool("get_user_preferences")
def fake_get_user_preferences(user_id: str) -> str:
    """Return one stable preference result."""

    return f"User {user_id} preferences: 1. quiet keyboard"


def _policy(
    *,
    parallel_enabled: bool,
    max_workers: int = 2,
    task_retry_policy: AgentTaskRetryPolicy | None = None,
) -> RuntimePolicy:
    return RuntimePolicy(
        agent_task_retry_policy=task_retry_policy or AgentTaskRetryPolicy(),
        metadata={
            "parallel_read_enabled": parallel_enabled,
            "parallel_read_max_workers": max_workers,
        }
    )


def _context(
    *,
    parallel_enabled: bool,
    max_workers: int = 2,
    max_steps: int | None = None,
    max_tool_calls: int | None = None,
    cancellation_requested: bool = False,
    task_retry_policy: AgentTaskRetryPolicy | None = None,
) -> RunContext:
    policy = _policy(
        parallel_enabled=parallel_enabled,
        max_workers=max_workers,
        task_retry_policy=task_retry_policy,
    )
    budget = RunBudget(max_steps=max_steps, max_tool_calls=max_tool_calls)
    request = RunRequest(
        operation="chat",
        user_id="USER-001",
        thread_id="THREAD-001",
        input_text=MESSAGE,
        policy=policy,
        budget=budget,
    )
    return RunContext(
        request=request,
        policy=policy,
        budget=budget,
        cancellation_requested=cancellation_requested,
    )


def _graph(
    context: RunContext,
    *,
    fail_rag: bool = False,
    cancel_after_product: Event | None = None,
    agent_planner=None,
):
    @tool("search_products")
    def fake_search_products(query: str, limit: int = 5) -> str:
        """Return one stable product result."""

        if cancel_after_product is not None:
            cancel_after_product.set()
        return "Found 1 product: Test Keyboard (TECH-KEY-001)."

    @tool("search_policy_docs")
    def fake_search_policy_docs(query: str) -> str:
        """Return a stable policy result or a controlled failure."""

        if fail_rag:
            raise RuntimeError("RAG backend unavailable")
        return "Return policy: returns accepted within 30 days."

    product_tools = tools_by_name(
        [
            guard_tool(
                "product_agent",
                fake_search_products,
                runtime_context=context,
            )
        ]
    )
    rag_tools = tools_by_name(
        [
            guard_tool(
                "rag_agent",
                fake_search_policy_docs,
                runtime_context=context,
            )
        ]
    )
    preference_tools = tools_by_name(
        [
            guard_tool(
                "preference_agent",
                fake_get_user_preferences,
                runtime_context=context,
            )
        ]
    )
    return create_shopmind_multi_agent_graph(
        product_tools=product_tools,
        rag_tools=rag_tools,
        preference_tools=preference_tools,
        agent_planner=agent_planner,
        runtime_context=context,
    )


def _invoke(
    context: RunContext,
    *,
    message: str = MESSAGE,
    fail_rag: bool = False,
    cancel_after_product: Event | None = None,
    agent_planner=None,
):
    return _graph(
        context,
        fail_rag=fail_rag,
        cancel_after_product=cancel_after_product,
        agent_planner=agent_planner,
    ).invoke(
        {
            "messages": [{"role": "user", "content": message}],
            "user_id": "USER-001",
            "thread_id": "THREAD-001",
            "tool_calls": [],
            "safety_flags": [],
            "agent_steps": [],
        }
    )


def test_opt_in_parallel_graph_matches_sequential_user_visible_result() -> None:
    sequential_context = _context(parallel_enabled=False)
    parallel_context = _context(parallel_enabled=True)

    sequential = _invoke(sequential_context)
    parallel = _invoke(parallel_context)

    assert sequential["execution_plan"]["execution_mode"] == "sequential"
    assert parallel["execution_plan"]["execution_mode"] == "bounded_parallel"
    assert parallel["execution_plan"]["max_parallelism"] == 2
    assert parallel["parallel_execution"]["status"] == "completed"
    assert parallel["final_response"] == sequential["final_response"]
    assert parallel["tool_calls"] == sequential["tool_calls"]
    assert parallel["executed_routes"] == sequential["executed_routes"]
    assert parallel["product_summary"] == sequential["product_summary"]
    assert parallel["rag_summary"] == sequential["rag_summary"]
    assert parallel["preference_summary"] == sequential["preference_summary"]
    assert [step["node"] for step in parallel["agent_steps"]] == [
        "supervisor",
        "product_agent",
        "rag_agent",
        "preference_agent",
        "decision_agent",
    ]
    records = parallel_context.metadata_snapshot()["tool_call_records"]
    assert [record["audit_sequence"] for record in records] == [1, 2, 3]


def test_parallel_graph_returns_partial_result_when_one_read_fails() -> None:
    context = _context(parallel_enabled=True)

    result = _invoke(context, fail_rag=True)

    assert result["parallel_execution"]["status"] == "partial"
    assert result["parallel_execution"]["error_codes"] == ["plan.step_failed"]
    assert result["executed_routes"] == ["product_agent", "preference_agent"]
    assert result["decision"]["used_summaries"] == [
        "product_summary",
        "preference_summary",
    ]
    assert "rag_summary" not in result
    records = context.metadata_snapshot()["tool_call_records"]
    assert len(records) == 3
    assert sorted(record["status"] for record in records) == [
        "completed",
        "completed",
        "failed",
    ]


@pytest.mark.parametrize(
    "failure_mode",
    ["exception", "wrong_task_id", "typed_unavailable"],
)
def test_parallel_graph_sanitizes_policy_wrapped_transport_failures(
    monkeypatch,
    failure_mode: str,
) -> None:
    private_detail = "private remote endpoint: rag.internal"

    class FaultyRagTransport:
        agent_name = "rag_agent"

        def invoke(self, task):
            if failure_mode == "exception":
                raise RuntimeError(private_detail)
            if failure_mode == "typed_unavailable":
                raise AgentTransportError(
                    AgentTransportFailureCode.UNAVAILABLE,
                    retriable=True,
                    usage=RunUsage(total_tokens=4, step_count=1),
                )
            return AgentResult(
                task_id="wrong-task-id",
                status=AgentTaskStatus.COMPLETED,
                output_data={"private_detail": private_detail},
            )

    def create_faulty_rag_adapter(tools, delegation_guard):
        return PolicyEnforcedAgentAdapter(
            adapter=FaultyRagTransport(),
            delegation_guard=delegation_guard,
        )

    monkeypatch.setattr(
        "agents.shopmind_multi_agent.graph.create_rag_agent_adapter",
        create_faulty_rag_adapter,
    )
    context = _context(parallel_enabled=True)

    result = _invoke(context)

    assert result["parallel_execution"]["status"] == "partial"
    expected_error_code = (
        "agent.transport_unavailable"
        if failure_mode == "typed_unavailable"
        else "plan.step_failed"
    )
    assert result["parallel_execution"]["error_codes"] == [expected_error_code]
    assert result["executed_routes"] == ["product_agent", "preference_agent"]
    assert result["decision"]["used_summaries"] == [
        "product_summary",
        "preference_summary",
    ]
    assert "rag_summary" not in result
    assert private_detail not in str(result)
    if failure_mode == "typed_unavailable":
        assert any(
            usage["total_tokens"] == 4
            for usage in result["delegated_usage"]
        )


def test_plan_owned_retry_replays_sequential_specialist_with_stable_identity(
    monkeypatch,
) -> None:
    attempts: list[tuple[str, str, str | None]] = []

    def create_flaky_rag_adapter(tools, delegation_guard):
        base_adapter = create_rag_agent_adapter(tools, delegation_guard)

        class FlakyRagTransport:
            agent_name = "rag_agent"

            def invoke(self, task):
                attempts.append((task.run_id, task.task_id, task.idempotency_key))
                assert task.retry_policy.owner == "plan_executor"
                assert task.retry_policy.max_attempts == 2
                if len(attempts) == 1:
                    raise AgentTransportError(
                        AgentTransportFailureCode.UNAVAILABLE,
                        retriable=True,
                        usage=RunUsage(total_tokens=4, step_count=1),
                    )
                return base_adapter.adapter.invoke(task)

        return PolicyEnforcedAgentAdapter(
            adapter=FlakyRagTransport(),
            delegation_guard=delegation_guard,
        )

    monkeypatch.setattr(
        "agents.shopmind_multi_agent.graph.create_rag_agent_adapter",
        create_flaky_rag_adapter,
    )
    retry_policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )
    context = _context(
        parallel_enabled=False,
        task_retry_policy=retry_policy,
    )

    result = _invoke(context)

    assert result["execution_plan"]["execution_mode"] == "sequential"
    assert result["parallel_execution"]["status"] == "completed"
    rag_status = next(
        item
        for item in result["parallel_execution"]["step_statuses"]
        if item["recipient"] == "rag_agent"
    )
    assert rag_status["attempt_count"] == 2
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert attempts[0][2] is not None
    rag_usage = result["delegated_usage"][1]
    assert rag_usage["total_tokens"] is None
    assert rag_usage["step_count"] == 1


def test_parallel_graph_enforces_shared_tool_budget_atomically() -> None:
    context = _context(parallel_enabled=True, max_workers=3, max_tool_calls=2)

    result = _invoke(context)

    assert result["parallel_execution"]["status"] == "partial"
    assert result["parallel_execution"]["error_codes"] == ["plan.step_failed"]
    assert len(result["executed_routes"]) == 2
    assert len(result["tool_calls"]) == 2
    metadata = context.metadata_snapshot()
    assert metadata["tool_gateway_call_count"] == 2
    assert len(metadata["tool_call_records"]) == 2
    assert [record["audit_sequence"] for record in metadata["tool_call_records"]] == [
        1,
        2,
    ]


def test_parallel_graph_enforces_shared_agent_step_budget_atomically() -> None:
    context = _context(parallel_enabled=True, max_workers=3, max_steps=2)

    result = _invoke(context)

    assert result["parallel_execution"]["status"] == "partial"
    assert result["parallel_execution"]["error_codes"] == [
        "plan.step_budget_exceeded"
    ]
    assert len(result["executed_routes"]) == 2
    assert len(result["tool_calls"]) == 2
    assert len(context.metadata_snapshot()["tool_call_records"]) == 2


def test_parallel_graph_honors_pre_execution_cancellation() -> None:
    context = _context(parallel_enabled=True, cancellation_requested=True)

    result = _invoke(context)

    assert result["parallel_execution"]["status"] == "failed"
    assert [
        item["status"] for item in result["parallel_execution"]["step_statuses"]
    ] == ["cancelled", "cancelled", "cancelled"]
    assert result["executed_routes"] == []
    assert result["tool_calls"] == []
    assert result["decision"]["answer_type"] == "insufficient_context"
    assert context.metadata_snapshot().get("tool_call_records", []) == []


def test_parallel_opt_in_keeps_single_route_on_sequential_path() -> None:
    context = _context(parallel_enabled=True, max_workers=3)

    result = _invoke(context, message="recommend a keyboard")

    assert result["routes"] == ["product_agent"]
    assert result["execution_plan"]["execution_mode"] == "sequential"
    assert result["execution_plan"]["max_parallelism"] == 1
    assert "parallel_execution" not in result
    assert result["tool_calls"] == ["search_products"]


def test_parallel_graph_cancels_queued_reads_and_emits_lifecycle_events() -> None:
    cancellation = Event()
    context = _context(parallel_enabled=True, max_workers=1)
    emitted: list[dict] = []
    context.bind_cancellation_check(cancellation.is_set)
    context.bind_event_emitter(lambda **event: emitted.append(event))

    result = _invoke(context, cancel_after_product=cancellation)

    assert result["parallel_execution"]["status"] == "partial"
    assert [
        item["status"] for item in result["parallel_execution"]["step_statuses"]
    ] == ["completed", "cancelled", "cancelled"]
    assert result["executed_routes"] == ["product_agent"]
    assert result["tool_calls"] == ["search_products"]
    assert result["decision"]["used_summaries"] == ["product_summary"]
    assert [event["event_type"] for event in emitted] == [
        "plan.execution.started",
        "plan.step.started",
        "plan.step.attempt.started",
        "plan.step.attempt.completed",
        "plan.step.completed",
        "plan.step.cancelled",
        "plan.step.cancelled",
        "plan.execution.completed",
    ]
    assert emitted[-1]["payload"] == {
        "plan_id": result["execution_plan"]["plan_id"],
        "status": "partial",
        "completed_step_count": 1,
        "cancelled_step_count": 2,
        "failed_step_count": 0,
    }


def test_compiled_graph_accepts_validated_planner_boundary() -> None:
    context = _context(parallel_enabled=False)
    planner = ValidatedProviderPlanner(
        lambda payload: payload["baseline_plan"],
        provider_type="test_provider",
    )

    result = _invoke(
        context,
        message="recommend a keyboard",
        agent_planner=planner,
    )

    assert result["execution_plan"]["planner_type"] == "validated_provider_plan"
    assert result["execution_plan"]["metadata"]["planner_provider"] == (
        "test_provider"
    )
    assert result["routes"] == ["product_agent"]
    assert result["tool_calls"] == ["search_products"]
