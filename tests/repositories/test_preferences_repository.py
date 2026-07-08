from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.repositories.preferences import (
    add_user_preference,
    clear_user_preferences,
    get_user_preferences,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_add_get_and_clear_user_preferences():
    session = make_session()

    created = add_user_preference(
        session,
        user_id="user-1",
        preference_type="budget",
        preference_value="under 1000",
    )
    session.commit()

    preferences = get_user_preferences(session, "user-1")
    clear_result = clear_user_preferences(session, "user-1")
    session.commit()

    assert created["preference_type"] == "budget"
    assert len(preferences) == 1
    assert preferences[0]["preference_value"] == "under 1000"
    assert clear_result["deleted_count"] == 1
    assert get_user_preferences(session, "user-1") == []


def test_invalid_preference_type_is_saved_as_other():
    session = make_session()

    created = add_user_preference(
        session,
        user_id="user-1",
        preference_type="surprise",
        preference_value="quiet keyboards",
    )

    assert created["preference_type"] == "other"
    assert created["was_invalid_type"] is True
