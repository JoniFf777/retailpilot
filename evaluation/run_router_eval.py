"""Run offline ShopMind supervisor router evaluation.

Usage:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py

Optional:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py --router llm-fallback
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_router_eval.py --router llm --model openai:gpt-5-nano
"""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from agents.shopmind_multi_agent.supervisor_router import (
    DeterministicSupervisorRouter,
    LLMSupervisorRouter,
    SupervisorRouter,
    create_supervisor_router,
)
from evaluation.shopmind_router_eval import RouterEvalSummary, evaluate_supervisor_router


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixed offline route checks for the ShopMind supervisor."
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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    router = build_router(args.router, model=args.model)
    summary = evaluate_supervisor_router(router=router)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_summary(args.router, summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
