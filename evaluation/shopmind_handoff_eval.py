"""Offline V3 API handoff evaluation helpers."""

from __future__ import annotations

from typing import Any, Callable, NotRequired, TypedDict

from app.dependencies.agent import call_shopmind_agent, confirm_pending_action
from evaluation.shopmind_event_reporting import (
    EventSummary,
    format_event_summary,
    summarize_debug_events,
)


ChatFn = Callable[..., dict[str, Any]]
ConfirmFn = Callable[..., dict[str, Any]]


class HandoffEvalCase(TypedDict):
    name: str
    message: str
    user_id: NotRequired[str | None]
    thread_id: NotRequired[str | None]
    confirm: NotRequired[bool | None]
    expected_chat_status: str
    expected_confirm_status: NotRequired[str]
    expected_chat_events: NotRequired[list[str]]
    expected_confirm_events: NotRequired[list[str]]


HANDOFF_EVAL_CASES: tuple[HandoffEvalCase, ...] = (
    {
        "name": "explicit_product_confirmed",
        "message": "add TECH-KEY-001 to cart quantity 2",
        "user_id": "HANDOFF-EVAL-USER",
        "thread_id": "handoff-eval-confirm",
        "confirm": True,
        "expected_chat_status": "confirmation_required",
        "expected_confirm_status": "completed",
        "expected_confirm_events": ["pending_action_confirmed"],
    },
    {
        "name": "missing_product_clarification",
        "message": "add this keyboard to cart",
        "user_id": "HANDOFF-EVAL-USER",
        "thread_id": "handoff-eval-clarify",
        "confirm": None,
        "expected_chat_status": "completed",
        "expected_chat_events": ["candidate_context_stored"],
    },
)


def _event_names(output: dict[str, Any]) -> list[str]:
    event_summary = summarize_debug_events([output])
    return list(event_summary["event_counts"].keys())


def _missing_events(
    expected_events: list[str] | None,
    output: dict[str, Any],
) -> list[str]:
    if not expected_events:
        return []
    actual_events = set(_event_names(output))
    return [event for event in expected_events if event not in actual_events]


def run_handoff_case(
    case: HandoffEvalCase,
    *,
    chat_fn: ChatFn = call_shopmind_agent,
    confirm_fn: ConfirmFn = confirm_pending_action,
) -> dict[str, Any]:
    """Run one chat/confirm handoff case using API-boundary dependency functions."""

    user_id = case.get("user_id")
    thread_id = case.get("thread_id")
    chat_output = chat_fn(
        message=case["message"],
        user_id=user_id,
        thread_id=thread_id,
    )
    outputs = [chat_output]
    failures: list[str] = []

    if chat_output.get("status") != case["expected_chat_status"]:
        failures.append(
            "chat status mismatch: "
            f"expected={case['expected_chat_status']} actual={chat_output.get('status')}"
        )
    missing_chat_events = _missing_events(case.get("expected_chat_events"), chat_output)
    if missing_chat_events:
        failures.append(f"missing chat events: {missing_chat_events}")

    confirm_output: dict[str, Any] | None = None
    should_confirm = case.get("confirm")
    if should_confirm is not None:
        pending_action_id = chat_output.get("pending_action_id")
        if not pending_action_id:
            failures.append("missing pending_action_id for confirmation step")
        else:
            confirm_output = confirm_fn(
                pending_action_id=str(pending_action_id),
                user_id=str(user_id or ""),
                confirmed=bool(should_confirm),
            )
            outputs.append(confirm_output)
            expected_confirm_status = case.get("expected_confirm_status")
            if (
                expected_confirm_status is not None
                and confirm_output.get("status") != expected_confirm_status
            ):
                failures.append(
                    "confirm status mismatch: "
                    f"expected={expected_confirm_status} "
                    f"actual={confirm_output.get('status')}"
                )
            missing_confirm_events = _missing_events(
                case.get("expected_confirm_events"),
                confirm_output,
            )
            if missing_confirm_events:
                failures.append(f"missing confirm events: {missing_confirm_events}")

    return {
        "case": case["name"],
        "passed": not failures,
        "failures": failures,
        "chat_output": chat_output,
        "confirm_output": confirm_output,
        "event_summary": summarize_debug_events(outputs),
    }


def evaluate_v3_handoff_target(
    *,
    cases: tuple[HandoffEvalCase, ...] = HANDOFF_EVAL_CASES,
    chat_fn: ChatFn = call_shopmind_agent,
    confirm_fn: ConfirmFn = confirm_pending_action,
) -> dict[str, Any]:
    """Run V3 API handoff cases and aggregate event metrics."""

    case_results = [
        run_handoff_case(case, chat_fn=chat_fn, confirm_fn=confirm_fn)
        for case in cases
    ]
    output_events = []
    for result in case_results:
        output_events.append(result["chat_output"])
        confirm_output = result.get("confirm_output")
        if isinstance(confirm_output, dict):
            output_events.append(confirm_output)

    passed_cases = sum(1 for result in case_results if result["passed"])
    return {
        "total_cases": len(case_results),
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(case_results) if case_results else 0.0,
        "event_summary": summarize_debug_events(output_events),
        "case_results": case_results,
        "failures": [
            {
                "case": result["case"],
                "failures": result["failures"],
            }
            for result in case_results
            if result["failures"]
        ],
    }


def format_handoff_summary(summary: dict[str, Any]) -> str:
    lines = [
        "ShopMind V3 API handoff eval",
        f"cases: {summary['passed_cases']}/{summary['total_cases']}",
        f"pass rate: {summary['pass_rate'] * 100:.1f}%",
        format_event_summary(summary["event_summary"]),
    ]
    if not summary["failures"]:
        lines.append("failures: none")
        return "\n".join(lines)

    lines.append("failures:")
    for failure in summary["failures"]:
        lines.append(f"- {failure['case']}: {failure['failures']}")
    return "\n".join(lines)


__all__ = [
    "HANDOFF_EVAL_CASES",
    "ChatFn",
    "ConfirmFn",
    "EventSummary",
    "HandoffEvalCase",
    "evaluate_v3_handoff_target",
    "format_handoff_summary",
    "run_handoff_case",
]
