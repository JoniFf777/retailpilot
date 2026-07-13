"""Run LangSmith evaluation for ShopMind.

Usage:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_langsmith_eval.py

Optional:
    INCLUDE_CORRECTNESS_EVALUATOR=true conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_langsmith_eval.py
    SHOPMIND_EVAL_TARGET=v3-router conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_langsmith_eval.py
    SHOPMIND_EVAL_TARGET=v3-handoff conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/run_langsmith_eval.py
"""

from __future__ import annotations

import os
from typing import Any

from langsmith.evaluation import evaluate

from agents.shopmind_multi_agent import (
    create_supervisor_router,
    invoke_shopmind_multi_agent,
)
from agents.shopmind_agent import invoke_shopmind_agent
from app.dependencies.agent import call_shopmind_agent, confirm_pending_action
from evaluation.create_shopmind_dataset import (
    DATASET_NAME,
    V3_HANDOFF_DATASET_NAME,
    V3_ROUTER_DATASET_NAME,
)
from evaluation.shopmind_event_reporting import summarize_debug_events
from evaluation.shopmind_api_handoff_smoke import cleanup_handoff_runtime_state
from evaluation.shopmind_evaluators import (
    correctness_evaluator,
    count_total_tool_calls_evaluator,
    debug_metadata_evaluator,
    expected_keywords_evaluator,
    expected_routes_evaluator,
    expected_tools_evaluator,
    forbidden_tools_evaluator,
    handoff_chat_status_evaluator,
    handoff_confirm_status_evaluator,
    handoff_debug_events_evaluator,
    pending_action_evaluator,
    status_evaluator,
)


V1_EVAL_TARGET = "v1"
V3_ROUTER_EVAL_TARGET = "v3-router"
V3_HANDOFF_EVAL_TARGET = "v3-handoff"
V3_HANDOFF_EVAL_USER_PREFIX = "HANDOFF-EVAL-"


def shopmind_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """LangSmith target function for ShopMind V1."""
    return invoke_shopmind_agent(
        message=inputs["message"],
        user_id=inputs.get("user_id"),
    )


def shopmind_v3_router_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """LangSmith target function for ShopMind V3 read-only router evaluation."""
    router_mode = os.getenv("SHOPMIND_SUPERVISOR_ROUTER", "deterministic")
    return invoke_shopmind_multi_agent(
        message=inputs["message"],
        user_id=inputs.get("user_id"),
        thread_id=inputs.get("thread_id"),
        supervisor_router=create_supervisor_router(router_mode),
    )


def shopmind_v3_handoff_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """LangSmith target function for ShopMind V3 API handoff evaluation."""
    user_id = inputs.get("user_id")
    thread_id = inputs.get("thread_id")
    cleanup_user_id = (
        str(user_id)
        if user_id and str(user_id).startswith(V3_HANDOFF_EVAL_USER_PREFIX)
        else None
    )
    if cleanup_user_id:
        cleanup_handoff_runtime_state([cleanup_user_id])

    try:
        chat_output = call_shopmind_agent(
            message=inputs["message"],
            user_id=user_id,
            thread_id=thread_id,
        )

        outputs = [chat_output]
        confirm_output: dict[str, Any] | None = None
        confirmation_error: str | None = None
        confirm = inputs.get("confirm")
        if confirm is not None:
            pending_action_id = chat_output.get("pending_action_id")
            if pending_action_id:
                confirm_output = confirm_pending_action(
                    pending_action_id=str(pending_action_id),
                    user_id=str(user_id or ""),
                    confirmed=bool(confirm),
                )
                outputs.append(confirm_output)
            else:
                confirmation_error = "missing_pending_action_id"

        return {
            "status": (
                confirm_output.get("status")
                if isinstance(confirm_output, dict)
                else chat_output.get("status")
            ),
            "chat_output": chat_output,
            "confirm_output": confirm_output,
            "confirmation_error": confirmation_error,
            "event_summary": summarize_debug_events(outputs),
        }
    finally:
        if cleanup_user_id:
            cleanup_handoff_runtime_state([cleanup_user_id])


def build_evaluators(
    include_correctness: bool = False,
    target: str = V1_EVAL_TARGET,
) -> list:
    """Build evaluator list for a ShopMind evaluation target."""
    if target == V3_HANDOFF_EVAL_TARGET:
        return [
            handoff_chat_status_evaluator,
            handoff_confirm_status_evaluator,
            handoff_debug_events_evaluator,
        ]

    if target == V3_ROUTER_EVAL_TARGET:
        return [
            status_evaluator,
            expected_routes_evaluator,
            debug_metadata_evaluator,
            forbidden_tools_evaluator,
            expected_keywords_evaluator,
            pending_action_evaluator,
        ]

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


def resolve_eval_config(target: str) -> dict[str, Any]:
    """Resolve LangSmith evaluate configuration for a ShopMind target."""
    if target == V3_HANDOFF_EVAL_TARGET:
        return {
            "target_fn": shopmind_v3_handoff_target,
            "dataset": V3_HANDOFF_DATASET_NAME,
            "experiment_prefix": "shopmind-v3-handoff",
            "description": (
                "ShopMind V3 API handoff evaluation for chat/confirm status "
                "and debug-event expectations."
            ),
        }

    if target == V3_ROUTER_EVAL_TARGET:
        return {
            "target_fn": shopmind_v3_router_target,
            "dataset": V3_ROUTER_DATASET_NAME,
            "experiment_prefix": "shopmind-v3-router",
            "description": (
                "ShopMind V3 read-only router evaluation for routes and "
                "debug metadata."
            ),
        }
    return {
        "target_fn": shopmind_target,
        "dataset": DATASET_NAME,
        "experiment_prefix": "shopmind-v1",
        "description": (
            "ShopMind V1 evaluation for tool calling, status, safety, "
            "and answer quality."
        ),
    }


def main() -> None:
    include_correctness = os.getenv("INCLUDE_CORRECTNESS_EVALUATOR", "").lower() in {
        "1",
        "true",
        "yes",
    }
    target = os.getenv("SHOPMIND_EVAL_TARGET", V1_EVAL_TARGET).strip().lower()
    if target not in {V1_EVAL_TARGET, V3_ROUTER_EVAL_TARGET, V3_HANDOFF_EVAL_TARGET}:
        target = V1_EVAL_TARGET
    eval_config = resolve_eval_config(target)

    results = evaluate(
        eval_config["target_fn"],
        data=eval_config["dataset"],
        evaluators=build_evaluators(
            include_correctness=include_correctness,
            target=target,
        ),
        experiment_prefix=eval_config["experiment_prefix"],
        description=eval_config["description"],
        max_concurrency=1,
    )
    print(results)


if __name__ == "__main__":
    main()
