"""Deterministic evaluation for the generic pending-action lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import PendingAction, UserPreference
from app.repositories.cart import (
    cancel_pending_action,
    confirm_save_preference,
    prepare_save_preference,
    resolve_pending_action,
)
from app.runtime import RunOperation, RunRequest, ShopMindRuntimeHarness


class ActionLifecycleCase(TypedDict):
    name: str
    scenario: str
    expected_result: str
    expected_action_status: str
    expected_preference_count: int
    expected_preference_value: str | None
    expected_events: tuple[str, ...] | None


ACTION_LIFECYCLE_CASES: tuple[ActionLifecycleCase, ...] = (
    {"name": "preference_confirm", "scenario": "confirm", "expected_result": "confirmed", "expected_action_status": "confirmed", "expected_preference_count": 1, "expected_preference_value": "quiet keyboard", "expected_events": None},
    {"name": "preference_cancel", "scenario": "cancel", "expected_result": "cancelled", "expected_action_status": "cancelled", "expected_preference_count": 0, "expected_preference_value": None, "expected_events": None},
    {"name": "preference_expired", "scenario": "expired", "expected_result": "pending action expired", "expected_action_status": "expired", "expected_preference_count": 0, "expected_preference_value": None, "expected_events": None},
    {"name": "preference_cross_user", "scenario": "cross_user", "expected_result": "user mismatch", "expected_action_status": "pending", "expected_preference_count": 0, "expected_preference_value": None, "expected_events": None},
    {"name": "preference_cross_thread", "scenario": "cross_thread", "expected_result": "thread mismatch", "expected_action_status": "pending", "expected_preference_count": 0, "expected_preference_value": None, "expected_events": None},
    {"name": "preference_duplicate", "scenario": "duplicate", "expected_result": "pending action is not confirmable", "expected_action_status": "confirmed", "expected_preference_count": 1, "expected_preference_value": "quiet keyboard", "expected_events": None},
    {"name": "preference_handler_failure", "scenario": "malformed", "expected_result": "invalid pending action payload", "expected_action_status": "pending", "expected_preference_count": 0, "expected_preference_value": None, "expected_events": None},
    {"name": "preference_edited", "scenario": "edited", "expected_result": "confirmed", "expected_action_status": "confirmed", "expected_preference_count": 1, "expected_preference_value": "silent switches", "expected_events": ("action.resumed", "action.edited", "action.confirmed")},
    {"name": "preference_resumed", "scenario": "resumed", "expected_result": "confirmed", "expected_action_status": "confirmed", "expected_preference_count": 1, "expected_preference_value": "quiet keyboard", "expected_events": ("action.resumed", "action.confirmed")},
    {"name": "preference_replayed", "scenario": "replayed", "expected_result": "replayed", "expected_action_status": "confirmed", "expected_preference_count": 1, "expected_preference_value": "quiet keyboard", "expected_events": ("action.resumed", "action.confirmed", "run.replayed")},
)


def replay_action_lifecycle_case(case: ActionLifecycleCase) -> dict[str, Any]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    prepared = prepare_save_preference(
        session,
        user_id="eval-user",
        preference_type="style",
        preference_value="quiet keyboard",
        thread_id="eval-thread",
        expires_at=(
            datetime.now(timezone.utc) - timedelta(seconds=1)
            if case["scenario"] == "expired"
            else None
        ),
    )
    action_id = prepared["pending_action_id"]
    action = session.get(PendingAction, action_id)
    if case["scenario"] == "malformed":
        action.payload_json = {"preference_type": "style"}
    session.commit()
    observed_events: list[str] = []

    if case["scenario"] == "cancel":
        outcome = cancel_pending_action(session, action_id, "eval-user", "eval-thread")
    elif case["scenario"] == "cross_user":
        outcome = confirm_save_preference(session, action_id, "other-user", "eval-thread")
    elif case["scenario"] == "cross_thread":
        outcome = confirm_save_preference(session, action_id, "eval-user", "other-thread")
    elif case["scenario"] == "duplicate":
        confirm_save_preference(session, action_id, "eval-user", "eval-thread")
        outcome = confirm_save_preference(session, action_id, "eval-user", "eval-thread")
    elif case["scenario"] == "edited":
        resolved = resolve_pending_action(
            session, action_id, "eval-user", "eval-thread"
        )
        if resolved["status"] == "resolved":
            observed_events.append("action.resumed")
        outcome = confirm_save_preference(
            session,
            action_id,
            "eval-user",
            "eval-thread",
            updated_arguments={"preference_value": "silent switches"},
        )
        if outcome["status"] == "confirmed":
            observed_events.extend(("action.edited", "action.confirmed"))
    elif case["scenario"] == "resumed":
        session.close()
        session = session_factory()
        resolved = resolve_pending_action(
            session, action_id, "eval-user", "eval-thread"
        )
        if resolved["status"] == "resolved":
            observed_events.append("action.resumed")
        outcome = confirm_save_preference(
            session, action_id, "eval-user", "eval-thread"
        )
        if outcome["status"] == "confirmed":
            observed_events.append("action.confirmed")
    elif case["scenario"] == "replayed":
        session.close()
        execution_count = 0

        def executor(context) -> dict[str, Any]:
            nonlocal execution_count
            execution_count += 1
            operation_session = session_factory()
            try:
                resolved = resolve_pending_action(
                    operation_session, action_id, "eval-user", "eval-thread"
                )
                if resolved["status"] == "resolved":
                    context.emit_event(
                        "action.resumed",
                        payload={"action_id": action_id},
                    )
                confirmed = confirm_save_preference(
                    operation_session, action_id, "eval-user", "eval-thread"
                )
                operation_session.commit()
            finally:
                operation_session.close()
            if confirmed["status"] == "confirmed":
                context.emit_event(
                    "action.confirmed",
                    payload={"action_id": action_id},
                )
            return {
                "answer": confirmed.get("message", ""),
                "status": "completed",
                "tool_calls": [],
                "pending_action_id": action_id,
            }

        harness = ShopMindRuntimeHarness(session_factory=session_factory)
        request = RunRequest(
            operation=RunOperation.CONFIRM_PENDING_ACTION,
            user_id="eval-user",
            input_data={
                "pending_action_id": action_id,
                "confirmed": True,
                "thread_id": "eval-thread",
            },
            idempotency_key="eval-action-replay",
        )
        first = harness.run(request, executor)
        replay = harness.run(request, executor)
        observed_events = [
            event.event_type
            for event in (*first.events, *replay.events)
            if event.event_type.startswith("action.")
            or event.event_type == "run.replayed"
        ]
        outcome = {
            "status": (
                "replayed"
                if replay.metadata.get("idempotency_replayed")
                and execution_count == 1
                else "error"
            )
        }
        session = session_factory()
    else:
        outcome = confirm_save_preference(session, action_id, "eval-user", "eval-thread")
    session.commit()

    action_status = session.get(PendingAction, action_id).status
    preferences = session.scalars(select(UserPreference)).all()
    preference_count = len(preferences)
    preference_value = (
        preferences[0].preference_value if preferences else None
    )
    result_value = outcome.get("message") if outcome["status"] == "error" else outcome["status"]
    checks = {
        "result": result_value == case["expected_result"],
        "action_status": action_status == case["expected_action_status"],
        "preference_count": preference_count == case["expected_preference_count"],
        "preference_value": preference_value == case["expected_preference_value"],
        "event_trajectory": (
            case["expected_events"] is None
            or tuple(observed_events) == case["expected_events"]
        ),
        "action_identity": bool(action_id),
    }
    session.close()
    engine.dispose()
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "name": case["name"],
        "scenario": case["scenario"],
        "passed": not failures,
        "checks_passed": sum(checks.values()),
        "total_checks": len(checks),
        "failures": failures,
        "outcome": {
            "result": result_value,
            "action_status": action_status,
            "preference_count": preference_count,
            "preference_value": preference_value,
            "events": observed_events,
        },
    }


def evaluate_action_lifecycle(
    cases: Sequence[ActionLifecycleCase] = ACTION_LIFECYCLE_CASES,
) -> dict[str, Any]:
    results = [replay_action_lifecycle_case(case) for case in cases]
    total_checks = sum(result["total_checks"] for result in results)
    passed_checks = sum(result["checks_passed"] for result in results)
    passed_cases = sum(result["passed"] for result in results)
    return {
        "schema_version": "shopmind.action-lifecycle-eval.v2",
        "evaluation": "shopmind_action_lifecycle",
        "total_cases": len(results),
        "passed_cases": passed_cases,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "failures": [result for result in results if not result["passed"]],
        "results": results,
    }


def format_action_lifecycle_summary(summary: dict[str, Any]) -> str:
    failures = ", ".join(item["name"] for item in summary["failures"]) or "none"
    return "\n".join((
        "# ShopMind Action Lifecycle Evaluation",
        "",
        f"- cases: {summary['passed_cases']}/{summary['total_cases']}",
        f"- checks: {summary['passed_checks']}/{summary['total_checks']}",
        f"- failures: {failures}",
    ))
