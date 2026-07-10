from contextlib import contextmanager

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from agents.shopmind_multi_agent.write_handoff import (
    clear_candidate_context,
    extract_product_id,
    find_product_candidates,
    get_candidate_context,
    infer_product_category,
    extract_quantity,
    invoke_write_handoff,
)
from app.db.base import Base
from app.db.models import PendingAction, Product
import tools.cart as cart_tools


TEST_USER_ID = "WRITE_HANDOFF_USER"
TEST_PRODUCT_ID = "TECH-KEY-001"


def test_extract_product_id_normalizes_explicit_id() -> None:
    assert extract_product_id("帮我把 tech-key-001 加入购物车") == TEST_PRODUCT_ID


def test_extract_quantity_defaults_to_one() -> None:
    assert extract_quantity(f"帮我把 {TEST_PRODUCT_ID} 加入购物车") == 1


def test_extract_quantity_supports_simple_number_patterns() -> None:
    assert extract_quantity(f"帮我把 {TEST_PRODUCT_ID} 加入购物车 2 个") == 2
    assert extract_quantity(f"add to cart {TEST_PRODUCT_ID} quantity 3") == 3
    assert extract_quantity(f"add {TEST_PRODUCT_ID} x4") == 4
    assert extract_quantity(f"帮我买两个 {TEST_PRODUCT_ID}") == 2


def test_infer_product_category_from_common_terms() -> None:
    assert infer_product_category("帮我把这个键盘加入购物车") == "Keyboards"
    assert infer_product_category("add this monitor to cart") == "Monitors"
    assert infer_product_category("这个不明确的东西加入购物车") is None


def test_write_handoff_requires_user_id() -> None:
    result = invoke_write_handoff(f"帮我把 {TEST_PRODUCT_ID} 加入购物车")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert "user_id" in result["answer"]


def test_write_handoff_requires_explicit_product_id_when_no_candidate() -> None:
    result = invoke_write_handoff("帮我把这个东西加入购物车", user_id=TEST_USER_ID)

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert "商品 ID" in result["answer"]


def test_write_handoff_suggests_candidates_without_creating_action(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all(
        [
            Product(
                product_id=TEST_PRODUCT_ID,
                name="Test Keyboard",
                category="Keyboards",
                price=99.00,
                in_stock=True,
            ),
            Product(
                product_id="TECH-KEY-002",
                name="Budget Keyboard",
                category="Keyboards",
                price=49.00,
                in_stock=True,
            ),
        ]
    )
    session.commit()

    @contextmanager
    def fake_product_session():
        yield session

    monkeypatch.setattr(
        "agents.shopmind_multi_agent.write_handoff._get_product_session",
        fake_product_session,
    )

    result = invoke_write_handoff("帮我把这个键盘加入购物车", user_id=TEST_USER_ID)
    pending_count = session.scalar(
        select(func.count()).select_from(PendingAction)
    )

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert "请选择" in result["answer"] or "可从这些候选中选择" in result["answer"]
    assert TEST_PRODUCT_ID in result["answer"]
    assert "TECH-KEY-002" in result["answer"]
    assert pending_count == 0

    session.close()


def test_write_handoff_resolves_same_thread_candidate_selection(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all(
        [
            Product(
                product_id=TEST_PRODUCT_ID,
                name="Test Keyboard",
                category="Keyboards",
                price=49.00,
                in_stock=True,
            ),
            Product(
                product_id="TECH-KEY-002",
                name="Premium Keyboard",
                category="Keyboards",
                price=99.00,
                in_stock=True,
            ),
        ]
    )
    session.commit()

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(
        "agents.shopmind_multi_agent.write_handoff._get_product_session",
        fake_session,
    )
    monkeypatch.setattr(cart_tools, "_get_cart_session", fake_session)

    thread_id = "thread-candidate-selection"
    first_result = invoke_write_handoff(
        "帮我把这个键盘加入购物车 2 个",
        user_id=TEST_USER_ID,
        thread_id=thread_id,
    )
    second_result = invoke_write_handoff(
        "选 1",
        user_id=TEST_USER_ID,
        thread_id=thread_id,
    )
    pending_action = session.get(PendingAction, second_result["pending_action_id"])

    assert first_result["status"] == "completed"
    assert first_result["tool_calls"] == []
    assert TEST_PRODUCT_ID in first_result["answer"]
    assert second_result["status"] == "confirmation_required"
    assert second_result["tool_calls"] == ["prepare_add_to_cart"]
    assert pending_action is not None
    assert pending_action.thread_id == thread_id
    assert pending_action.payload_json == {"product_id": TEST_PRODUCT_ID, "quantity": 2}

    clear_candidate_context(TEST_USER_ID, thread_id)
    session.close()


def test_write_handoff_reports_candidate_selection_out_of_range(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all(
        [
            Product(
                product_id=TEST_PRODUCT_ID,
                name="Test Keyboard",
                category="Keyboards",
                price=49.00,
                in_stock=True,
            ),
            Product(
                product_id="TECH-KEY-002",
                name="Premium Keyboard",
                category="Keyboards",
                price=99.00,
                in_stock=True,
            ),
        ]
    )
    session.commit()

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(
        "agents.shopmind_multi_agent.write_handoff._get_product_session",
        fake_session,
    )
    monkeypatch.setattr(cart_tools, "_get_cart_session", fake_session)

    thread_id = "thread-candidate-out-of-range"
    invoke_write_handoff(
        "帮我把这个键盘加入购物车",
        user_id=TEST_USER_ID,
        thread_id=thread_id,
    )
    result = invoke_write_handoff(
        "选 3",
        user_id=TEST_USER_ID,
        thread_id=thread_id,
    )
    pending_count = session.scalar(select(func.count()).select_from(PendingAction))

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert "当前候选只有 1-2" in result["answer"]
    assert "你选择的是 3" in result["answer"]
    assert pending_count == 0
    assert get_candidate_context(TEST_USER_ID, thread_id) is not None

    clear_candidate_context(TEST_USER_ID, thread_id)
    session.close()


def test_write_handoff_does_not_resolve_selection_without_context(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(
        "agents.shopmind_multi_agent.write_handoff._get_product_session",
        fake_session,
    )

    result = invoke_write_handoff(
        "选 1",
        user_id=TEST_USER_ID,
        thread_id="thread-without-candidates",
    )

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert "商品 ID" in result["answer"]

    session.close()


def test_find_product_candidates_uses_catalog_category(monkeypatch) -> None:
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
    def fake_product_session():
        yield session

    monkeypatch.setattr(
        "agents.shopmind_multi_agent.write_handoff._get_product_session",
        fake_product_session,
    )

    candidates = find_product_candidates("帮我把这个键盘加入购物车")

    assert [candidate["product_id"] for candidate in candidates] == [TEST_PRODUCT_ID]

    session.close()


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
        f"帮我把 {TEST_PRODUCT_ID} 加入购物车 2 个",
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
    assert pending_action.payload_json == {"product_id": TEST_PRODUCT_ID, "quantity": 2}

    session.close()
