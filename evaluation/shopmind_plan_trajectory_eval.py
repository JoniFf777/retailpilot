"""Model-independent replay evaluation for graph plan execution trajectories."""

from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
from datetime import timedelta
from threading import Event
from typing import Any, Literal, NotRequired, TypedDict
from unittest.mock import patch

from langchain_core.tools import tool
from langsmith import tracing_context

from agents.shopmind_multi_agent import create_shopmind_multi_agent_graph
from agents.shopmind_multi_agent.permissions import guard_tool, tools_by_name
from agents.shopmind_multi_agent.rag_adapter import create_rag_agent_adapter
from app.runtime import (
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
from app.runtime.contracts import utc_now


EVAL_MESSAGE = "recommend a keyboard with return policy based on my preference"

TrajectoryScenario = Literal[
    "completed",
    "partial_failure",
    "shared_budget",
    "shared_step_budget",
    "pre_cancelled",
    "cooperative_cancelled",
    "expired_deadline",
    "expired_duration",
    "retry_success",
    "retry_exhausted",
    "retry_non_retriable",
    "retry_budget_blocked",
    "retry_cancelled",
]


class PlanTrajectoryCase(TypedDict):
    name: str
    scenario: TrajectoryScenario
    max_workers: int
    max_steps: int | None
    max_tool_calls: int | None
    expected_status: str
    expected_step_status_counts: dict[str, int]
    expected_route_count: int
    expected_tool_call_count: int
    expected_tool_record_count: int
    expected_gateway_call_count: int
    expected_error_counts: dict[str, int]
    expected_summary_count: int
    message: NotRequired[str]
    parallel_enabled: NotRequired[bool]
    max_attempts: NotRequired[int]
    max_total_tokens: NotRequired[int | None]
    expected_execution_mode: NotRequired[str]
    expected_attempt_sequence: NotRequired[list[str]]
    expected_attempt_count: NotRequired[int]


class PlanTrajectoryCaseResult(TypedDict):
    name: str
    scenario: TrajectoryScenario
    passed: bool
    checks_passed: int
    total_checks: int
    failures: list[str]
    trajectory: dict[str, Any]


class PlanTrajectorySummary(TypedDict):
    schema_version: str
    evaluation: str
    total_cases: int
    passed_cases: int
    pass_rate: float
    total_checks: int
    passed_checks: int
    check_pass_rate: float
    failures: list[PlanTrajectoryCaseResult]
    results: list[PlanTrajectoryCaseResult]


PLAN_TRAJECTORY_CASES: tuple[PlanTrajectoryCase, ...] = (
    {
        "name": "bounded_parallel_complete",
        "scenario": "completed",
        "max_workers": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_status": "completed",
        "expected_step_status_counts": {"completed": 3},
        "expected_route_count": 3,
        "expected_tool_call_count": 3,
        "expected_tool_record_count": 3,
        "expected_gateway_call_count": 3,
        "expected_error_counts": {},
        "expected_summary_count": 3,
    },
    {
        "name": "bounded_parallel_partial_failure",
        "scenario": "partial_failure",
        "max_workers": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_status": "partial",
        "expected_step_status_counts": {"completed": 2, "failed": 1},
        "expected_route_count": 2,
        "expected_tool_call_count": 2,
        "expected_tool_record_count": 3,
        "expected_gateway_call_count": 3,
        "expected_error_counts": {"plan.step_failed": 1},
        "expected_summary_count": 2,
    },
    {
        "name": "bounded_parallel_shared_budget",
        "scenario": "shared_budget",
        "max_workers": 3,
        "max_steps": None,
        "max_tool_calls": 2,
        "expected_status": "partial",
        "expected_step_status_counts": {"completed": 2, "failed": 1},
        "expected_route_count": 2,
        "expected_tool_call_count": 2,
        "expected_tool_record_count": 2,
        "expected_gateway_call_count": 2,
        "expected_error_counts": {"plan.step_failed": 1},
        "expected_summary_count": 2,
    },
    {
        "name": "bounded_parallel_shared_step_budget",
        "scenario": "shared_step_budget",
        "max_workers": 3,
        "max_steps": 2,
        "max_tool_calls": None,
        "expected_status": "partial",
        "expected_step_status_counts": {"completed": 2, "failed": 1},
        "expected_route_count": 2,
        "expected_tool_call_count": 2,
        "expected_tool_record_count": 2,
        "expected_gateway_call_count": 2,
        "expected_error_counts": {"plan.step_budget_exceeded": 1},
        "expected_summary_count": 2,
    },
    {
        "name": "bounded_parallel_pre_execution_cancellation",
        "scenario": "pre_cancelled",
        "max_workers": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_status": "failed",
        "expected_step_status_counts": {"cancelled": 3},
        "expected_route_count": 0,
        "expected_tool_call_count": 0,
        "expected_tool_record_count": 0,
        "expected_gateway_call_count": 0,
        "expected_error_counts": {"plan.step_cancelled": 3},
        "expected_summary_count": 0,
    },
    {
        "name": "bounded_parallel_cooperative_cancellation",
        "scenario": "cooperative_cancelled",
        "max_workers": 1,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_status": "partial",
        "expected_step_status_counts": {"cancelled": 2, "completed": 1},
        "expected_route_count": 1,
        "expected_tool_call_count": 1,
        "expected_tool_record_count": 1,
        "expected_gateway_call_count": 1,
        "expected_error_counts": {"plan.step_cancelled": 2},
        "expected_summary_count": 1,
    },
    {
        "name": "bounded_parallel_expired_deadline",
        "scenario": "expired_deadline",
        "max_workers": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_status": "failed",
        "expected_step_status_counts": {"failed": 3},
        "expected_route_count": 0,
        "expected_tool_call_count": 0,
        "expected_tool_record_count": 0,
        "expected_gateway_call_count": 0,
        "expected_error_counts": {"plan.deadline_exceeded": 3},
        "expected_summary_count": 0,
    },
    {
        "name": "bounded_parallel_expired_duration",
        "scenario": "expired_duration",
        "max_workers": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_status": "failed",
        "expected_step_status_counts": {"failed": 3},
        "expected_route_count": 0,
        "expected_tool_call_count": 0,
        "expected_tool_record_count": 0,
        "expected_gateway_call_count": 0,
        "expected_error_counts": {"plan.duration_budget_exceeded": 3},
        "expected_summary_count": 0,
    },
    {
        "name": "sequential_retry_success_after_unavailable",
        "scenario": "retry_success",
        "message": "what is the return policy",
        "parallel_enabled": False,
        "max_workers": 1,
        "max_attempts": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_execution_mode": "sequential",
        "expected_status": "completed",
        "expected_step_status_counts": {"completed": 1},
        "expected_route_count": 1,
        "expected_tool_call_count": 1,
        "expected_tool_record_count": 1,
        "expected_gateway_call_count": 1,
        "expected_error_counts": {},
        "expected_summary_count": 1,
        "expected_attempt_count": 2,
        "expected_attempt_sequence": [
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.retry.scheduled",
            "plan.step.retry.started",
            "plan.step.attempt.started",
            "plan.step.attempt.completed",
            "plan.step.retry.succeeded",
        ],
    },
    {
        "name": "sequential_retry_attempts_exhausted",
        "scenario": "retry_exhausted",
        "message": "what is the return policy",
        "parallel_enabled": False,
        "max_workers": 1,
        "max_attempts": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_execution_mode": "sequential",
        "expected_status": "failed",
        "expected_step_status_counts": {"failed": 1},
        "expected_route_count": 0,
        "expected_tool_call_count": 0,
        "expected_tool_record_count": 0,
        "expected_gateway_call_count": 0,
        "expected_error_counts": {"agent.transport_unavailable": 1},
        "expected_summary_count": 0,
        "expected_attempt_count": 2,
        "expected_attempt_sequence": [
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.retry.scheduled",
            "plan.step.retry.started",
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.attempt.exhausted",
        ],
    },
    {
        "name": "sequential_retry_non_retriable_failure",
        "scenario": "retry_non_retriable",
        "message": "what is the return policy",
        "parallel_enabled": False,
        "max_workers": 1,
        "max_attempts": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_execution_mode": "sequential",
        "expected_status": "failed",
        "expected_step_status_counts": {"failed": 1},
        "expected_route_count": 0,
        "expected_tool_call_count": 0,
        "expected_tool_record_count": 0,
        "expected_gateway_call_count": 0,
        "expected_error_counts": {"agent.transport_unavailable": 1},
        "expected_summary_count": 0,
        "expected_attempt_count": 1,
        "expected_attempt_sequence": [
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.retry.non_retriable",
        ],
    },
    {
        "name": "sequential_retry_usage_budget_blocked",
        "scenario": "retry_budget_blocked",
        "message": "what is the return policy",
        "parallel_enabled": False,
        "max_workers": 1,
        "max_attempts": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "max_total_tokens": 3,
        "expected_execution_mode": "sequential",
        "expected_status": "failed",
        "expected_step_status_counts": {"failed": 1},
        "expected_route_count": 0,
        "expected_tool_call_count": 0,
        "expected_tool_record_count": 0,
        "expected_gateway_call_count": 0,
        "expected_error_counts": {"plan.usage_budget_exceeded": 1},
        "expected_summary_count": 0,
        "expected_attempt_count": 1,
        "expected_attempt_sequence": [
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.retry.budget_blocked",
        ],
    },
    {
        "name": "sequential_retry_cancelled_before_replay",
        "scenario": "retry_cancelled",
        "message": "what is the return policy",
        "parallel_enabled": False,
        "max_workers": 1,
        "max_attempts": 2,
        "max_steps": None,
        "max_tool_calls": None,
        "expected_execution_mode": "sequential",
        "expected_status": "failed",
        "expected_step_status_counts": {"cancelled": 1},
        "expected_route_count": 0,
        "expected_tool_call_count": 0,
        "expected_tool_record_count": 0,
        "expected_gateway_call_count": 0,
        "expected_error_counts": {"plan.step_cancelled": 1},
        "expected_summary_count": 0,
        "expected_attempt_count": 1,
        "expected_attempt_sequence": [
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.retry.scheduled",
            "plan.step.retry.cancelled",
        ],
    },
)


def _sorted_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _build_context(case: PlanTrajectoryCase, cancellation: Event) -> RunContext:
    now = utc_now()
    max_attempts = case.get("max_attempts", 1)
    retry_policy = (
        AgentTaskRetryPolicy()
        if max_attempts == 1
        else AgentTaskRetryPolicy(
            owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
            max_attempts=max_attempts,
            retryable_failure_codes={
                AgentTransportFailureCode.UNAVAILABLE,
                AgentTransportFailureCode.TIMEOUT,
            },
        )
    )
    policy = RuntimePolicy(
        agent_task_retry_policy=retry_policy,
        metadata={
            "parallel_read_enabled": case.get("parallel_enabled", True),
            "parallel_read_max_workers": case["max_workers"],
        }
    )
    budget = RunBudget(
        max_steps=case["max_steps"],
        max_tool_calls=case["max_tool_calls"],
        max_total_tokens=case.get("max_total_tokens"),
        max_duration_ms=(
            1 if case["scenario"] == "expired_duration" else None
        ),
    )
    request = RunRequest(
        operation="chat",
        user_id="trajectory-eval-user",
        thread_id=f"trajectory-eval:{case['name']}",
        input_text=case.get("message", EVAL_MESSAGE),
        policy=policy,
        budget=budget,
        deadline_at=(
            now - timedelta(seconds=1)
            if case["scenario"] == "expired_deadline"
            else None
        ),
    )
    context = RunContext(
        request=request,
        policy=policy,
        budget=budget,
        cancellation_requested=case["scenario"] == "pre_cancelled",
        started_at=(
            now - timedelta(seconds=1)
            if case["scenario"] == "expired_duration"
            else now
        ),
    )
    if case["scenario"] in {"cooperative_cancelled", "retry_cancelled"}:
        context.bind_cancellation_check(cancellation.is_set)
    return context


def _faulty_rag_adapter_factory(
    case: PlanTrajectoryCase,
    cancellation: Event,
):
    def factory(tools, delegation_guard):
        base_adapter = create_rag_agent_adapter(tools, delegation_guard)

        class FaultInjectedRagTransport:
            agent_name = "rag_agent"

            def __init__(self) -> None:
                self.attempts = 0

            def invoke(self, task):
                self.attempts += 1
                scenario = case["scenario"]
                if scenario == "retry_success" and self.attempts > 1:
                    return base_adapter.adapter.invoke(task)
                if scenario == "retry_cancelled":
                    cancellation.set()
                raise AgentTransportError(
                    AgentTransportFailureCode.UNAVAILABLE,
                    retriable=scenario != "retry_non_retriable",
                    usage=RunUsage(total_tokens=4, step_count=1),
                )

        return PolicyEnforcedAgentAdapter(
            adapter=FaultInjectedRagTransport(),
            delegation_guard=delegation_guard,
        )

    return factory


def _invoke_case(
    case: PlanTrajectoryCase,
) -> tuple[dict[str, Any], RunContext, list[dict[str, Any]]]:
    cancellation = Event()
    context = _build_context(case, cancellation)
    emitted: list[dict[str, Any]] = []
    context.bind_event_emitter(lambda **event: emitted.append(event))

    @tool("search_products")
    def fake_search_products(query: str, limit: int = 5) -> str:
        """Return one stable product result."""

        if case["scenario"] == "cooperative_cancelled":
            cancellation.set()
        return "Found 1 product: Test Keyboard (TECH-KEY-001)."

    @tool("search_policy_docs")
    def fake_search_policy_docs(query: str) -> str:
        """Return one stable policy result or a controlled failure."""

        if case["scenario"] == "partial_failure":
            raise RuntimeError("private trajectory backend detail")
        return "Return policy: returns accepted within 30 days."

    @tool("get_user_preferences")
    def fake_get_user_preferences(user_id: str) -> str:
        """Return one stable preference result."""

        return f"User {user_id} preferences: quiet keyboard"

    fault_context = (
        patch(
            "agents.shopmind_multi_agent.graph.create_rag_agent_adapter",
            side_effect=_faulty_rag_adapter_factory(case, cancellation),
        )
        if case["scenario"].startswith("retry_")
        else nullcontext()
    )
    with fault_context:
        graph = create_shopmind_multi_agent_graph(
            product_tools=tools_by_name(
                [
                    guard_tool(
                        "product_agent",
                        fake_search_products,
                        runtime_context=context,
                    )
                ]
            ),
            rag_tools=tools_by_name(
                [
                    guard_tool(
                        "rag_agent",
                        fake_search_policy_docs,
                        runtime_context=context,
                    )
                ]
            ),
            preference_tools=tools_by_name(
                [
                    guard_tool(
                        "preference_agent",
                        fake_get_user_preferences,
                        runtime_context=context,
                    )
                ]
            ),
            runtime_context=context,
        )
        with tracing_context(enabled=False):
            result = graph.invoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": case.get("message", EVAL_MESSAGE),
                        }
                    ],
                    "user_id": context.user_id,
                    "thread_id": context.client_thread_id,
                    "tool_calls": [],
                    "safety_flags": [],
                    "agent_steps": [],
                }
            )
    return result, context, emitted


