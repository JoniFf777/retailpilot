import pytest

from agents.shopmind_multi_agent.parallel_state import (
    ParallelStateError,
    build_isolated_step_state,
    merge_parallel_step_results,
)
from agents.shopmind_multi_agent.planning import build_deterministic_agent_plan
from app.runtime import (
    AgentPlanStep,
    AgentResult,
    AgentTaskStatus,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTransportFailureCode,
    BoundedPlanExecutor,
    MemoryReference,
    RunUsage,
)


def test_isolated_step_state_does_not_share_mutable_agent_state() -> None:
    state = {
        "messages": [{"role": "user", "content": "compare keyboards"}],
        "user_id": "user-1",
        "thread_id": "thread-1",
        "intent": "read_path",
        "product_summary": {"summary": "old product"},
        "executed_routes": ["product_agent"],
        "tool_calls": ["search_products"],
        "safety_flags": ["existing_flag"],
        "agent_steps": [{"index": 1, "node": "supervisor"}],
    }
    step = AgentPlanStep(
        step_id="read-1-rag_agent",
        recipient="rag_agent",
        intent="document_retrieval",
        retry_policy=AgentTaskRetryPolicy(
            owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
            max_attempts=2,
            retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
        ),
    )

    isolated = build_isolated_step_state(state, step)
    isolated["messages"][0]["content"] = "changed"
    isolated["safety_flags"].append("step_flag")

    assert state["messages"][0]["content"] == "compare keyboards"
    assert state["safety_flags"] == ["existing_flag"]
    assert isolated["user_id"] == "user-1"
    assert isolated["thread_id"] == "thread-1"
    assert isolated["current_route"] == "rag_agent"
    assert isolated["plan_step_id"] == "read-1-rag_agent"
    assert isolated["plan_step_retry_policy"]["owner"] == "plan_executor"
    assert isolated["plan_step_retry_policy"]["max_attempts"] == 2
    assert isolated["executed_routes"] == []
    assert isolated["tool_calls"] == []
    assert isolated["agent_steps"] == []
    assert "product_summary" not in isolated


def test_parallel_fan_in_maps_outputs_in_plan_order() -> None:
    plan = build_deterministic_agent_plan(
        ["product_agent", "rag_agent", "preference_agent"],
        run_id="run-1",
    )
    outputs = {
        "product_agent": {
            "product_summary": {"summary": "product"},
            "tool_calls": ["search_products"],
            "agent_steps": [{"index": 1, "node": "product_agent"}],
        },
        "rag_agent": {
            "rag_summary": {"summary": "document"},
            "tool_calls": ["search_product_docs"],
            "safety_flags": ["rag_flag"],
            "agent_steps": [{"index": 1, "node": "rag_agent"}],
        },
        "preference_agent": {
            "preference_summary": {"summary": "preference"},
            "tool_calls": ["get_user_preferences"],
            "agent_steps": [{"index": 1, "node": "preference_agent"}],
        },
    }

    plan_result = BoundedPlanExecutor().execute(
        plan,
        lambda step: AgentResult(
            task_id=step.step_id,
            status=AgentTaskStatus.COMPLETED,
            output_data=outputs[step.recipient],
            evidence_references=(
                [
                    MemoryReference(
                        ref_id="doc-1",
                        ref_type="document",
                        scope="operational",
                    )
                ]
                if step.recipient == "rag_agent"
                else []
            ),
            usage=RunUsage(
                total_tokens={
                    "product_agent": 10,
                    "rag_agent": 20,
                    "preference_agent": 30,
                }[step.recipient]
            ),
        ),
    )
    merged = merge_parallel_step_results(
        {
            "safety_flags": ["existing_flag"],
            "agent_steps": [{"index": 1, "node": "supervisor"}],
        },
        plan,
        plan_result,
    )

    assert merged["executed_routes"] == [
        "product_agent",
        "rag_agent",
        "preference_agent",
    ]
    assert merged["tool_calls"] == [
        "search_products",
        "search_product_docs",
        "get_user_preferences",
    ]
    assert merged["safety_flags"] == ["existing_flag", "rag_flag"]
    assert [step["index"] for step in merged["agent_steps"]] == [1, 2, 3, 4]
    assert [step.get("plan_step_id") for step in merged["agent_steps"][1:]] == [
        "read-1-product_agent",
        "read-2-rag_agent",
        "read-3-preference_agent",
    ]
    assert merged["evidence_references"][0]["ref_id"] == "doc-1"
    assert merged["parallel_execution"]["status"] == "completed"
    assert [usage["total_tokens"] for usage in merged["delegated_usage"]] == [
        10,
        20,
        30,
    ]


def test_parallel_fan_in_rejects_plan_identity_mismatch() -> None:
    plan = build_deterministic_agent_plan(["product_agent"], run_id="run-1")
    result = BoundedPlanExecutor().execute(
        plan,
        lambda step: AgentResult(
            task_id=step.step_id,
            status=AgentTaskStatus.COMPLETED,
        ),
    ).model_copy(update={"plan_id": "wrong-plan"})

    with pytest.raises(ParallelStateError, match="identity"):
        merge_parallel_step_results({}, plan, result)
