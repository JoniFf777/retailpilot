import os
import uuid

import pytest
from sqlalchemy import select

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip(
        "set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL API integration tests",
        allow_module_level=True,
    )

from httpx import ASGITransport, AsyncClient

from app.db.session import SessionLocal
from app.db.models import AgentRun
from app.main import app
from app.repositories import cart as cart_repository
from app.repositories import products as product_repository
from app.repositories import preferences as preference_repository
from app.repositories.runtime_runs import list_agent_run_events
from scripts.smoke_postgres import EXPECTED_ALEMBIC_VERSION


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _with_session(callback):
    session = SessionLocal()
    try:
        return callback(session)
    finally:
        session.close()


@pytest.fixture
def smoke_user_id():
    user_id = f"integration-api-{uuid.uuid4()}"
    _clear_user_state(user_id)
    try:
        yield user_id
    finally:
        _clear_user_state(user_id)


def _clear_user_state(user_id: str) -> None:
    def clear(session):
        cart_repository.clear_cart_items(session, user_id)
        preference_repository.clear_user_preferences(session, user_id)
        session.commit()

    _with_session(clear)


def _get_smoke_product_id() -> str:
    def get_product(session):
        products = product_repository.search_products(
            session, query="keyboard", in_stock_only=True, limit=1
        )
        assert products, "seeded PostgreSQL database should contain a keyboard product"
        return products[0]["product_id"]

    return _with_session(get_product)


def _prepare_pending_action(user_id: str, quantity: int = 1) -> str:
    product_id = _get_smoke_product_id()

    def prepare(session):
        result = cart_repository.prepare_add_to_cart(
            session,
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
            thread_id="integration-api-thread",
        )
        session.commit()
        assert result["status"] == cart_repository.PENDING_STATUS
        return result["pending_action_id"]

    return _with_session(prepare)


def _get_cart_item_count(user_id: str) -> int:
    return _with_session(
        lambda session: len(cart_repository.get_cart_items(session, user_id))
    )


def _prepare_preference_action(user_id: str) -> str:
    def prepare(session):
        result = cart_repository.prepare_save_preference(
            session,
            user_id=user_id,
            preference_type="style",
            preference_value="quiet keyboard",
            thread_id="integration-api-thread",
        )
        session.commit()
        return result["pending_action_id"]

    return _with_session(prepare)


def _get_pending_action_status(pending_action_id: str) -> str:
    def get_status(session):
        action = session.get(cart_repository.PendingAction, pending_action_id)
        assert action is not None
        return action.status

    return _with_session(get_status)


async def test_postgres_health_endpoint_against_configured_database():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/postgres")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "retailpilot_v2_smoke"
    assert response.json()["user"] == "postgres"
    assert response.json()["alembic_version"] == EXPECTED_ALEMBIC_VERSION


async def test_deployment_readiness_endpoint_against_configured_database():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/readiness")

    payload = response.json()
    assert response.status_code == 200
    assert payload["schema_version"] == "shopmind.deployment-readiness.v1"
    assert payload["profile"] == "development"
    assert payload["status"] == "ready"
    assert payload["passed_checks"] == 3
    assert payload["failed_checks"] == 0
    assert payload["not_applicable_checks"] == 2


async def test_service_metrics_endpoint_exposes_closed_process_snapshot():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/service-metrics")

    payload = response.json()
    assert response.status_code == 200
    assert payload["schema_version"] == "shopmind.service-health.v1"
    assert payload["metrics"]["schema_version"] == (
        "shopmind.service-metrics.v1"
    )
    assert payload["slo"]["schema_version"] == "shopmind.service-slo.v1"
    assert payload["status"] in {"insufficient_data", "met", "breached"}