def _event_contract(
    emitted: list[dict[str, Any]],
    step_statuses: list[dict[str, Any]],
) -> tuple[bool, bool, dict[str, int]]:
    event_types = [str(event["event_type"]) for event in emitted]
    event_counts = _sorted_counts(event_types)
    step_status_counts = _sorted_counts(
        [str(item["status"]) for item in step_statuses]
    )
    expected_started = sum(int(item["attempt_count"]) > 0 for item in step_statuses)
    expected_attempts = sum(int(item["attempt_count"]) for item in step_statuses)
    valid = (
        bool(event_types)
        and event_types[0] == "plan.execution.started"
        and event_types[-1] == "plan.execution.completed"
        and event_counts.get("plan.execution.started") == 1
        and event_counts.get("plan.execution.completed") == 1
        and event_counts.get("plan.step.started", 0) == expected_started
        and event_counts.get("plan.step.completed", 0)
        == step_status_counts.get("completed", 0)
        and event_counts.get("plan.step.failed", 0)
        == step_status_counts.get("failed", 0)
        and event_counts.get("plan.step.cancelled", 0)
        == step_status_counts.get("cancelled", 0)
    )
    attempt_events = [
        event
        for event in emitted
        if str(event["event_type"]).startswith("plan.step.attempt.")
        or str(event["event_type"]).startswith("plan.step.retry.")
    ]
    terminal_attempt_count = sum(
        event_counts.get(event_type, 0)
        for event_type in (
            "plan.step.attempt.completed",
            "plan.step.attempt.failed",
            "plan.step.attempt.cancelled",
        )
    )
    attempt_payloads_valid = all(
        event.get("payload", {}).get("plan_id")
        and event.get("payload", {}).get("step_id")
        and event.get("payload", {}).get("recipient")
        and event.get("payload", {}).get("lifecycle")
        == str(event["event_type"]).removeprefix("plan.step.")
        and 1 <= int(event.get("payload", {}).get("attempt", 0)) <= 3
        for event in attempt_events
    )
    attempt_valid = (
        event_counts.get("plan.step.attempt.started", 0) == expected_attempts
        and terminal_attempt_count == expected_attempts
        and attempt_payloads_valid
    )
    return valid, attempt_valid, event_counts


