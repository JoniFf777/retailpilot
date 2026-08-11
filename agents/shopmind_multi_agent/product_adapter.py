"""Typed local adapter for the existing V3 product specialist."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.runtime import (
    AgentAdapter,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    DelegationBudgetGuard,
    InProcessAgentAdapter,
    PolicyEnforcedAgentAdapter,
    build_agent_task_idempotency_key,
    invoke_agent_adapter,
)
from app.runtime.contracts import AgentTaskRetryPolicy, MemoryReference, RunBudget

from .product_agent import product_agent_node
from .state import ShopMindMultiAgentState
from .supervisor import get_last_user_message


class ProductAgentTaskInput(BaseModel):
    message: str
    tool_calls: list[str] = Field(default_factory=list)
    executed_routes: list[str] = Field(default_factory=list)
    agent_steps: list[dict[str, Any]] = Field(default_factory=list)


class ProductAgentTaskOutput(BaseModel):
    product_summary: dict[str, Any]
    executed_routes: list[str]
    current_route: str | None = None
    tool_calls: list[str]
    agent_steps: list[dict[str, Any]]


def create_product_agent_adapter(
    tools: Mapping[str, Any] | Iterable[Any] | None = None,
    delegation_guard: DelegationBudgetGuard | None = None,
) -> PolicyEnforcedAgentAdapter:
    """Wrap the current product node without changing its tool behavior."""

    def handler(task: AgentTask) -> AgentResult:
        task_input = ProductAgentTaskInput.model_validate(task.input_data)
        node_result = product_agent_node(
            {
                "messages": [{"role": "user", "content": task_input.message}],
                "user_id": task.user_id or "",
                "thread_id": task.thread_id,
                "tool_calls": task_input.tool_calls,
                "executed_routes": task_input.executed_routes,
                "agent_steps": task_input.agent_steps,
            },
            tools=tools,
        )
        output = ProductAgentTaskOutput.model_validate(node_result)
        return AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
            output_data=output.model_dump(mode="python"),
            metadata={"adapter": "in_process", "agent": "product_agent"},
        )

    return PolicyEnforcedAgentAdapter(
        adapter=InProcessAgentAdapter(
            agent_name="product_agent",
            handler=handler,
        ),
        delegation_guard=delegation_guard or DelegationBudgetGuard(),
    )


def product_agent_adapter_node(
    state: ShopMindMultiAgentState,
    *,
    adapter: AgentAdapter,
    runtime_context: Any | None = None,
) -> dict[str, Any]:
    """Build a typed task from graph state and map the local result back."""

    budget = getattr(runtime_context, "budget", None) or RunBudget()
    context_references = getattr(runtime_context, "memory_references", [])
    task_id = state.get("plan_step_id") or str(uuid4())
    run_id = getattr(runtime_context, "run_id", None) or str(uuid4())
    task = AgentTask(
        task_id=task_id,
        run_id=run_id,
        thread_id=state.get("thread_id"),
        user_id=state.get("user_id"),
        sender="route_dispatcher",
        recipient="product_agent",
        intent="product_read",
        input_data=ProductAgentTaskInput(
            message=get_last_user_message(state),
            tool_calls=list(state.get("tool_calls", [])),
            executed_routes=list(state.get("executed_routes", [])),
            agent_steps=list(state.get("agent_steps", [])),
        ).model_dump(mode="python"),
        context_references=[
            reference
            if isinstance(reference, MemoryReference)
            else MemoryReference.model_validate(reference)
            for reference in context_references
        ],
        trace_id=getattr(runtime_context, "trace_id", None) or str(uuid4()),
        deadline_at=(
            getattr(getattr(runtime_context, "request", None), "deadline_at", None)
            or budget.deadline_at
        ),
        idempotency_key=build_agent_task_idempotency_key(run_id, task_id),
        budget=budget,
        retry_policy=AgentTaskRetryPolicy.model_validate(
            state.get("plan_step_retry_policy") or {}
        ),
        metadata={
            "adapter": "in_process",
            "graph_node": "product_agent",
            "plan_step_id": state.get("plan_step_id"),
        },
    )
    result = invoke_agent_adapter(adapter, task)
    node_output = ProductAgentTaskOutput.model_validate(result.output_data).model_dump(
        mode="python"
    )
    node_output["delegated_usage"] = [
        *state.get("delegated_usage", []),
        result.usage.model_dump(mode="python"),
    ]
    return node_output


__all__ = [
    "ProductAgentTaskInput",
    "ProductAgentTaskOutput",
    "create_product_agent_adapter",
    "product_agent_adapter_node",
]
