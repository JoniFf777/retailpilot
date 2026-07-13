import os
import uuid

import pytest

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip(
        "set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL API integration tests",
        allow_module_level=True,
    )

from httpx import ASGITransport, AsyncClient

from app.db.session import SessionLocal
from app.main import app
from app.repositories import cart as cart_repository
from app.repositories import products as product_repository
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