def replay_plan_trajectory_case(
    case: PlanTrajectoryCase,
) -> PlanTrajectoryCaseResult:
    """Replay one fixed scenario through the production graph boundaries."""

    result, context, emitted = _invoke_case(case)
    execution = result["parallel_execution"]
    step_status_counts = _sorted_counts(
        [str(item["status"]) for item in execution["step_statuses"]]
    )
    error_counts = _sorted_counts(
        [str(code) for code in execution["error_codes"]]
    )
    metadata = context.metadata_snapshot()
    tool_records = list(metadata.get("tool_call_records", []))
    tool_record_status_counts = _sorted_counts(
        [str(record["status"]) for record in tool_records]
    )
    plan_routes = [
        step["recipient"] for step in result["execution_plan"]["steps"]
    ]
    route_positions = [
        plan_routes.index(route) for route in result["executed_routes"]
    ]
    fan_in_plan_order = route_positions == sorted(route_positions)
    step_statuses = list(execution["step_statuses"])
    event_contract, attempt_event_contract, event_counts = _event_contract(
        emitted,
        step_statuses,
    )
    rag_attempt_sequence = [
        str(event["event_type"])
        for event in emitted
        if event.get("agent_name") == "rag_agent"
        and (
            str(event["event_type"]).startswith("plan.step.attempt.")
            or str(event["event_type"]).startswith("plan.step.retry.")
        )
    ]
    attempt_counts = {
        str(item["recipient"]): int(item["attempt_count"])
        for item in step_statuses
    }
    gateway_call_count = int(metadata.get("tool_gateway_call_count", 0))
    max_tool_calls = case["max_tool_calls"]
    max_steps = case["max_steps"]
    budget_respected = (
        max_tool_calls is None or gateway_call_count <= max_tool_calls
    ) and (max_steps is None or gateway_call_count <= max_steps)
    trajectory = {
        "execution_mode": str(execution["execution_mode"]),
        "status": str(execution["status"]),
        "step_status_counts": step_status_counts,
        "executed_route_count": len(result["executed_routes"]),
        "fan_in_plan_order": fan_in_plan_order,
        "tool_call_count": len(result["tool_calls"]),
        "tool_record_count": len(tool_records),
        "tool_record_status_counts": tool_record_status_counts,
        "gateway_call_count": gateway_call_count,
        "error_counts": error_counts,
        "decision_summary_count": len(result["decision"]["used_summaries"]),
        "event_contract": event_contract,
        "attempt_event_contract": attempt_event_contract,
        "event_counts": event_counts,
        "rag_attempt_sequence": rag_attempt_sequence,
        "attempt_counts": attempt_counts,
        "budget_respected": budget_respected,
    }
    checks = {
        "execution_mode": trajectory["execution_mode"]
        == case.get("expected_execution_mode", "bounded_parallel"),
        "status": trajectory["status"] == case["expected_status"],
        "step_status_counts": step_status_counts
        == case["expected_step_status_counts"],
        "executed_route_count": trajectory["executed_route_count"]
        == case["expected_route_count"],
        "fan_in_plan_order": fan_in_plan_order,
        "tool_call_count": trajectory["tool_call_count"]
        == case["expected_tool_call_count"],
        "tool_record_count": trajectory["tool_record_count"]
        == case["expected_tool_record_count"],
        "gateway_call_count": gateway_call_count
        == case["expected_gateway_call_count"],
        "error_counts": error_counts == case["expected_error_counts"],
        "decision_summary_count": trajectory["decision_summary_count"]
        == case["expected_summary_count"],
        "event_contract": event_contract,
        "attempt_event_contract": attempt_event_contract,
        "attempt_sequence": (
            "expected_attempt_sequence" not in case
            or rag_attempt_sequence == case["expected_attempt_sequence"]
        ),
        "attempt_count": (
            "expected_attempt_count" not in case
            or attempt_counts.get("rag_agent") == case["expected_attempt_count"]
        ),
        "budget_respected": budget_respected,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "name": case["name"],
        "scenario": case["scenario"],
        "passed": not failures,
        "checks_passed": sum(checks.values()),
        "total_checks": len(checks),
        "failures": failures,
        "trajectory": trajectory,
    }


