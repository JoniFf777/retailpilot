from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest
from datetime import datetime, timedelta, timezone

from app.db.base import Base
from app.db.models import ConversationThread
from app.repositories.runtime_shopping_state import (
    ShoppingSessionStateConflict,
    persist_shopping_session_state,
)
from app.recommendation.session_state import ShoppingSessionState


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_shopping_session_state_is_owner_scoped_and_monotonic() -> None:
    session = make_session()
    session.add(ConversationThread(id="runtime-1", user_id="user-1", status="active"))
    session.commit()
    state = ShoppingSessionState(
        owner_id="user-1",
        thread_id="client-1",
        version=1,
        category="laptop",
        budget_max="6000",
    )
    persisted = persist_shopping_session_state(
        session,
        runtime_thread_id="runtime-1",
        user_id="user-1",
        state=state,
    )
    assert persisted.version == 1
    assert (
        session.get(ConversationThread, "runtime-1").metadata_json[
            "shopping_session_state"
        ]["version"]
        == 1
    )

    with pytest.raises(ShoppingSessionStateConflict):
        persist_shopping_session_state(
            session,
            runtime_thread_id="runtime-1",
            user_id="user-1",
            state=state.model_copy(update={"version": 3}),
        )


def test_shopping_session_state_rejects_cross_owner_thread() -> None:
    session = make_session()
    session.add(ConversationThread(id="runtime-2", user_id="owner-a", status="active"))
    session.commit()
    with pytest.raises(ShoppingSessionStateConflict):
        persist_shopping_session_state(
            session,
            runtime_thread_id="runtime-2",
            user_id="owner-b",
            state=ShoppingSessionState(
                owner_id="owner-b", version=1, category="laptop"
            ),
        )


def test_shopping_session_state_keeps_bounded_patch_log_and_expiry() -> None:
    session = make_session()
    session.add(ConversationThread(id="runtime-3", user_id="owner-a", status="active"))
    session.commit()
    first = persist_shopping_session_state(
        session,
        runtime_thread_id="runtime-3",
        user_id="owner-a",
        state=ShoppingSessionState(
            owner_id="owner-a",
            thread_id="runtime-3",
            version=1,
            category="laptop",
            candidate_sku_codes=["sku-1"],
            candidate_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        ),
    )
    assert first.current_candidate_sku_codes() == []
    second = persist_shopping_session_state(
        session,
        runtime_thread_id="runtime-3",
        user_id="owner-a",
        state=first.model_copy(
            update={
                "version": 2,
                "budget_max": "6000",
                "candidate_sku_codes": ["sku-2"],
            }
        ),
    )
    metadata = session.get(ConversationThread, "runtime-3").metadata_json
    assert second.version == 2
    assert [item["version"] for item in metadata["shopping_session_state_patches"]] == [
        1,
        2,
    ]
    assert metadata["shopping_session_state_patches"][1]["changed_fields"] == [
        "budget_max",
        "candidate_sku_codes",
    ]


def test_shopping_session_state_rejects_mismatched_owner_identity() -> None:
    session = make_session()
    session.add(ConversationThread(id="runtime-4", user_id="owner-a", status="active"))
    session.commit()
    with pytest.raises(ShoppingSessionStateConflict):
        persist_shopping_session_state(
            session,
            runtime_thread_id="runtime-4",
            user_id="owner-a",
            state=ShoppingSessionState(
                owner_id="owner-b", thread_id="other", version=1
            ),
        )
