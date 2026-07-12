from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import CandidateContext, CartItem, PendingAction
from evaluation.shopmind_api_handoff_smoke import (
    API_HANDOFF_SMOKE_CASES,
    cleanup_api_handoff_smoke_state,
    format_api_handoff_smoke_summary,
    run_api_handoff_smoke,
    run_api_handoff_smoke_case,
)


class FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def post(self, path: str, json: dict[str, Any]) -> FakeResponse:
        self.requests.append((path, json))
        return self.responses.pop(0)


@pytest.mark.anyio
async def test_run_api_handoff_smoke_case_confirms_pending_action() -> None:
    client = FakeClient(
        [
            FakeResponse(
                {
                    "status": "confirmation_required",
                    "pending_action_id": "pending-001",
                    "debug": {},
                }
            ),
            FakeResponse(
                {
                    "status": "completed",
                    "pending_action_id": "pending-001",
                    "debug": {
                        "confirmation": {
                            "events": [{"event": "pending_action_confirmed"}]
                        }
                    },
                }
            ),
        ]
    )

    result = await run_api_handoff_smoke_case(
        {
            "name": "confirm",
            "user_id": "user-001",
            "thread_id": "thread-001",
            "messages": ("add TECH-KEY-001 to cart",),
            "expected_chat_statuses": ("confirmation_required",),
            "confirm": True,
            "expected_confirm_status": "completed",
            "expected_events": ("pending_action_confirmed",),
        },
        client,
    )

    assert result["passed"] is True
    assert result["failures"] == []
    assert client.requests[0] == (
        "/api/chat",
        {
            "message": "add TECH-KEY-001 to cart",
            "user_id": "user-001",
            "thread_id": "thread-001",
            "include_debug": True,
        },
    )
    assert client.requests[1] == (
        "/api/chat/confirm",
        {
            "user_id": "user-001",
            "pending_action_id": "pending-001",
            "confirmed": True,
            "thread_id": "thread-001",
            "include_debug": True,
        },
    )


@pytest.mark.anyio
async def test_run_api_handoff_smoke_case_reports_missing_events() -> None:
    client = FakeClient(
        [
            FakeResponse(
                {
                    "status": "completed",
                    "pending_action_id": None,
                    "debug": {},
                }
            ),
        ]
    )

    result = await run_api_handoff_smoke_case(
        {
            "name": "missing_event",
            "user_id": "user-001",
            "thread_id": "thread-001",
            "messages": ("add keyboard to cart",),
            "expected_chat_statuses": ("completed",),
            "confirm": None,
            "expected_confirm_status": None,
            "expected_events": ("candidate_context_stored",),
        },
        client,
    )

    assert result["passed"] is False
    assert "candidate_context_stored" in result["failures"][0]


@pytest.mark.anyio
async def test_run_api_handoff_smoke_aggregates_cases_and_events() -> None:
    client = FakeClient(
        [
            FakeResponse(
                {
                    "status": "completed",
                    "debug": {
                        "write_handoff_debug": {
                            "candidate_context": {
                                "events": [{"event": "candidate_context_stored"}]
                            }
                        }
                    },
                }
            ),
            FakeResponse(
                {
                    "status": "confirmation_required",
                    "pending_action_id": "pending-001",
                    "debug": {
                        "write_handoff_debug": {
                            "candidate_context": {
                                "events": [
                                    {"event": "candidate_context_selected"},
                                    {"event": "candidate_context_cleared"},
                                ]
                            }
                        }
                    },
                }
            ),
            FakeResponse(
                {
                    "status": "completed",
                    "debug": {
                        "confirmation": {
                            "events": [{"event": "pending_action_confirmed"}]
                        }
                    },
                }
            ),
        ]
    )

    summary = await run_api_handoff_smoke(
        client,
        cases=(
            {
                "name": "candidate",
                "user_id": "user-001",
                "thread_id": "thread-001",
                "messages": ("add keyboard to cart", "1"),
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
        ),
    )

    assert summary["passed_cases"] == 1
    assert summary["total_cases"] == 1
    assert summary["failures"] == []
    assert summary["event_summary"]["event_counts"] == {
        "candidate_context_stored": 1,
        "candidate_context_selected": 1,
        "candidate_context_cleared": 1,
        "pending_action_confirmed": 1,
    }


def test_format_api_handoff_smoke_summary_reports_failures() -> None:
    output = format_api_handoff_smoke_summary(
        {
            "passed_cases": 0,
            "total_cases": 1,
            "pass_rate": 0.0,
            "event_summary": {
                "total_outputs": 0,
                "outputs_with_events": 0,
                "output_event_rate": 0.0,
                "total_events": 0,
                "group_counts": {},
                "event_counts": {},
                "group_rates": {},
                "event_rates": {},
            },
            "failures": [{"case": "broken", "failures": ["bad status"]}],
        }
    )

    assert "ShopMind V3 API handoff smoke" in output
    assert "broken" in output
    assert "bad status" in output


def test_api_handoff_smoke_cases_cover_confirm_cancel_and_candidate_paths() -> None:
    assert {case["name"] for case in API_HANDOFF_SMOKE_CASES} == {
        "explicit_product_confirmed",
        "explicit_product_cancelled",
        "candidate_selection_confirmed",
    }
    explicit_messages = [
        case["messages"][0]
        for case in API_HANDOFF_SMOKE_CASES
        if case["name"].startswith("explicit_product_")
    ]
    assert all("TECH-KEY-010" in message for message in explicit_messages)
    assert all("add to cart" in message for message in explicit_messages)


def test_cleanup_api_handoff_smoke_state_deletes_only_smoke_owned_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    expires_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all(
        [
            CartItem(
                user_id="API-HANDOFF-SMOKE-CONFIRM",
                product_id="TECH-KEY-010",
                quantity=2,
            ),
            CartItem(
                user_id="REAL-USER",
                product_id="TECH-KEY-010",
                quantity=1,
            ),
            PendingAction(
                id="pending-smoke",
                user_id="API-HANDOFF-SMOKE-CONFIRM",
                thread_id="api-handoff-smoke-confirm",
                action_type="add_to_cart",
                payload_json={"product_id": "TECH-KEY-010", "quantity": 2},
                status="confirmed",
            ),
            PendingAction(
                id="pending-real",
                user_id="REAL-USER",
                thread_id="real-thread",
                action_type="add_to_cart",
                payload_json={"product_id": "TECH-KEY-010", "quantity": 1},
                status="pending",
            ),
            CandidateContext(
                user_id="API-HANDOFF-SMOKE-CANDIDATE",
                thread_id="api-handoff-smoke-candidate",
                product_ids=["TECH-KEY-010"],
                quantity=1,
                expires_at=expires_at,
            ),
            CandidateContext(
                user_id="REAL-USER",
                thread_id="real-thread",
                product_ids=["TECH-KEY-010"],
                quantity=1,
                expires_at=expires_at,
            ),
        ]
    )
    session.commit()
    session.close()

    result = cleanup_api_handoff_smoke_state(session_factory=Session)

    verify_session = Session()
    try:
        assert result == {
            "cart_items": 1,
            "pending_actions": 1,
            "candidate_contexts": 1,
        }
        assert [
            item.user_id
            for item in verify_session.scalars(select(CartItem)).all()
        ] == ["REAL-USER"]
        assert [
            action.user_id
            for action in verify_session.scalars(select(PendingAction)).all()
        ] == ["REAL-USER"]
        assert [
            context.user_id
            for context in verify_session.scalars(select(CandidateContext)).all()
        ] == ["REAL-USER"]
    finally:
        verify_session.close()
