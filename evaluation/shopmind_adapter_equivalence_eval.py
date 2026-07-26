"""Model-independent contract evaluation for local and HTTP Agent adapters."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypedDict

import httpx

from app.runtime import (
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentTransportError,
    AgentTransportFailureCode,
    HttpAgentAdapter,
    InProcessAgentAdapter,
    RunUsage,
    invoke_agent_adapter,
)


ENDPOINT = "https://specialists.eval.internal/v1/tasks"


class AdapterEquivalenceCase(TypedDict):
    name: str
    scenario: str
    expected_outcome: str


class AdapterEquivalenceResult(TypedDict):
    name: str
    scenario: str
    passed: bool
    checks_passed: int
    total_checks: int
    failures: list[str]
    outcome: dict[str, Any]


class AdapterEquivalenceSummary(TypedDict):
    schema_version: str
    evaluation: str
    total_cases: int
    passed_cases: int
    pass_rate: float
    total_checks: int
    passed_checks: int
    check_pass_rate: float
    failures: list[AdapterEquivalenceResult]
    results: list[AdapterEquivalenceResult]


ADAPTER_EQUIVALENCE_CASES: tuple[AdapterEquivalenceCase, ...] = (
    {
        "name": "local_http_success_contract",
        "scenario": "success_equivalence",
        "expected_outcome": "completed",
    },
    {
        "name": "http_timeout_contract",
        "scenario": "timeout",
        "expected_outcome": "agent.transport_timeout",
    },
    {
        "name": "http_unavailable_contract",
        "scenario": "unavailable",
        "expected_outcome": "agent.transport_unavailable",
    },
    {
        "name": "http_protocol_contract",
        "scenario": "malformed",
        "expected_outcome": "agent.transport_protocol_error",
    },
    {
        "name": "http_response_bound_contract",
        "scenario": "oversized",
        "expected_outcome": "agent.transport_protocol_error",
    },
)


def _task() -> AgentTask:
    return AgentTask(
        task_id="eval-task-1",
        run_id="eval-run-1",
        sender="supervisor",
        recipient="rag_agent",
        intent="policy_read",
        input_data={"query": "return policy"},
        trace_id="eval-trace-1",
    )


def _specialist_handler(task: AgentTask) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        status=AgentTaskStatus.COMPLETED,
        output_data={"answer": "30 days", "source": "policy"},
        usage=RunUsage(total_tokens=8, tool_call_count=1, step_count=1),
        metadata={"schema": "rag.v1"},
    )


def _normalized_result(result: AgentResult) -> dict[str, Any]:
    return {
        "task_id": result.task_id,
        "status": result.status,
        "output_data": result.output_data,
        "evidence_references": [
            reference.model_dump(mode="json")
            for reference in result.evidence_references
        ],
        "usage": result.usage.model_dump(mode="json"),
        "error": result.error.model_dump(mode="json") if result.error else None,
        "child_trace_ids": result.child_trace_ids,
        "metadata": result.metadata,
    }


def _http_adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_response_bytes: int = 1_048_576,
) -> tuple[HttpAgentAdapter, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        HttpAgentAdapter(
            agent_name="rag_agent",
            endpoint_url=ENDPOINT,
            allowed_https_hosts=frozenset({"specialists.eval.internal"}),
            max_response_bytes=max_response_bytes,
            client=client,
        ),
        client,
    )


def replay_adapter_equivalence_case(
    case: AdapterEquivalenceCase,
) -> AdapterEquivalenceResult:
    task = _task()
    scenario = case["scenario"]
    checks: dict[str, bool]
    outcome: dict[str, Any]

    if scenario == "success_equivalence":
        local = invoke_agent_adapter(
            InProcessAgentAdapter("rag_agent", _specialist_handler),
            task,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            remote_task = AgentTask.model_validate_json(request.content)
            remote_result = _specialist_handler(remote_task)
            return httpx.Response(
                200,
                content=remote_result.model_dump_json().encode("utf-8"),
            )

        adapter, client = _http_adapter(handler)
        try:
            remote = invoke_agent_adapter(adapter, task)
        finally:
            client.close()
        local_contract = _normalized_result(local)
        remote_contract = _normalized_result(remote)
        checks = {
            "same_contract": local_contract == remote_contract,
            "task_identity": remote.task_id == task.task_id,
            "typed_usage": remote.usage.step_count == 1,
            "expected_outcome": remote.status == case["expected_outcome"],
        }
        outcome = {
            "kind": "result",
            "status": remote.status,
            "same_contract": local_contract == remote_contract,
        }
    else:
        response_by_scenario = {
            "timeout": lambda: httpx.Response(504),
            "unavailable": lambda: httpx.Response(503),
            "malformed": lambda: httpx.Response(200, content=b"not-json"),
            "oversized": lambda: httpx.Response(200, content=b"x" * 9),
        }

        def handler(_request: httpx.Request) -> httpx.Response:
            return response_by_scenario[scenario]()

        adapter, client = _http_adapter(
            handler,
            max_response_bytes=8 if scenario == "oversized" else 1_048_576,
        )
        try:
            try:
                adapter.invoke(task)
            except AgentTransportError as error:
                outcome = {
                    "kind": "transport_error",
                    "failure_code": error.error_code,
                    "retriable": error.retriable,
                    "usage_step_count": error.usage.step_count,
                    "message": str(error),
                }
            else:
                outcome = {"kind": "unexpected_success"}
        finally:
            client.close()
        expected_retriable = scenario in {"timeout", "unavailable"}
        checks = {
            "typed_failure": outcome.get("kind") == "transport_error",
            "expected_outcome": (
                outcome.get("failure_code") == case["expected_outcome"]
            ),
            "retry_class": outcome.get("retriable") is expected_retriable,
            "attempt_accounted": outcome.get("usage_step_count") == 1,
            "sanitized": "specialists.eval.internal" not in str(outcome),
        }

    failures = [name for name, passed in checks.items() if not passed]
    return {
        "name": case["name"],
        "scenario": scenario,
        "passed": not failures,
        "checks_passed": sum(checks.values()),
        "total_checks": len(checks),
        "failures": failures,
        "outcome": outcome,
    }


def evaluate_adapter_equivalence(
    cases: Sequence[AdapterEquivalenceCase] = ADAPTER_EQUIVALENCE_CASES,
) -> AdapterEquivalenceSummary:
    results = [replay_adapter_equivalence_case(case) for case in cases]
    passed_cases = sum(result["passed"] for result in results)
    total_checks = sum(result["total_checks"] for result in results)
    passed_checks = sum(result["checks_passed"] for result in results)
    total_cases = len(results)
    return {
        "schema_version": "shopmind.adapter-equivalence-eval.v1",
        "evaluation": "shopmind_adapter_equivalence",
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / total_cases if total_cases else 1.0,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "check_pass_rate": passed_checks / total_checks if total_checks else 1.0,
        "failures": [result for result in results if not result["passed"]],
        "results": results,
    }


def format_adapter_equivalence_summary(
    summary: AdapterEquivalenceSummary,
) -> str:
    lines = [
        "# ShopMind Adapter Equivalence Evaluation",
        "",
        f"- cases: {summary['passed_cases']}/{summary['total_cases']}",
        f"- checks: {summary['passed_checks']}/{summary['total_checks']}",
        f"- pass rate: {summary['pass_rate']:.1%}",
    ]
    if summary["failures"]:
        lines.append("- failures: " + ", ".join(
            failure["name"] for failure in summary["failures"]
        ))
    else:
        lines.append("- failures: none")
    return "\n".join(lines)


__all__ = [
    "ADAPTER_EQUIVALENCE_CASES",
    "evaluate_adapter_equivalence",
    "format_adapter_equivalence_summary",
    "replay_adapter_equivalence_case",
]
