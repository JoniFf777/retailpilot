"""Isolated read-step state and deterministic graph-state fan-in."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.runtime import (
    AgentExecutionPlan,
    AgentPlanResult,
    AgentPlanStep,
    AgentPlanStepStatus,
)

from .planning import ROUTE_INTENTS
from .state import ShopMindMultiAgentState


SUMMARY_KEYS = {
    "product_agent": "product_summary",
    "rag_agent": "rag_summary",
    "preference_agent": "preference_summary",
}


class ParallelStateError(ValueError):
    """Raised when isolated state or fan-in data violates the plan boundary."""


def build_isolated_step_state(
    state: ShopMindMultiAgentState,
    step: AgentPlanStep,
) -> ShopMindMultiAgentState:
    """Copy only request identity and current-turn inputs into one read step."""

    if step.recipient not in ROUTE_INTENTS:
        raise ParallelStateError("Parallel state supports registered read routes only.")
    return {
        "messages": deepcopy(list(state.get("messages", []))),
        "user_id": state.get("user_id") or "",
        "thread_id": state.get("thread_id"),
        "intent": state.get("intent"),
        "current_route": step.recipient,
        "plan_step_id": step.step_id,
        "plan_step_retry_policy": step.retry_policy.model_dump(mode="python"),
        "executed_routes": [],
        "safety_flags": list(state.get("safety_flags", [])),
        "tool_calls": [],
        "agent_steps": [],
        "delegated_usage": [],
    }


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def merge_parallel_step_results(
    state: ShopMindMultiAgentState,
    plan: AgentExecutionPlan,
    plan_result: AgentPlanResult,
) -> dict[str, Any]:
    """Map typed fan-in output to stable graph fields using plan order."""

    if plan_result.plan_id != plan.plan_id:
        raise ParallelStateError("Plan result identity does not match the plan.")

    expected_step_ids = [step.step_id for step in plan.steps]
    result_by_id = {result.step_id: result for result in plan_result.step_results}
    if set(result_by_id) != set(expected_step_ids):
        raise ParallelStateError("Plan result steps do not match the execution plan.")
    if set(plan_result.output_data).difference(expected_step_ids):
        raise ParallelStateError("Plan result contains output for an unknown step.")

    merged: dict[str, Any] = {
        "executed_routes": [],
        "current_route": None,
        "tool_calls": [],
        "safety_flags": list(state.get("safety_flags", [])),
        "agent_steps": deepcopy(list(state.get("agent_steps", []))),
        "evidence_references": [
            reference.model_dump(mode="python")
            for reference in plan_result.evidence_references
        ],
        "delegated_usage": [
            step_result.usage.model_dump(mode="python")
            for step in plan.steps
            if (
                (step_result := result_by_id[step.step_id]).usage is not None
            )
        ],
        "parallel_execution": {
            "plan_id": plan.plan_id,
            "status": plan_result.status,
            "execution_mode": plan.execution_mode,
            "max_parallelism": plan.max_parallelism,
            "step_statuses": [
                {
                    "step_id": step.step_id,
                    "recipient": step.recipient,
                    "status": result_by_id[step.step_id].status,
                    "attempt_count": result_by_id[step.step_id].attempt_count,
                }
                for step in plan.steps
            ],
            "error_codes": [error.code for error in plan_result.errors],
        },
    }

    for step in plan.steps:
        step_result = result_by_id[step.step_id]
        if step_result.status != AgentPlanStepStatus.COMPLETED:
            continue
        output = plan_result.output_data.get(step.step_id, {})
        summary_key = SUMMARY_KEYS[step.recipient]
        if summary_key in output:
            merged[summary_key] = deepcopy(output[summary_key])
        merged["executed_routes"].append(step.recipient)
        merged["tool_calls"].extend(list(output.get("tool_calls", [])))
        _append_unique(merged["safety_flags"], list(output.get("safety_flags", [])))

        for agent_step in output.get("agent_steps", []):
            if not isinstance(agent_step, dict):
                continue
            normalized_step = deepcopy(agent_step)
            normalized_step.pop("index", None)
            merged["agent_steps"].append(
                {
                    "index": len(merged["agent_steps"]) + 1,
                    **normalized_step,
                    "plan_step_id": step.step_id,
                }
            )

    return merged


__all__ = [
    "ParallelStateError",
    "build_isolated_step_state",
    "merge_parallel_step_results",
]
