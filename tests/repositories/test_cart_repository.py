from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import PendingAction, Product, UserPreference
from app.repositories.cart import (
    CONFIRMED_STATUS,
    EXPIRED_STATUS,
    PENDING_STATUS,
    clear_cart_items,
    confirm_add_to_cart,
    confirm_save_preference,
    get_cart_items,
    prepare_add_to_cart,
    prepare_save_preference,
    resolve_pending_action,
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


def test_prepare_add_to_cart_persists_action_preview_and_expiry():
    session = make_session()
    seed_product(session)

    result = prepare_add_to_cart(
        session,
        user_id="user-1",
        product_id="TECH-KEY-010",
        quantity=2,
        thread_id="thread-1",
    )
    action = session.get(PendingAction, result["pending_action_id"])

    assert action.risk_class == "high"
    assert "Mechanical Keyboard" in action.preview_text
    assert action.expires_at is not None


def test_confirm_add_to_cart_rejects_thread_mismatch():
    session = make_session()
    seed_product(session)
    prepare_result = prepare_add_to_cart(
        session,
        user_id="user-1",
        product_id="TECH-KEY-010",
        thread_id="thread-1",
    )

    result = confirm_add_to_cart(
        session,
        prepare_result["pending_action_id"],
        "user-1",
        thread_id="other-thread",
    )

    assert result == {"status": "error", "message": "thread mismatch"}
    assert get_cart_items(session, "user-1") == []


def test_confirm_add_to_cart_expires_action_before_cart_write():
    session = make_session()
    seed_product(session)
    prepare_result = prepare_add_to_cart(
        session,
        user_id="user-1",
        product_id="TECH-KEY-010",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    result = confirm_add_to_cart(
        session, prepare_result["pending_action_id"], "user-1"
    )

    assert result == {"status": "error", "message": "pending action expired"}
    assert get_cart_items(session, "user-1") == []
    action = session.get(PendingAction, prepare_result["pending_action_id"])
    assert action.status == EXPIRED_STATUS


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


def test_save_preference_action_is_resolved_and_confirmed_generically():
    session = make_session()
    prepared = prepare_save_preference(
        session,
        user_id="user-1",
        preference_type="style",
        preference_value="quiet keyboard",
        thread_id="thread-1",
    )
    session.commit()

    resolved = resolve_pending_action(
        session,
        prepared["pending_action_id"],
        "user-1",
        thread_id="thread-1",
    )
    confirmed = confirm_save_preference(
        session,
        prepared["pending_action_id"],
        "user-1",
        thread_id="thread-1",
    )
    session.commit()

    assert resolved["action_type"] == "save_preference"
    assert resolved["risk_class"] == "medium"
    assert resolved["preview"] == "Save style preference: quiet keyboard"
    assert confirmed["status"] == CONFIRMED_STATUS
    preferences = session.query(UserPreference).all()
    assert len(preferences) == 1
    assert preferences[0].preference_value == "quiet keyboard"


def test_save_preference_action_rejects_scope_duplicate_and_expiry():
    session = make_session()
    scoped = prepare_save_preference(
        session,
        user_id="user-1",
        preference_type="brand",
        preference_value="Acme",
        thread_id="thread-1",
    )
    expired = prepare_save_preference(
        session,
        user_id="user-1",
        preference_type="avoid",
        preference_value="glossy screens",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    session.commit()

    assert resolve_pending_action(
        session, scoped["pending_action_id"], "user-2"
    )["message"] == "user mismatch"
    assert confirm_save_preference(
        session,
        scoped["pending_action_id"],
        "user-1",
        thread_id="wrong-thread",
    )["message"] == "thread mismatch"
    assert confirm_save_preference(
        session, scoped["pending_action_id"], "user-1", thread_id="thread-1"
    )["status"] == CONFIRMED_STATUS
    assert confirm_save_preference(
        session, scoped["pending_action_id"], "user-1", thread_id="thread-1"
    )["current_status"] == CONFIRMED_STATUS
    assert confirm_save_preference(
        session, expired["pending_action_id"], "user-1"
    )["message"] == "pending action expired"
    assert session.get(PendingAction, expired["pending_action_id"]).status == (
        EXPIRED_STATUS
    )


def test_confirm_add_to_cart_applies_quantity_edit_atomically():
    session = make_session()
    seed_product(session)
    prepared = prepare_add_to_cart(
        session,
        user_id="edit-user",
        product_id="TECH-KEY-010",
        quantity=1,
        thread_id="edit-thread",
    )
    session.commit()

    result = confirm_add_to_cart(
        session,
        prepared["pending_action_id"],
        "edit-user",
        thread_id="edit-thread",
        updated_arguments={"quantity": 3},
    )
    session.commit()

    action = session.get(PendingAction, prepared["pending_action_id"])
    assert result["status"] == CONFIRMED_STATUS
    assert result["quantity"] == 3
    assert result["updated_arguments"] == {"quantity": 3}
    assert action.payload_json == {"product_id": "TECH-KEY-010", "quantity": 3}
    assert "Add 3 x" in action.preview_text
    assert get_cart_items(session, "edit-user")[0]["quantity"] == 3


def test_confirm_save_preference_applies_exact_edit_fields_atomically():
    session = make_session()
    prepared = prepare_save_preference(
        session,
        user_id="edit-user",
        preference_type="style",
        preference_value="quiet keyboard",
        thread_id="edit-thread",
    )
    session.commit()

    result = confirm_save_preference(
        session,
        prepared["pending_action_id"],
        "edit-user",
        thread_id="edit-thread",
        updated_arguments={
            "preference_type": "avoid",
            "preference_value": " glossy screens ",
        },
    )
    session.commit()

    action = session.get(PendingAction, prepared["pending_action_id"])
    assert result["status"] == CONFIRMED_STATUS
    assert result["preference"]["preference_type"] == "avoid"
    assert result["preference"]["preference_value"] == "glossy screens"
    assert action.payload_json == {
        "preference_type": "avoid",
        "preference_value": "glossy screens",
    }
    assert action.preview_text == "Save avoid preference: glossy screens"


def test_invalid_action_edit_leaves_pending_payload_unchanged():
    session = make_session()
    seed_product(session)
    prepared = prepare_add_to_cart(
        session,
        user_id="edit-user",
        product_id="TECH-KEY-010",
        quantity=1,
    )
    session.commit()

    result = confirm_add_to_cart(
        session,
        prepared["pending_action_id"],
        "edit-user",
        updated_arguments={"product_id": "OTHER"},
    )
    session.rollback()

    action = session.get(PendingAction, prepared["pending_action_id"])
    assert result == {"status": "error", "message": "invalid updated arguments"}
    assert action.status == PENDING_STATUS
    assert action.payload_json == {"product_id": "TECH-KEY-010", "quantity": 1}
    assert get_cart_items(session, "edit-user") == []
