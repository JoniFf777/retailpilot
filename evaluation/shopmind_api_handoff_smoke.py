"""Run production-like ShopMind V3 API handoff smoke checks.

Usage:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/shopmind_api_handoff_smoke.py

Optional:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/shopmind_api_handoff_smoke.py --json
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/shopmind_api_handoff_smoke.py --case explicit_product_confirmed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Protocol, Sequence, TypedDict

from evaluation.shopmind_event_reporting import (
    format_event_summary,
    summarize_debug_events,
)


class ApiHandoffSmokeCase(TypedDict):
    name: str
    user_id: str
    thread_id: str
    messages: tuple[str, ...]
    expected_chat_statuses: tuple[str, ...]
    confirm: bool | None
    expected_confirm_status: str | None
    expected_events: tuple[str, ...]


class ResponseLike(Protocol):
    status_code: int
    text: str

    def json(self) -> dict[str, Any]: ...


class AsyncPostClient(Protocol):
    async def post(self, path: str, json: dict[str, Any]) -> ResponseLike: ...


API_HANDOFF_SMOKE_CASES: tuple[ApiHandoffSmokeCase, ...] = (
    {
        "name": "explicit_product_confirmed",
        "user_id": "API-HANDOFF-SMOKE-CONFIRM",
        "thread_id": "api-handoff-smoke-confirm",
        "messages": ("add to cart TECH-KEY-010 quantity 2",),
        "expected_chat_statuses": ("confirmation_required",),
        "confirm": True,
        "expected_confirm_status": "completed",
        "expected_events": ("pending_action_confirmed",),
    },
    {
        "name": "explicit_product_cancelled",
        "user_id": "API-HANDOFF-SMOKE-CANCEL",
        "thread_id": "api-handoff-smoke-cancel",
        "messages": ("add to cart TECH-KEY-010 quantity 1",),
        "expected_chat_statuses": ("confirmation_required",),
        "confirm": False,
        "expected_confirm_status": "cancelled",
        "expected_events": ("pending_action_cancelled",),
    },
    {
        "name": "candidate_selection_confirmed",
        "user_id": "API-HANDOFF-SMOKE-CANDIDATE",
        "thread_id": "api-handoff-smoke-candidate",
        "messages": ("add to cart keyboard quantity 2", "1"),
        "expected_chat_statuses": ("completed", "confirmation_required"),
        "confirm": True,
        "expected_confirm_status": "completed",
        "expected_events": (
            "candidate_context_stored",
            "candidate_context_selected",
            "candidate_context_cleared",
            "pending_action_confirmed",
        ),
    },
)


def _smoke_user_ids(cases: Sequence[ApiHandoffSmokeCase]) -> list[str]:
    return sorted({case["user_id"] for case in cases})


def cleanup_api_handoff_smoke_state(
    cases: Sequence[ApiHandoffSmokeCase] = API_HANDOFF_SMOKE_CASES,
    *,
    session_factory: Any | None = None,
) -> dict[str, int]:
    """Delete runtime state owned by the fixed API handoff smoke users."""
    return cleanup_handoff_runtime_state(
        _smoke_user_ids(cases),
        session_factory=session_factory,
    )


def cleanup_handoff_runtime_state(
    user_ids: Sequence[str],
    *,
    session_factory: Any | None = None,
) -> dict[str, int]:
    """Delete cart, pending-action, and candidate state for dedicated users."""
    from sqlalchemy import delete

    from app.db.models import CandidateContext, CartItem, PendingAction

    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    normalized_user_ids = sorted({user_id for user_id in user_ids if user_id})
    if not normalized_user_ids:
        return {
            "cart_items": 0,
            "pending_actions": 0,
            "candidate_contexts": 0,
        }

    session = session_factory()
    try:
        deleted_cart_items = session.execute(
            delete(CartItem).where(CartItem.user_id.in_(normalized_user_ids))
        ).rowcount
        deleted_pending_actions = session.execute(
            delete(PendingAction).where(PendingAction.user_id.in_(normalized_user_ids))
        ).rowcount
        deleted_candidate_contexts = session.execute(
            delete(CandidateContext).where(
                CandidateContext.user_id.in_(normalized_user_ids)
            )
        ).rowcount
        session.commit()
        return {
            "cart_items": int(deleted_cart_items or 0),
            "pending_actions": int(deleted_pending_actions or 0),
            "candidate_contexts": int(deleted_candidate_contexts or 0),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _json_body(response: ResponseLike) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {"raw_body": response.text}


async def run_api_handoff_smoke_case(
    case: ApiHandoffSmokeCase,
    client: AsyncPostClient,
) -> dict[str, Any]:
    """Run one API-boundary chat/confirm smoke case."""
    failures: list[str] = []
    outputs: list[dict[str, Any]] = []
    chat_outputs: list[dict[str, Any]] = []

    for index, message in enumerate(case["messages"]):
        response = await client.post(
            "/api/chat",
            json={
                "message": message,
                "user_id": case["user_id"],
                "thread_id": case["thread_id"],
                "include_debug": True,
            },
        )
        body = _json_body(response)
        chat_outputs.append(body)
        outputs.append(body)

        if response.status_code != 200:
            failures.append(
                f"chat[{index}] http status expected=200 actual={response.status_code}"
            )

        expected_status = case["expected_chat_statuses"][index]
        actual_status = body.get("status")
        if actual_status != expected_status:
            failures.append(
                f"chat[{index}] status expected={expected_status} actual={actual_status}"
            )

    confirm_output: dict[str, Any] | None = None
    if case["confirm"] is not None:
        pending_action_id = (
            chat_outputs[-1].get("pending_action_id") if chat_outputs else None
        )
        if not pending_action_id:
            failures.append("missing pending_action_id for confirmation step")
        else:
            response = await client.post(
                "/api/chat/confirm",
                json={
                    "user_id": case["user_id"],
                    "pending_action_id": pending_action_id,
                    "confirmed": bool(case["confirm"]),
                    "thread_id": case["thread_id"],
                    "include_debug": True,
                },
            )
            confirm_output = _json_body(response)
            outputs.append(confirm_output)

            if response.status_code != 200:
                failures.append(
                    "confirm http status "
                    f"expected=200 actual={response.status_code}"
                )

            expected_status = case.get("expected_confirm_status")
            actual_status = confirm_output.get("status")
            if expected_status is not None and actual_status != expected_status:
                failures.append(
                    "confirm status "
                    f"expected={expected_status} actual={actual_status}"
                )

    event_summary = summarize_debug_events(outputs)
    event_counts = event_summary["event_counts"]
    missing_events = [
        event for event in case["expected_events"] if event not in event_counts
    ]
    if missing_events:
        failures.append(f"missing expected debug events: {missing_events}")

    return {
        "case": case["name"],
        "passed": not failures,
        "failures": failures,
        "chat_outputs": chat_outputs,
        "confirm_output": confirm_output,
        "event_summary": event_summary,
    }


async def run_api_handoff_smoke(
    client: AsyncPostClient,
    cases: Sequence[ApiHandoffSmokeCase] = API_HANDOFF_SMOKE_CASES,
) -> dict[str, Any]:
    """Run API-boundary smoke cases and aggregate event metrics."""
    case_results = [
        await run_api_handoff_smoke_case(case, client)
        for case in cases
    ]
    outputs_for_event_summary: list[dict[str, Any]] = []
    for result in case_results:
        outputs_for_event_summary.extend(result["chat_outputs"])
        confirm_output = result.get("confirm_output")
        if isinstance(confirm_output, dict):
            outputs_for_event_summary.append(confirm_output)

    passed_cases = sum(1 for result in case_results if result["passed"])
    return {
        "total_cases": len(case_results),
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(case_results) if case_results else 0.0,
        "event_summary": summarize_debug_events(outputs_for_event_summary),
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


def format_api_handoff_smoke_summary(summary: dict[str, Any]) -> str:
    """Format a concise human-readable smoke summary."""
    lines = [
        "ShopMind V3 API handoff smoke",
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


async def run_with_asgi_app(
    cases: Sequence[ApiHandoffSmokeCase] = API_HANDOFF_SMOKE_CASES,
    *,
    cleanup_runtime_state: bool = True,
) -> dict[str, Any]:
    """Run smoke checks against the in-process FastAPI app."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    if cleanup_runtime_state:
        cleanup_api_handoff_smoke_state(cases)

    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await run_api_handoff_smoke(client, cases=cases)
    finally:
        if cleanup_runtime_state:
            cleanup_api_handoff_smoke_state(cases)


