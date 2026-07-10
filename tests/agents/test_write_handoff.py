from contextlib import contextmanager

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from agents.shopmind_multi_agent.write_handoff import (
    extract_product_id,
    invoke_write_handoff,
)
from app.db.base import Base
from app.db.models import PendingAction, Product
import tools.cart as cart_tools


TEST_USER_ID = "WRITE_HANDOFF_USER"
TEST_PRODUCT_ID = "TECH-KEY-001"


def test_extract_product_id_normalizes_explicit_id() -> None:
    assert extract_product_id("帮我把 tech-key-001 加入购物车") == TEST_PRODUCT_ID


def test_write_handoff_requires_user_id() -> None:
    result = invoke_write_handoff(f"帮我把 {TEST_PRODUCT_ID} 加入购物车")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert "user_id" in result["answer"]


def test_write_handoff_requires_explicit_product_id() -> None:
    result = invoke_write_handoff("帮我把这个键盘加入购物车", user_id=TEST_USER_ID)

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert "商品 ID" in result["answer"]


def test_write_handoff_prepares_add_to_cart(monkeypatch) -> None:
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

    result = invoke_write_handoff(
        f"帮我把 {TEST_PRODUCT_ID} 加入购物车",
        user_id=TEST_USER_ID,
        thread_id="thread-write-native",
    )
    pending_action = session.get(PendingAction, result["pending_action_id"])
    pending_count = session.scalar(
        select(func.count())
        .select_from(PendingAction)
        .where(PendingAction.user_id == TEST_USER_ID)
    )

    assert result["status"] == "confirmation_required"
    assert result["tool_calls"] == ["prepare_add_to_cart"]
    assert result["pending_action_id"]
    assert pending_count == 1
    assert pending_action is not None
    assert pending_action.thread_id == "thread-write-native"
    assert pending_action.status == "pending"
    assert pending_action.payload_json == {"product_id": TEST_PRODUCT_ID, "quantity": 1}

    session.close()
