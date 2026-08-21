from contextlib import contextmanager
from threading import get_ident

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db_session
from app.cart.models import ShopMindCartItem
from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.models import PendingAction, Product
from app.dependencies import agent as agent_dependency
from app.main import app
from agents.shopmind_multi_agent import write_handoff as write_handoff_module
import tools.cart as cart_tools


TEST_USER_ID = "API_WRITE_HANDOFF_USER"
TEST_PRODUCT_ID = "TECH-KEY-001"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def cart_session(monkeypatch, tmp_path):
    # The Chat route deliberately runs synchronous Agent work in a worker
    # thread.  Keep that production boundary intact and give each patched
    # worker-side context its own Session and SQLite connection.  NullPool
    # prevents a connection created on one thread from being reused on another.
    database_path = tmp_path / "chat-write-handoff.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path}",
        poolclass=NullPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    inspection_session = Session()
    inspection_session.add(
        Product(
            product_id=TEST_PRODUCT_ID,
            name="Test Keyboard",
            category="Keyboards",
            price=99.00,
            in_stock=True,
        )
    )
    category = CatalogCategory(code="keyboards", name="Keyboards", status="active")
    catalog_product = CatalogProduct(
        product_code="CAT-KEY-001",
        legacy_product_id=TEST_PRODUCT_ID,
        category=category,
        brand="ShopMind",
        name="Test Keyboard",
        sale_status="active",
        attributes_json={},
    )
    catalog_sku = CatalogSku(
        product=catalog_product,
        sku_code="CAT-KEY-001-SKU",
        name="Standard",
        money_amount=99,
        currency="CNY",
        sale_status="active",
        variant_attributes_json={},
    )
    inspection_session.add_all([
        category,
        catalog_product,
        catalog_sku,
        CatalogInventory(sku=catalog_sku, on_hand_quantity=20, reserved_quantity=0, version=0),
    ])
    inspection_session.commit()

    @contextmanager
    def fake_cart_session():
        owner_thread_id = get_ident()
        worker_session = Session()
        try:
            yield worker_session
        finally:
            assert get_ident() == owner_thread_id
            worker_session.close()

    monkeypatch.setattr(cart_tools, "_get_cart_session", fake_cart_session)
    monkeypatch.setattr(
        write_handoff_module,
        "_get_product_session",
        fake_cart_session,
    )

    def override_db():
        request_session = Session()
        try:
            yield request_session
        finally:
            request_session.close()

    app.dependency_overrides[get_db_session] = override_db
    yield inspection_session
    app.dependency_overrides.pop(get_db_session, None)
    inspection_session.close()
    engine.dispose()


def _cart_item_count(session, user_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(ShopMindCartItem).where(ShopMindCartItem.user_id == user_id)
    )


def _pending_action_count(session) -> int:
    return session.scalar(select(func.count()).select_from(PendingAction))


def _cart_item_quantity(session, user_id: str) -> int:
    return session.scalar(select(ShopMindCartItem.quantity).where(ShopMindCartItem.user_id == user_id))


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
                "expected_version": 1,
                "thread_id": "thread-write-smoke",
                "include_debug": True,
            },
        )
        cart_response = await client.get("/api/cart", params={"user_id": TEST_USER_ID})

    confirm_body = confirm_response.json()
    cart_session.expire_all()
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
    assert pending_action.payload_json["schema_version"] == "shopmind.pending_action.add_to_cart.v1"
    assert pending_action.payload_json["origin_identifier"] == TEST_PRODUCT_ID
    assert pending_action.status == "confirmed"
    assert confirm_response.status_code == 200
    assert confirm_body["status"] == "completed"
    assert confirm_body["tool_calls"] == ["confirm_add_to_cart"]
    assert confirm_body["pending_action_id"] == pending_action_id
    assert confirm_body["debug"]["confirmation"]["events"][0]["event"] == (
        "pending_action_confirmed"
    )
    assert cart_response.status_code == 200
    assert cart_response.json()["items"][0]["quantity"] == 2
    assert _cart_item_count(cart_session, TEST_USER_ID) == 1
    assert _cart_item_quantity(cart_session, TEST_USER_ID) == 2


