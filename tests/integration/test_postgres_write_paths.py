import os
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


@pytest.fixture
def postgres_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def smoke_user_id(postgres_session):
    user_id = f"integration-smoke-{uuid.uuid4()}"
    _clear_user_state(postgres_session, user_id)
    postgres_session.commit()
    try:
        yield user_id
    finally:
        _clear_user_state(postgres_session, user_id)
        postgres_session.commit()


def _clear_user_state(session, user_id: str) -> None:
    preference_repository.clear_user_preferences(session, user_id)
    cart_repository.clear_cart_items(session, user_id)


def _get_smoke_product_id(session) -> str:
    products = product_repository.search_products(
        session, query="keyboard", in_stock_only=True, limit=1
    )
    assert products, "seeded PostgreSQL database should contain a keyboard product"
    return products[0]["product_id"]


def test_postgres_preference_write_path(postgres_session, smoke_user_id):
    created = preference_repository.add_user_preference(
        postgres_session,
        user_id=smoke_user_id,
        preference_type="brand",
        preference_value="Logitech",
    )
    postgres_session.commit()

    preferences = preference_repository.get_user_preferences(
        postgres_session, smoke_user_id
    )
    clear_result = preference_repository.clear_user_preferences(
        postgres_session, smoke_user_id
    )
    postgres_session.commit()

    assert created["preference_type"] == "brand"
    assert preferences[0]["preference_value"] == "Logitech"
    assert clear_result["deleted_count"] == 1
    assert preference_repository.get_user_preferences(postgres_session, smoke_user_id) == []


def test_postgres_cart_pending_confirm_write_path(postgres_session, smoke_user_id):
    product_id = _get_smoke_product_id(postgres_session)

    prepared = cart_repository.prepare_add_to_cart(
        postgres_session,
        user_id=smoke_user_id,
        product_id=product_id,
        quantity=2,
        thread_id="integration-smoke-thread",
    )
    postgres_session.commit()

    assert prepared["status"] == cart_repository.PENDING_STATUS
    assert cart_repository.get_cart_items(postgres_session, smoke_user_id) == []

    mismatch = cart_repository.confirm_add_to_cart(
        postgres_session, prepared["pending_action_id"], "different-user"
    )
    confirmed = cart_repository.confirm_add_to_cart(
        postgres_session, prepared["pending_action_id"], smoke_user_id
    )
    duplicate = cart_repository.confirm_add_to_cart(
        postgres_session, prepared["pending_action_id"], smoke_user_id
    )
    postgres_session.commit()

    cart_items = cart_repository.get_cart_items(postgres_session, smoke_user_id)

    assert mismatch["status"] == "error"
    assert mismatch["message"] == "user mismatch"
    assert confirmed["status"] == cart_repository.CONFIRMED_STATUS
    assert duplicate["status"] == "error"
    assert duplicate["current_status"] == cart_repository.CONFIRMED_STATUS
    assert len(cart_items) == 1
    assert cart_items[0]["product_id"] == product_id
    assert cart_items[0]["quantity"] == 2
