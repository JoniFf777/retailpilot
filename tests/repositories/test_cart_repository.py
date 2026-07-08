from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Product
from app.repositories.cart import (
    CONFIRMED_STATUS,
    PENDING_STATUS,
    clear_cart_items,
    confirm_add_to_cart,
    get_cart_items,
    prepare_add_to_cart,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed_product(session):
    session.add(
        Product(
            product_id="TECH-KEY-010",
            name="Mechanical Keyboard",
            category="Keyboards",
            price=129.00,
            in_stock=True,
        )
    )
    session.commit()


def test_prepare_add_to_cart_creates_pending_action_only():
    session = make_session()
    seed_product(session)

    result = prepare_add_to_cart(
        session, user_id="user-1", product_id="TECH-KEY-010", quantity=2
    )
    session.commit()

    assert result["status"] == PENDING_STATUS
    assert result["pending_action_id"]
    assert get_cart_items(session, "user-1") == []


def test_confirm_add_to_cart_writes_cart_item():
    session = make_session()
    seed_product(session)
    prepare_result = prepare_add_to_cart(
        session, user_id="user-1", product_id="TECH-KEY-010", quantity=2
    )
    session.commit()

    confirm_result = confirm_add_to_cart(
        session, prepare_result["pending_action_id"], "user-1"
    )
    session.commit()
    cart_items = get_cart_items(session, "user-1")

    assert confirm_result["status"] == CONFIRMED_STATUS
    assert len(cart_items) == 1
    assert cart_items[0]["product_id"] == "TECH-KEY-010"
    assert cart_items[0]["quantity"] == 2


def test_confirm_add_to_cart_rejects_user_mismatch():
    session = make_session()
    seed_product(session)
    prepare_result = prepare_add_to_cart(
        session, user_id="user-1", product_id="TECH-KEY-010", quantity=1
    )
    session.commit()

    result = confirm_add_to_cart(session, prepare_result["pending_action_id"], "user-2")

    assert result["status"] == "error"
    assert result["message"] == "user mismatch"
    assert get_cart_items(session, "user-1") == []


def test_confirm_add_to_cart_rejects_duplicate_confirmation():
    session = make_session()
    seed_product(session)
    prepare_result = prepare_add_to_cart(
        session, user_id="user-1", product_id="TECH-KEY-010", quantity=1
    )
    session.commit()

    first = confirm_add_to_cart(session, prepare_result["pending_action_id"], "user-1")
    second = confirm_add_to_cart(session, prepare_result["pending_action_id"], "user-1")

    assert first["status"] == CONFIRMED_STATUS
    assert second["status"] == "error"
    assert second["current_status"] == CONFIRMED_STATUS


def test_clear_cart_items_removes_cart_and_pending_actions():
    session = make_session()
    seed_product(session)
    prepare_add_to_cart(session, user_id="user-1", product_id="TECH-KEY-010")
    confirmed = prepare_add_to_cart(session, user_id="user-1", product_id="TECH-KEY-010")
    confirm_add_to_cart(session, confirmed["pending_action_id"], "user-1")
    session.commit()

    result = clear_cart_items(session, "user-1")
    session.commit()

    assert result["deleted_cart_items"] == 1
    assert result["deleted_pending_actions"] == 2
    assert get_cart_items(session, "user-1") == []
