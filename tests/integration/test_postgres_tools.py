import os
import re
import uuid

import pytest

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip(
        "set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL integration tests",
        allow_module_level=True,
    )

from app.db.session import SessionLocal
from app.repositories import cart as cart_repository
from app.repositories import preferences as preference_repository
from app.repositories import products as product_repository
from tools.cart import (
    clear_cart_items,
    confirm_add_to_cart,
    get_cart_items,
    prepare_add_to_cart,
)
from tools.preferences import (
    add_user_preference,
    clear_user_preferences,
    get_user_preferences,
)
from tools.products import search_products


def _with_session(callback):
    session = SessionLocal()
    try:
        return callback(session)
    finally:
        session.close()


@pytest.fixture
def smoke_user_id():
    user_id = f"integration-tool-{uuid.uuid4()}"
    _clear_user_state(user_id)
    try:
        yield user_id
    finally:
        _clear_user_state(user_id)


def _clear_user_state(user_id: str) -> None:
    def clear(session):
        preference_repository.clear_user_preferences(session, user_id)
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


def _get_preferences(user_id: str):
    return _with_session(
        lambda session: preference_repository.get_user_preferences(session, user_id)
    )


def _get_cart_items(user_id: str):
    return _with_session(lambda session: cart_repository.get_cart_items(session, user_id))


def _extract_pending_action_id(result: str) -> str:
    match = re.search(r"pending_action_id[^0-9a-f]*([0-9a-f-]+)", result)
    assert match is not None, result
    return match.group(1)


def test_product_tool_reads_from_postgres():
    result = search_products.invoke({"query": "keyboard", "limit": 1})

    assert "TECH-" in result
    assert "Keyboards" in result


def test_preference_tools_write_read_and_clear_postgres(smoke_user_id):
    add_result = add_user_preference.invoke(
        {
            "user_id": smoke_user_id,
            "preference_type": "brand",
            "preference_value": "Logitech",
        }
    )
    get_result = get_user_preferences.invoke({"user_id": smoke_user_id})
    preferences = _get_preferences(smoke_user_id)
    clear_result = clear_user_preferences.invoke({"user_id": smoke_user_id})

    assert smoke_user_id in add_result
    assert "Logitech" in get_result
    assert len(preferences) == 1
    assert preferences[0]["preference_value"] == "Logitech"
    assert smoke_user_id in clear_result
    assert _get_preferences(smoke_user_id) == []


def test_cart_tools_prepare_confirm_and_clear_postgres(smoke_user_id):
    product_id = _get_smoke_product_id()

    prepare_result = prepare_add_to_cart.invoke(
        {
            "user_id": smoke_user_id,
            "product_id": product_id,
            "quantity": 2,
            "thread_id": "integration-tool-thread",
        }
    )
    pending_action_id = _extract_pending_action_id(prepare_result)
    empty_cart_result = get_cart_items.invoke({"user_id": smoke_user_id})
    other_user_id = f"{smoke_user_id}-other"
    confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": other_user_id}
    )
    confirm_result = confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": smoke_user_id}
    )
    confirm_add_to_cart.invoke(
        {"pending_action_id": pending_action_id, "user_id": smoke_user_id}
    )
    cart_result = get_cart_items.invoke({"user_id": smoke_user_id})
    cart_items = _get_cart_items(smoke_user_id)
    clear_result = clear_cart_items.invoke({"user_id": smoke_user_id})

    assert pending_action_id
    assert product_id not in empty_cart_result
    assert _get_cart_items(other_user_id) == []
    assert product_id in confirm_result
    assert product_id in cart_result
    assert len(cart_items) == 1
    assert cart_items[0]["quantity"] == 2
    assert smoke_user_id in clear_result
    assert _get_cart_items(smoke_user_id) == []
