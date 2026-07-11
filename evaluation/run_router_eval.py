"""Run offline ShopMind supervisor router evaluation.

Usage:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py

Optional:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py --router llm-fallback
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py --router llm --model openai:gpt-5-nano
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py --mode target
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py --mode handoff
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py --mode handoff --event-metrics
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable
from typing import Sequence

from evaluation.run_langsmith_eval import shopmind_v3_router_target
from evaluation.shopmind_handoff_eval import (
    evaluate_v3_handoff_target,
    format_handoff_summary,
)
from evaluation.shopmind_event_reporting import (
    format_event_metrics,
    format_event_summary,
    summarize_debug_events,
)
from evaluation.shopmind_evaluators import (
    debug_metadata_evaluator,
    expected_routes_evaluator,
    expected_keywords_evaluator,
    forbidden_tools_evaluator,
    pending_action_evaluator,
    status_evaluator,
)
from agents.shopmind_multi_agent.supervisor_router import (
    DeterministicSupervisorRouter,
    LLMSupervisorRouter,
    SupervisorRouter,
    create_supervisor_router,
)
from evaluation.shopmind_router_eval import RouterEvalSummary, evaluate_supervisor_router
from evaluation.shopmind_router_eval import ROUTER_EVAL_CASES, RouterEvalCase


TargetFn = Callable[[dict[str, Any]], dict[str, Any]]
TARGET_EVALUATORS = (
    status_evaluator,
    expected_routes_evaluator,
    debug_metadata_evaluator,
    forbidden_tools_evaluator,
    expected_keywords_evaluator,
    pending_action_evaluator,
)


def build_router(router_mode: str, model: str | None = None) -> SupervisorRouter:
    """Build a router for offline evaluation without surprising network calls."""
    if router_mode == "deterministic":
        return DeterministicSupervisorRouter()
    if router_mode == "llm-fallback":
        return LLMSupervisorRouter()
    return create_supervisor_router("llm", model=model)


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_summary(router_mode: str, summary: RouterEvalSummary) -> str:
    lines = [
        "ShopMind router eval",
        f"router: {router_mode}",
        f"cases: {summary['total']}",
        (
            "exact matches: "
            f"{summary['exact_matches']}/{summary['total']} "
            f"({_percent(summary['exact_match_rate'])})"
        ),
        (
            "fallbacks: "
            f"{summary['fallback_count']}/{summary['total']} "
            f"({_percent(summary['fallback_rate'])})"
        ),
    ]

    if not summary["failures"]:
        lines.append("failures: none")
        return "\n".join(lines)

    lines.append("failures:")
    for failure in summary["failures"]:
        lines.append(
            "- "
            f"{failure['name']}: expected={failure['expected_routes']} "
            f"actual={failure['actual_routes']} "
            f"missing={failure['missing_routes']} "
            f"unexpected={failure['unexpected_routes']}"
        )
    return "\n".join(lines)


def _reference_outputs_for_case(case: RouterEvalCase) -> dict[str, Any]:
    reference_outputs: dict[str, Any] = {
        "expected_routes": case["expected_routes"],
        "expected_status": "completed",
    }
    for key in (
        "expected_intent",
        "expected_answer_type",
        "expected_safety_flags",
        "forbidden_tools",
        "expected_keywords",
        "expected_pending_action_present",
    ):
        if key in case:
            reference_outputs[key] = case[key]
    return reference_outputs


def evaluate_v3_router_target(
    target_fn: TargetFn | None = None,
    cases: tuple[RouterEvalCase, ...] | None = None,
) -> dict[str, Any]:
    """Run the local V3 router target and its rule-based evaluators."""
    active_target = target_fn or shopmind_v3_router_target
    active_cases = cases or ROUTER_EVAL_CASES
    failures: list[dict[str, Any]] = []
    evaluator_totals = {evaluator.__name__: 0 for evaluator in TARGET_EVALUATORS}
    evaluator_passes = {evaluator.__name__: 0 for evaluator in TARGET_EVALUATORS}
    outputs_for_event_summary: list[dict[str, Any]] = []

    for case in active_cases:
        inputs = {
            **({"user_id": case.get("user_id")} if case.get("user_id") else {}),
            "message": case["message"],
            "include_debug": True,
        }
        reference_outputs = _reference_outputs_for_case(case)
        outputs = active_target(inputs)
        outputs_for_event_summary.append(outputs)

        for evaluator in TARGET_EVALUATORS:
            result = evaluator(inputs, outputs, reference_outputs)
            evaluator_name = evaluator.__name__
            evaluator_totals[evaluator_name] += 1
            if result["score"]:
                evaluator_passes[evaluator_name] += 1
            else:
                failures.append(
                    {
                        "case": case["name"],
                        "evaluator": result["key"],
                        "comment": result["comment"],
                    }
                )

    total_checks = sum(evaluator_totals.values())
    passed_checks = sum(evaluator_passes.values())
    return {
        "total_cases": len(active_cases),
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "pass_rate": passed_checks / total_checks if total_checks else 0.0,
        "evaluator_passes": evaluator_passes,
        "evaluator_totals": evaluator_totals,
        "event_summary": summarize_debug_events(outputs_for_event_summary),
        "failures": failures,
    }


def format_target_summary(summary: dict[str, Any]) -> str:
    lines = [
        "ShopMind V3 router target eval",
        f"cases: {summary['total_cases']}",
        (
            "checks: "
            f"{summary['passed_checks']}/{summary['total_checks']} "
            f"({_percent(summary['pass_rate'])})"
        ),
    ]
    for evaluator_name, passed in summary["evaluator_passes"].items():
        total = summary["evaluator_totals"][evaluator_name]
        lines.append(f"{evaluator_name}: {passed}/{total}")

    event_summary = summary.get("event_summary")
    if isinstance(event_summary, dict):
        lines.append(format_event_summary(event_summary))

    if not summary["failures"]:
        lines.append("failures: none")
        return "\n".join(lines)

    lines.append("failures:")
    for failure in summary["failures"]:
        lines.append(
            "- "
            f"{failure['case']} {failure['evaluator']}: {failure['comment']}"
        )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixed offline route checks for the ShopMind supervisor."
    )
    parser.add_argument(
        "--mode",
        choices=["router", "target", "handoff"],
        default="router",
        help=(
            "router checks supervisor route decisions only; target invokes the "
            "V3 multi-agent target and runs rule-based evaluators; handoff "
            "runs API-boundary chat/confirm handoff cases."
        ),
    )
    parser.add_argument(
        "--router",
        choices=["deterministic", "llm-fallback", "llm"],
        default="deterministic",
        help=(
            "Router to evaluate. The llm mode may call the configured model; "
            "llm-fallback never calls a model."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model name for --router llm, e.g. openai:gpt-5-nano.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw evaluation summary as JSON.",
    )
    parser.add_argument(
        "--event-metrics",
        action="store_true",
        help=(
            "Print Prometheus-style V3 debug event metrics for target or "
            "handoff mode."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "handoff":
        summary = evaluate_v3_handoff_target()
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        elif args.event_metrics:
            print(format_event_metrics(summary["event_summary"]))
        else:
            print(format_handoff_summary(summary))
        return 0

    if args.mode == "target":
        summary = evaluate_v3_router_target()
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        elif args.event_metrics:
            print(format_event_metrics(summary["event_summary"]))
        else:
            print(format_target_summary(summary))
        return 0

    router = build_router(args.router, model=args.model)
    summary = evaluate_supervisor_router(router=router)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_summary(args.router, summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