def _select_cases(case_name: str | None) -> tuple[ApiHandoffSmokeCase, ...]:
    if case_name is None:
        return API_HANDOFF_SMOKE_CASES
    return tuple(case for case in API_HANDOFF_SMOKE_CASES if case["name"] == case_name)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ShopMind V3 API-boundary chat/confirm smoke checks."
    )
    parser.add_argument(
        "--case",
        choices=[case["name"] for case in API_HANDOFF_SMOKE_CASES],
        default=None,
        help="Run a single smoke case instead of the full set.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw smoke summary as JSON.",
    )
    parser.add_argument(
        "--preserve-agent-mode",
        action="store_true",
        help=(
            "Do not force SHOPMIND_AGENT_MODE=multi and "
            "SHOPMIND_SUPERVISOR_ROUTER=deterministic before running."
        ),
    )
    parser.add_argument(
        "--preserve-runtime-state",
        action="store_true",
        help=(
            "Do not clean smoke-owned cart, pending action, and candidate "
            "context rows before and after running."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.preserve_agent_mode:
        os.environ["SHOPMIND_AGENT_MODE"] = "multi"
        os.environ["SHOPMIND_SUPERVISOR_ROUTER"] = "deterministic"
        from app.core.settings import get_settings

        get_settings.cache_clear()

    summary = asyncio.run(
        run_with_asgi_app(
            _select_cases(args.case),
            cleanup_runtime_state=not args.preserve_runtime_state,
        )
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_api_handoff_smoke_summary(summary))
    return 0 if summary["failures"] == [] else 1


if __name__ == "__main__":
    raise SystemExit(main())