@pytest.mark.anyio
async def test_multi_agent_write_handoff_clarifies_missing_product_id(
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
                "message": "帮我把这个键盘加入购物车",
                "user_id": TEST_USER_ID,
                "thread_id": "thread-write-missing-product",
                "include_debug": True,
            },
        )

    chat_body = chat_response.json()

    assert chat_response.status_code == 200
    assert chat_body["status"] == "completed"
    assert chat_body["tool_calls"] == []
    assert chat_body["pending_action_id"] is None
    assert "商品 ID" in chat_body["answer"]
    assert TEST_PRODUCT_ID in chat_body["answer"]
    assert chat_body["debug"]["multi_agent_handoff"]["status"] == "completed"
    assert chat_body["debug"]["multi_agent_handoff"]["to"] == "v3_write_handoff_path"
    assert chat_body["debug"]["multi_agent_debug"]["supervisor_decision"]["intent"] == (
        "write_path_unsupported"
    )
    assert chat_body["debug"]["multi_agent_debug"]["supervisor_decision"]["routes"] == []
    assert "write_intent_blocked" in chat_body["debug"]["multi_agent_debug"][
        "safety_flags"
    ]
    assert _pending_action_count(cart_session) == 0
    assert _cart_item_count(cart_session, TEST_USER_ID) == 0


@pytest.mark.anyio
async def test_multi_agent_write_handoff_selects_candidate_by_number(
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
        candidate_response = await client.post(
            "/api/chat",
            json={
                "message": "帮我把这个键盘加入购物车 2 个",
                "user_id": TEST_USER_ID,
                "thread_id": "thread-write-select-candidate",
                "include_debug": True,
            },
        )
        selection_response = await client.post(
            "/api/chat",
            json={
                "message": "选 1",
                "user_id": TEST_USER_ID,
                "thread_id": "thread-write-select-candidate",
                "include_debug": True,
            },
        )

    candidate_body = candidate_response.json()
    selection_body = selection_response.json()
    pending_action = cart_session.get(PendingAction, selection_body["pending_action_id"])

    assert candidate_response.status_code == 200
    assert candidate_body["status"] == "completed"
    assert candidate_body["tool_calls"] == []
    assert candidate_body["pending_action_id"] is None
    assert TEST_PRODUCT_ID in candidate_body["answer"]
    assert candidate_body["debug"]["write_handoff_debug"]["candidate_context"][
        "events"
    ][-1]["event"] == "candidate_context_stored"
    assert selection_response.status_code == 200
    assert selection_body["status"] == "confirmation_required"
    assert selection_body["tool_calls"] == ["prepare_add_to_cart"]
    assert [
        event["event"]
        for event in selection_body["debug"]["write_handoff_debug"][
            "candidate_context"
        ]["events"]
    ] == ["candidate_context_selected", "candidate_context_cleared"]
    assert selection_body["debug"]["multi_agent_debug"]["supervisor_decision"][
        "intent"
    ] == "write_path_unsupported"
    assert pending_action is not None
    assert pending_action.thread_id == "thread-write-select-candidate"
    assert pending_action.payload_json["schema_version"] == "shopmind.pending_action.add_to_cart.v1"
    assert pending_action.payload_json["origin_identifier"] == TEST_PRODUCT_ID


@pytest.mark.anyio
async def test_multi_agent_write_handoff_reports_candidate_selection_out_of_range(
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
        candidate_response = await client.post(
            "/api/chat",
            json={
                "message": "帮我把这个键盘加入购物车",
                "user_id": TEST_USER_ID,
                "thread_id": "thread-write-select-out-of-range",
                "include_debug": True,
            },
        )
        selection_response = await client.post(
            "/api/chat",
            json={
                "message": "选 2",
                "user_id": TEST_USER_ID,
                "thread_id": "thread-write-select-out-of-range",
                "include_debug": True,
            },
        )

    candidate_body = candidate_response.json()
    selection_body = selection_response.json()

    assert candidate_response.status_code == 200
    assert TEST_PRODUCT_ID in candidate_body["answer"]
    assert selection_response.status_code == 200
    assert selection_body["status"] == "completed"
    assert selection_body["tool_calls"] == []
    assert selection_body["pending_action_id"] is None
    assert "当前候选只有 1-1" in selection_body["answer"]
    assert "你选择的是 2" in selection_body["answer"]
    assert _pending_action_count(cart_session) == 0


@pytest.mark.anyio
async def test_multi_agent_write_handoff_clarifies_missing_user_id(
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
                "message": f"帮我把 {TEST_PRODUCT_ID} 加入购物车",
                "thread_id": "thread-write-missing-user",
                "include_debug": True,
            },
        )

    chat_body = chat_response.json()

    assert chat_response.status_code == 200
    assert chat_body["status"] == "completed"
    assert chat_body["tool_calls"] == []
    assert chat_body["pending_action_id"] is None
    assert "user_id" in chat_body["answer"]
    assert chat_body["debug"]["multi_agent_handoff"]["status"] == "completed"
    assert chat_body["debug"]["multi_agent_handoff"]["to"] == "v3_write_handoff_path"
    assert chat_body["debug"]["multi_agent_debug"]["supervisor_decision"]["intent"] == (
        "write_path_unsupported"
    )
    assert chat_body["debug"]["multi_agent_debug"]["supervisor_decision"]["routes"] == []
    assert _pending_action_count(cart_session) == 0
