import re
import sqlite3

import pytest

from config import DEFAULT_DB_PATH
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
def cleanup_test_cart_data():
    ensure_cart_tables()
    clear_cart_items.invoke({"user_id": TEST_USER_ID})
    clear_cart_items.invoke({"user_id": OTHER_USER_ID})
    yield
    clear_cart_items.invoke({"user_id": TEST_USER_ID})
    clear_cart_items.invoke({"user_id": OTHER_USER_ID})


def _extract_pending_action_id(result: str) -> str:
    match = re.search(r"pending_action_id：([0-9a-f-]+)", result)
    assert match is not None, result
    return match.group(1)


def _count_cart_items(user_id: str) -> int:
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM cart_items WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row[0]


def _count_pending_actions(user_id: str) -> int:
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row[0]


def _get_pending_action_status(pending_action_id: str) -> str:
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        row = connection.execute(
            "SELECT status FROM pending_actions WHERE id = ?",
            (pending_action_id,),
        ).fetchone()
    assert row is not None
    return row[0]


def test_ensure_cart_tables_creates_tables() -> None:
    ensure_cart_tables()

    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name IN ('cart_items', 'pending_actions')
                """
            ).fetchall()
        }

    assert table_names == {"cart_items", "pending_actions"}


def test_prepare_add_to_cart_does_not_insert_cart_item() -> None:
    result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 2,
        }
    )

    assert "已生成待确认的加入购物车动作" in result
    assert "当前尚未写入购物车" in result
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
        {"pending_action_id": pending_action_id, "user_id": TEST_USER_ID}
    )

    assert "已确认加入购物车" in confirm_result
    assert _count_cart_items(TEST_USER_ID) == 1


def test_confirm_add_to_cart_sets_pending_action_status_confirmed() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 1,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)

    confirm_add_to_cart.invoke({"pending_action_id": pending_action_id, "user_id": TEST_USER_ID})

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

    assert "商品 NO-SUCH-PRODUCT 不存在" in result
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
        {"pending_action_id": pending_action_id, "user_id": OTHER_USER_ID}
    )

    assert "用户不匹配" in confirm_result
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
        {"pending_action_id": pending_action_id, "user_id": TEST_USER_ID}
    )
    second_result = confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": TEST_USER_ID}
    )

    assert "已确认加入购物车" in first_result
    assert "不能重复确认" in second_result
    assert _count_cart_items(TEST_USER_ID) == 1


def test_get_cart_items_returns_cart_products() -> None:
    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": TEST_USER_ID,
            "product_id": TEST_PRODUCT_ID,
            "quantity": 3,
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)
    confirm_add_to_cart.invoke({"pending_action_id": pending_action_id, "user_id": TEST_USER_ID})

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
    confirm_add_to_cart.invoke({"pending_action_id": pending_action_id, "user_id": TEST_USER_ID})

    clear_result = clear_cart_items.invoke({"user_id": TEST_USER_ID})
    cart_result = get_cart_items.invoke({"user_id": TEST_USER_ID})

    assert "删除购物车记录 1 条" in clear_result
    assert "删除待确认动作 1 条" in clear_result
    assert f"用户 {TEST_USER_ID} 的购物车暂无商品" in cart_result
    assert _count_pending_actions(TEST_USER_ID) == 0
