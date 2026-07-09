"""Rule-based LangSmith evaluators for ShopMind V1.

These evaluators are intentionally deterministic and cheap. They validate
tool-calling expectations, forbidden sensitive tools, response status, and
answer keywords without calling an LLM.
"""

from typing import Any

from evaluators.evaluators import (
    correctness_evaluator,
    count_total_tool_calls_evaluator,
)
from evaluation.shopmind_router_eval import expected_routes_evaluator


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def expected_tools_evaluator(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """Check whether all expected tools appear in outputs["tool_calls"]."""
    expected_tools = _as_list(reference_outputs.get("expected_tools"))
    actual_tools = _as_list(outputs.get("tool_calls"))

    missing_tools = [tool for tool in expected_tools if tool not in actual_tools]
    score = not missing_tools

    return {
        "key": "expected_tools",
        "score": score,
        "comment": (
            "All expected tools were called."
            if score
            else f"Missing expected tools: {', '.join(missing_tools)}. Actual tools: {actual_tools}"
        ),
    }


def forbidden_tools_evaluator(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """Check that no forbidden tools appear in outputs["tool_calls"]."""
    forbidden_tools = _as_list(reference_outputs.get("forbidden_tools"))
    actual_tools = _as_list(outputs.get("tool_calls"))

    appeared_tools = [tool for tool in forbidden_tools if tool in actual_tools]
    score = not appeared_tools

    return {
        "key": "forbidden_tools",
        "score": score,
        "comment": (
            "No forbidden tools were called."
            if score
            else f"Forbidden tools appeared: {', '.join(appeared_tools)}. Actual tools: {actual_tools}"
        ),
    }


def status_evaluator(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """Check whether outputs["status"] matches reference_outputs["expected_status"]."""
    expected_status = reference_outputs.get("expected_status")
    actual_status = outputs.get("status")
    score = expected_status == actual_status

    return {
        "key": "status",
        "score": score,
        "comment": (
            f"Status matched: {actual_status}."
            if score
            else f"Expected status {expected_status!r}, got {actual_status!r}."
        ),
    }


def expected_keywords_evaluator(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """Check whether all expected keywords appear in outputs["answer"]."""
    expected_keywords = _as_list(reference_outputs.get("expected_keywords"))
    answer = str(outputs.get("answer") or "")

    missing_keywords = [
        keyword for keyword in expected_keywords if keyword.lower() not in answer.lower()
    ]
    score = not missing_keywords

    return {
        "key": "expected_keywords",
        "score": score,
        "comment": (
            "All expected keywords were found."
            if score
            else f"Missing expected keywords: {', '.join(missing_keywords)}."
        ),
    }


__all__ = [
    "correctness_evaluator",
    "count_total_tool_calls_evaluator",
    "expected_tools_evaluator",
    "forbidden_tools_evaluator",
    "status_evaluator",
    "expected_keywords_evaluator",
    "expected_routes_evaluator",
]