def evaluate_plan_trajectories(
    cases: tuple[PlanTrajectoryCase, ...] = PLAN_TRAJECTORY_CASES,
) -> PlanTrajectorySummary:
    """Replay fixed graph trajectories without a model or external service."""

    results = [replay_plan_trajectory_case(case) for case in cases]
    passed_cases = sum(result["passed"] for result in results)
    total_checks = sum(result["total_checks"] for result in results)
    passed_checks = sum(result["checks_passed"] for result in results)
    return {
        "schema_version": "shopmind.plan-trajectory-eval.v2",
        "evaluation": "plan_trajectory_replay",
        "total_cases": len(results),
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(results) if results else 0.0,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "check_pass_rate": passed_checks / total_checks if total_checks else 0.0,
        "failures": [result for result in results if not result["passed"]],
        "results": results,
    }


def format_plan_trajectory_summary(summary: PlanTrajectorySummary) -> str:
    """Render a concise graph trajectory replay report."""

    lines = [
        "ShopMind V5 plan trajectory replay eval",
        f"cases: {summary['passed_cases']}/{summary['total_cases']}",
        f"checks: {summary['passed_checks']}/{summary['total_checks']}",
    ]
    if not summary["failures"]:
        lines.append("failures: none")
        return "\n".join(lines)
    lines.append("failures:")
    for failure in summary["failures"]:
        lines.append(f"- {failure['name']}: {', '.join(failure['failures'])}")
    return "\n".join(lines)


__all__ = [
    "PLAN_TRAJECTORY_CASES",
    "PlanTrajectoryCase",
    "PlanTrajectoryCaseResult",
    "PlanTrajectorySummary",
    "evaluate_plan_trajectories",
    "format_plan_trajectory_summary",
    "replay_plan_trajectory_case",
]
