from contextlib import contextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import CartItem, PendingAction, Product
from app.dependencies import agent as agent_dependency
from app.main import app
import tools.cart as cart_tools


TEST_USER_ID = "API_WRITE_HANDOFF_USER"
TEST_PRODUCT_ID = "TECH-KEY-001"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def cart_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        Product(
            product_id=TEST_PRODUCT_ID,
            name="Test Keyboard",
            category="Keyboards",
            price=99.00,
            in_stock=True,
        )
    )
    session.commit()

    @contextmanager
    def fake_cart_session():
        yield session

    monkeypatch.setattr(cart_tools, "_get_cart_session", fake_cart_session)
    yield session
    session.close()


def _cart_item_count(session, user_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(CartItem).where(CartItem.user_id == user_id)
    )


def _cart_item_quantity(session, user_id: str) -> int:
    return session.scalar(select(CartItem.quantity).where(CartItem.user_id == user_id))


@pytest.mark.anyio
async def test_multi_agent_write_handoff_can_confirm_add_to_cart(
    monkeypatch,
    cart_session,
) -> None:
    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "shopmind_agent_mode": "multi",
                "shopmind_supervisor_router": "deterministic",
            },
        )(),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        chat_response = await client.post(
            "/api/chat",
            json={
                "message": f"帮我把 {TEST_PRODUCT_ID} 加入购物车 2 个",
                "user_id": TEST_USER_ID,
                "thread_id": "thread-write-smoke",
                "include_debug": True,
            },
        )

        chat_body = chat_response.json()
        pending_action_id = chat_body["pending_action_id"]

        confirm_response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": TEST_USER_ID,
                "pending_action_id": pending_action_id,
                "confirmed": True,
                "thread_id": "thread-write-smoke",
            },
        )

    confirm_body = confirm_response.json()
    pending_action = cart_session.get(PendingAction, pending_action_id)

    assert chat_response.status_code == 200
    assert chat_body["status"] == "confirmation_required"
    assert chat_body["tool_calls"] == ["prepare_add_to_cart"]
    assert chat_body["debug"]["multi_agent_handoff"]["status"] == (
        "confirmation_required"
    )
    assert chat_body["debug"]["multi_agent_handoff"]["to"] == "v3_write_handoff_path"
    assert chat_body["debug"]["multi_agent_debug"]["supervisor_decision"]["intent"] == (
        "write_path_unsupported"
    )
    assert chat_body["debug"]["multi_agent_debug"]["supervisor_decision"]["routes"] == []
    assert "write_intent_blocked" in chat_body["debug"]["multi_agent_debug"][
        "safety_flags"
    ]
    assert pending_action is not None
    assert pending_action.thread_id == "thread-write-smoke"
    assert pending_action.payload_json == {"product_id": TEST_PRODUCT_ID, "quantity": 2}
    assert pending_action.status == "confirmed"
    assert confirm_response.status_code == 200
    assert confirm_body["status"] == "completed"
    assert confirm_body["tool_calls"] == ["confirm_add_to_cart"]
    assert confirm_body["pending_action_id"] == pending_action_id
    assert _cart_item_count(cart_session, TEST_USER_ID) == 1
    assert _cart_item_quantity(cart_session, TEST_USER_ID) == 2
