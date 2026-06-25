"""Run LangSmith evaluation for ShopMind V1.

Usage:
    conda run -n pythonLearn python evaluation/run_langsmith_eval.py

Optional:
    INCLUDE_CORRECTNESS_EVALUATOR=true conda run -n pythonLearn python evaluation/run_langsmith_eval.py
"""

from __future__ import annotations

import os
from typing import Any

from langsmith.evaluation import evaluate

from agents.shopmind_agent import invoke_shopmind_agent
from evaluation.create_shopmind_dataset import DATASET_NAME
from evaluation.shopmind_evaluators import (
    correctness_evaluator,
    count_total_tool_calls_evaluator,
    expected_keywords_evaluator,
    expected_tools_evaluator,
    forbidden_tools_evaluator,
    status_evaluator,
)


def shopmind_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """LangSmith target function for ShopMind V1."""
    return invoke_shopmind_agent(
        message=inputs["message"],
        user_id=inputs.get("user_id"),
    )


def build_evaluators(include_correctness: bool = False) -> list:
    """Build evaluator list for ShopMind V1."""
    evaluators = [
        expected_tools_evaluator,
        forbidden_tools_evaluator,
        status_evaluator,
        expected_keywords_evaluator,
        count_total_tool_calls_evaluator,
    ]

    if include_correctness:
        evaluators.append(correctness_evaluator)

    return evaluators


def main() -> None:
    include_correctness = os.getenv("INCLUDE_CORRECTNESS_EVALUATOR", "").lower() in {
        "1",
        "true",
        "yes",
    }

    results = evaluate(
        shopmind_target,
        data=DATASET_NAME,
        evaluators=build_evaluators(include_correctness=include_correctness),
        experiment_prefix="shopmind-v1",
        description="ShopMind V1 evaluation for tool calling, status, safety, and answer quality.",
        max_concurrency=1,
    )
    print(results)


if __name__ == "__main__":
    main()

