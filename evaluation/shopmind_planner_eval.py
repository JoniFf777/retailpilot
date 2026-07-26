"""Deterministic offline evaluation for the V5 planner policy boundary."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, NotRequired, TypedDict

from agents.shopmind_multi_agent.planning import (
    ValidatedProviderPlanner,
    build_deterministic_agent_plan,
)


PlannerScenario = Literal[
    "accepted",
    "route_injection",
    "dependency_injection",
    "parallelism_escalation",
    "execution_mode_escalation",
    "run_identity_spoof",
    "malformed_contract",
    "provider_error",
]


class PlannerEvalCase(TypedDict):
    name: str
    message: str
    routes: list[str]
    scenario: PlannerScenario
    expected_planner_type: str
    expected_provider_calls: int
    expected_execution_mode: str
    expected_max_parallelism: int
    parallel_enabled: NotRequired[bool]
    max_parallelism: NotRequired[int]
    expected_fallback_reason: NotRequired[str]
    expected_provider_skip: NotRequired[str]


class PlannerEvalCaseResult(TypedDict):
    name: str
    passed: bool
    checks_passed: int
    total_checks: int
    planner_type: str
    fallback_reason: str | None
    provider_calls: int
    failures: list[str]


class PlannerEvalSummary(TypedDict):
    schema_version: str
    evaluation: str
    total_cases: int
    passed_cases: int
    pass_rate: float
    total_checks: int
    passed_checks: int
    check_pass_rate: float
    failures: list[PlannerEvalCaseResult]
    results: list[PlannerEvalCaseResult]


PLANNER_EVAL_CASES: tuple[PlannerEvalCase, ...] = (
    {
        "name": "accepted_sequential",
        "message": "recommend a keyboard",
        "routes": ["product_agent"],
        "scenario": "accepted",
        "expected_planner_type": "validated_provider_plan",
        "expected_provider_calls": 1,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
    },
    {
        "name": "accepted_bounded_parallel",
        "message": "recommend a keyboard and check return policy",
        "routes": ["product_agent", "rag_agent"],
        "scenario": "accepted",
        "parallel_enabled": True,
        "max_parallelism": 2,
        "expected_planner_type": "validated_provider_plan",
        "expected_provider_calls": 1,
        "expected_execution_mode": "bounded_parallel",
        "expected_max_parallelism": 2,
    },
    {
        "name": "route_injection_fallback",
        "message": "recommend a keyboard",
        "routes": ["product_agent"],
        "scenario": "route_injection",
        "expected_planner_type": "provider_fallback",
        "expected_provider_calls": 1,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
        "expected_fallback_reason": "routes_outside_supervisor_decision",
    },
    {
        "name": "dependency_injection_fallback",
        "message": "recommend a keyboard and check return policy",
        "routes": ["product_agent", "rag_agent"],
        "scenario": "dependency_injection",
        "expected_planner_type": "provider_fallback",
        "expected_provider_calls": 1,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
        "expected_fallback_reason": "step_contract_outside_policy",
    },
    {
        "name": "parallelism_escalation_fallback",
        "message": "recommend a keyboard and check return policy",
        "routes": ["product_agent", "rag_agent"],
        "scenario": "parallelism_escalation",
        "parallel_enabled": True,
        "max_parallelism": 2,
        "expected_planner_type": "provider_fallback",
        "expected_provider_calls": 1,
        "expected_execution_mode": "bounded_parallel",
        "expected_max_parallelism": 2,
        "expected_fallback_reason": "parallelism_outside_policy",
    },
    {
        "name": "execution_mode_escalation_fallback",
        "message": "recommend a keyboard",
        "routes": ["product_agent"],
        "scenario": "execution_mode_escalation",
        "expected_planner_type": "provider_fallback",
        "expected_provider_calls": 1,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
        "expected_fallback_reason": "execution_mode_outside_policy",
    },
    {
        "name": "run_identity_spoof_fallback",
        "message": "recommend a keyboard",
        "routes": ["product_agent"],
        "scenario": "run_identity_spoof",
        "expected_planner_type": "provider_fallback",
        "expected_provider_calls": 1,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
        "expected_fallback_reason": "run_identity_mismatch",
    },
    {
        "name": "malformed_contract_fallback",
        "message": "recommend a keyboard",
        "routes": ["product_agent"],
        "scenario": "malformed_contract",
        "expected_planner_type": "provider_fallback",
        "expected_provider_calls": 1,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
        "expected_fallback_reason": "provider_error_or_invalid_contract",
    },
    {
        "name": "provider_error_fallback",
        "message": "recommend a keyboard",
        "routes": ["product_agent"],
        "scenario": "provider_error",
        "expected_planner_type": "provider_fallback",
        "expected_provider_calls": 1,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
        "expected_fallback_reason": "provider_error_or_invalid_contract",
    },
    {
        "name": "write_guard_skips_provider",
        "message": "add this keyboard to cart",
        "routes": [],
        "scenario": "provider_error",
        "expected_planner_type": "deterministic_route_plan",
        "expected_provider_calls": 0,
        "expected_execution_mode": "sequential",
        "expected_max_parallelism": 1,
        "expected_provider_skip": "no_read_routes",
    },
)


def _proposal_provider(
    scenario: PlannerScenario,
    calls: list[int],
):
    def provider(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        if scenario == "provider_error":
            raise RuntimeError("private planner provider detail")
        if scenario == "malformed_contract":
            return {"unexpected": "shape"}

        proposal = deepcopy(payload["baseline_plan"])
        if scenario == "route_injection":
            proposal["steps"][0]["recipient"] = "decision_agent"
        elif scenario == "dependency_injection":
            proposal["steps"][1]["depends_on"] = [proposal["steps"][0]["step_id"]]
        elif scenario == "parallelism_escalation":
            proposal["max_parallelism"] += 1
        elif scenario == "execution_mode_escalation":
            proposal["execution_mode"] = "bounded_parallel"
        elif scenario == "run_identity_spoof":
            proposal["run_id"] = "other-run"
        return proposal

    return provider


def _step_contract(plan: Any) -> list[tuple[Any, ...]]:
    return [
        (
            step.step_id,
            step.recipient,
            step.intent,
            list(step.depends_on),
            step.parallel_eligible,
        )
        for step in plan.steps
    ]


def run_planner_eval_case(case: PlannerEvalCase) -> PlannerEvalCaseResult:
    """Run one untrusted proposal through the production validator boundary."""

    run_id = f"planner-eval:{case['name']}"
    parallel_enabled = bool(case.get("parallel_enabled", False))
    max_parallelism = int(case.get("max_parallelism", 1))
    baseline = build_deterministic_agent_plan(
        case["routes"],
        run_id=run_id,
        parallel_enabled=parallel_enabled,
        max_parallelism=max_parallelism,
    )
    provider_calls: list[int] = []
    planner = ValidatedProviderPlanner(
        _proposal_provider(case["scenario"], provider_calls),
        provider_type="offline_eval_provider",
    )
    plan = planner.build_plan(
        case["routes"],
        message=case["message"],
        run_id=run_id,
        parallel_enabled=parallel_enabled,
        max_parallelism=max_parallelism,
    )

    checks = {
        "planner_type": plan.planner_type == case["expected_planner_type"],
        "fallback_reason": plan.metadata.get("planner_fallback_reason")
        == case.get("expected_fallback_reason"),
        "provider_calls": len(provider_calls) == case["expected_provider_calls"],
        "step_contract": _step_contract(plan) == _step_contract(baseline),
        "execution_mode": plan.execution_mode == case["expected_execution_mode"],
        "max_parallelism": plan.max_parallelism
        == case["expected_max_parallelism"],
        "provider_skip": plan.metadata.get("planner_provider_skipped")
        == case.get("expected_provider_skip"),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "name": case["name"],
        "passed": not failures,
        "checks_passed": sum(checks.values()),
        "total_checks": len(checks),
        "planner_type": plan.planner_type,
        "fallback_reason": plan.metadata.get("planner_fallback_reason"),
        "provider_calls": len(provider_calls),
        "failures": failures,
    }


def evaluate_planner_policy(
    cases: tuple[PlannerEvalCase, ...] = PLANNER_EVAL_CASES,
) -> PlannerEvalSummary:
    """Evaluate fixed planner safety trajectories without calling a model."""

    results = [run_planner_eval_case(case) for case in cases]
    passed_cases = sum(result["passed"] for result in results)
    total_checks = sum(result["total_checks"] for result in results)
    passed_checks = sum(result["checks_passed"] for result in results)
    return {
        "schema_version": "shopmind.planner-policy-eval.v1",
        "evaluation": "planner_policy",
        "total_cases": len(results),
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(results) if results else 0.0,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "check_pass_rate": passed_checks / total_checks if total_checks else 0.0,
        "failures": [result for result in results if not result["passed"]],
        "results": results,
    }


def format_planner_eval_summary(summary: PlannerEvalSummary) -> str:
    """Render a concise human-readable planner evaluation report."""

    lines = [
        "ShopMind V5 planner policy eval",
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
    "PLANNER_EVAL_CASES",
    "PlannerEvalCase",
    "PlannerEvalCaseResult",
    "PlannerEvalSummary",
    "evaluate_planner_policy",
    "format_planner_eval_summary",
    "run_planner_eval_case",
]
