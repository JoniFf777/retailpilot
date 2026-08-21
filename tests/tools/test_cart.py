import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.cart.models import ShopMindCartItem
from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.models import CartItem, PendingAction, Product
from app.schemas.pending_actions import CartActionOutcome
import tools.cart as cart_tools
from tools.cart import (
    cancel_pending_action,
    clear_cart_items,
    confirm_add_to_cart,
    ensure_cart_tables,
    get_cart_items,
    prepare_add_to_cart,
)


TEST_USER_ID = "TEST_CART_USER"
OTHER_USER_ID = "TEST_CART_OTHER_USER"
TEST_PRODUCT_ID = "TECH-KEY-010"


@pytest.fixture(autouse=True)
def cart_repository_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        Product(
            product_id=TEST_PRODUCT_ID,
            name="Apple Magic Keyboard",
            category="Keyboards",
            price=99.00,
            in_stock=True,
        )
    )
    category = CatalogCategory(code="keyboards", name="Keyboards", status="active")
    catalog_product = CatalogProduct(
        product_code="LP-LEGACY-010",
        legacy_product_id=TEST_PRODUCT_ID,
        category=category,
        brand="ShopMind",
        name="Apple Magic Keyboard",
        sale_status="active",
        attributes_json={},
    )
    catalog_sku = CatalogSku(
        product=catalog_product,
        sku_code=TEST_PRODUCT_ID,
        name="Standard",
        money_amount=99,
        currency="USD",
        sale_status="active",
        variant_attributes_json={},
    )
    session.add_all([
        category,
        catalog_product,
        catalog_sku,
        CatalogInventory(sku=catalog_sku, on_hand_quantity=20, reserved_quantity=0, version=0),
    ])
    session.commit()

    @contextmanager
    def fake_cart_session():
        yield session

    monkeypatch.setattr(cart_tools, "_get_cart_session", fake_cart_session)
    yield
    session.close()


def _outcome(result: str) -> CartActionOutcome:
    return CartActionOutcome.model_validate(json.loads(result))


def _extract_pending_action_id(result: str) -> str:
    outcome = _outcome(result)
    assert outcome.status == "prepared", outcome
    assert outcome.pending_action_id
    return outcome.pending_action_id


def _count_cart_items(user_id: str) -> int:
    with cart_tools._get_cart_session() as session:
        return session.scalar(
            select(func.count()).select_from(CartItem).where(CartItem.user_id == user_id)
        )


def _count_pending_actions(user_id: str) -> int:
    with cart_tools._get_cart_session() as session:
        return session.scalar(
            select(func.count())
            .select_from(PendingAction)
            .where(PendingAction.user_id == user_id)
        )


def _count_shopmind_cart_items(user_id: str) -> int:
    with cart_tools._get_cart_session() as session:
        return session.scalar(
            select(func.count()).select_from(ShopMindCartItem).where(ShopMindCartItem.user_id == user_id)
        )


def _get_pending_action_status(pending_action_id: str) -> str:
    with cart_tools._get_cart_session() as session:
        action = session.get(PendingAction, pending_action_id)
    assert action is not None
    return action.status


def test_ensure_cart_tables_is_compatibility_noop() -> None:
    assert ensure_cart_tables() is None


def test_prepare_add_to_cart_does_not_insert_cart_item() -> None:
    result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 2,
        }
    )

    assert _outcome(result).status == "prepared"
    assert _count_cart_items(TEST_USER_ID) == 0


def test_prepare_add_to_cart_creates_pending_action() -> None:
    result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 1,
            "thread_id": "thread-cart-test",
        }
    )
    pending_action_id = _extract_pending_action_id(result)

    assert pending_action_id
    assert _count_pending_actions(TEST_USER_ID) == 1
    assert _get_pending_action_status(pending_action_id) == "pending"


def test_confirm_add_to_cart_inserts_cart_item() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 2,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)

    confirm_result = confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": TEST_USER_ID, "expected_version": 1}
    )

    assert _outcome(confirm_result).status == "confirmed"
    assert _count_cart_items(TEST_USER_ID) == 0
    assert _count_shopmind_cart_items(TEST_USER_ID) == 1


def test_confirm_add_to_cart_sets_pending_action_status_confirmed() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 1,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)

    confirm_add_to_cart.invoke({"pending_action_id": pending_action_id, "user_id": TEST_USER_ID, "expected_version": 1})

    assert _get_pending_action_status(pending_action_id) == "confirmed"


def test_cancel_pending_action_cancels_pending_action() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 1,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)

    cancel_result = cancel_pending_action.invoke(
        {"pending_action_id": pending_action_id, "user_id": TEST_USER_ID}
    )

    assert "已取消待确认动作" in cancel_result
    assert _get_pending_action_status(pending_action_id) == "cancelled"
    assert _count_cart_items(TEST_USER_ID) == 0


def test_prepare_add_to_cart_returns_chinese_error_for_missing_product() -> None:
    result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": "NO-SUCH-PRODUCT",
            "quantity": 1,
        }
    )

    assert _outcome(result).code == "catalog_not_found"
    assert _count_pending_actions(TEST_USER_ID) == 0


def test_confirm_add_to_cart_rejects_user_mismatch() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 1,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)

    confirm_result = confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": OTHER_USER_ID, "expected_version": 1}
    )

    assert _outcome(confirm_result).code == "pending_action_not_found"
    assert _get_pending_action_status(pending_action_id) == "pending"
    assert _count_cart_items(OTHER_USER_ID) == 0


def test_confirm_add_to_cart_rejects_duplicate_confirmation() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 1,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)

    first_result = confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": TEST_USER_ID, "expected_version": 1}
    )
    second_result = confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": TEST_USER_ID, "expected_version": 1}
    )

    assert _outcome(first_result).status == "confirmed"
    assert _outcome(second_result).idempotent_replay is True
    assert _count_cart_items(TEST_USER_ID) == 0
    assert _count_shopmind_cart_items(TEST_USER_ID) == 1


def test_get_cart_items_returns_cart_products() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 3,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)
    confirm_add_to_cart.invoke({"pending_action_id": pending_action_id, "user_id": TEST_USER_ID, "expected_version": 1})

    result = get_cart_items.invoke({"user_id": TEST_USER_ID})

    assert f"用户 {TEST_USER_ID} 的购物车" in result
    assert TEST_PRODUCT_ID in result
    assert "Apple Magic Keyboard" in result
    assert "数量：3" in result
    assert "购物车合计" in result


def test_clear_cart_items_cleans_test_data() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 1,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)
    confirm_add_to_cart.invoke({"pending_action_id": pending_action_id, "user_id": TEST_USER_ID, "expected_version": 1})

    clear_result = clear_cart_items.invoke({"user_id": TEST_USER_ID})
    cart_result = get_cart_items.invoke({"user_id": TEST_USER_ID})

    assert "删除购物车记录 1 条" in clear_result
    assert "删除待确认动作 1 条" in clear_result
    assert f"用户 {TEST_USER_ID} 的购物车暂无商品" in cart_result
    assert _count_pending_actions(TEST_USER_ID) == 0