async def test_chat_confirm_endpoint_confirms_pending_action(smoke_user_id):
    pending_action_id = _prepare_pending_action(smoke_user_id, quantity=2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": smoke_user_id,
                "pending_action_id": pending_action_id,
                "confirmed": True,
                "thread_id": "integration-api-thread",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["tool_calls"] == ["confirm_add_to_cart"]
    assert body["pending_action_id"] == pending_action_id
    assert _get_pending_action_status(pending_action_id) == cart_repository.CONFIRMED_STATUS
    assert _get_cart_item_count(smoke_user_id) == 1


async def test_chat_confirm_endpoint_cancels_pending_action(smoke_user_id):
    pending_action_id = _prepare_pending_action(smoke_user_id, quantity=1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": smoke_user_id,
                "pending_action_id": pending_action_id,
                "confirmed": False,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["tool_calls"] == ["cancel_pending_action"]
    assert body["pending_action_id"] == pending_action_id
    assert _get_pending_action_status(pending_action_id) == cart_repository.CANCELLED_STATUS
    assert _get_cart_item_count(smoke_user_id) == 0


async def test_chat_confirm_endpoint_dispatches_preference_action(smoke_user_id):
    pending_action_id = _prepare_preference_action(smoke_user_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": smoke_user_id,
                "pending_action_id": pending_action_id,
                "confirmed": True,
                "thread_id": "integration-api-thread",
                "include_debug": True,
            },
        )
        body = response.json()
        inspection = await client.post(
            "/api/owner-data/runs/inspect",
            json={
                "user_id": smoke_user_id,
                "run_id": body["run_id"],
                "event_limit": 50,
            },
        )

    preferences = _with_session(
        lambda session: preference_repository.get_user_preferences(
            session, smoke_user_id
        )
    )
    def load_action_events(session):
        run_id = session.scalar(
            select(AgentRun.id)
            .where(AgentRun.pending_action_id == pending_action_id)
            .order_by(AgentRun.started_at.desc())
        )
        assert run_id is not None
        return list_agent_run_events(session, run_id=run_id)

    events = _with_session(load_action_events)
    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["tool_calls"] == ["confirm_save_preference"]
    assert body["debug"]["confirmation"]["events"][0]["action_type"] == (
        "save_preference"
    )
    assert body["trace_id"]
    inspection_payload = inspection.json()
    assert inspection.status_code == 200
    assert inspection_payload["schema_version"] == (
        "shopmind.owner-run-inspection.v1"
    )
    assert inspection_payload["run_id"] == body["run_id"]
    assert inspection_payload["trace_id"] == body["trace_id"]
    assert all(
        event["visibility"] == "client"
        for event in inspection_payload["events"]
    )
    assert "payload" not in inspection.text
    assert [item["preference_value"] for item in preferences] == ["quiet keyboard"]
    action_events = [event for event in events if event["event_type"].startswith("action.")]
    assert [event["event_type"] for event in action_events] == [
        "action.resumed",
        "action.confirmed",
    ]
    assert action_events[-1]["payload_json"]["action_type"] == "save_preference"


async def test_chat_confirm_edit_is_persisted_and_idempotently_replayed(
    smoke_user_id,
):
    pending_action_id = _prepare_preference_action(smoke_user_id)
    request_body = {
        "user_id": smoke_user_id,
        "pending_action_id": pending_action_id,
        "confirmed": True,
        "thread_id": "integration-api-thread",
        "updated_arguments": {"preference_value": "silent switches"},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/chat/confirm",
            headers={"Idempotency-Key": f"edit-{pending_action_id}"},
            json=request_body,
        )
        replay = await client.post(
            "/api/chat/confirm",
            headers={"Idempotency-Key": f"edit-{pending_action_id}"},
            json=request_body,
        )

    def load_state(session):
        action = session.get(cart_repository.PendingAction, pending_action_id)
        run_id = session.scalar(
            select(AgentRun.id)
            .where(AgentRun.pending_action_id == pending_action_id)
            .order_by(AgentRun.started_at.desc())
        )
        assert action is not None and run_id is not None
        return (
            action,
            preference_repository.get_user_preferences(session, smoke_user_id),
            list_agent_run_events(session, run_id=run_id),
        )

    action, preferences, events = _with_session(load_state)
    action_events = [
        event for event in events if event["event_type"].startswith("action.")
    ]
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert action.payload_json["preference_value"] == "silent switches"
    assert [item["preference_value"] for item in preferences] == [
        "silent switches"
    ]
    assert [event["event_type"] for event in action_events] == [
        "action.resumed",
        "action.edited",
        "action.confirmed",
    ]
    assert action_events[1]["payload_json"]["updated_fields"] == [
        "preference_value"
    ]
