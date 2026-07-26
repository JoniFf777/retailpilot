from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.repositories.runtime_conversations import get_or_create_conversation_thread
from app.repositories.runtime_memory import (
    create_memory_record,
    list_memory_records,
    soft_delete_memory_record,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_memory_records_are_scoped_to_user_and_thread():
    session = make_session()
    thread = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
    )
    create_memory_record(
        session,
        memory_kind="long_term",
        scope="user",
        user_id="user-1",
        content_text="prefers quiet keyboards",
        priority=80,
    )
    create_memory_record(
        session,
        memory_kind="long_term",
        scope="user",
        user_id="user-2",
        content_text="must not leak",
        priority=100,
    )
    create_memory_record(
        session,
        memory_kind="episodic",
        scope="thread",
        user_id="user-1",
        thread_id=thread["thread_id"],
        content_text="same thread fact",
        priority=90,
    )
    session.commit()

    records = list_memory_records(
        session,
        user_id="user-1",
        thread_id=thread["thread_id"],
    )

    assert [record["content"] for record in records] == [
        "same thread fact",
        "prefers quiet keyboards",
    ]


def test_memory_records_filter_expiry_and_support_soft_delete():
    session = make_session()
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    active = create_memory_record(
        session,
        memory_kind="long_term",
        scope="user",
        user_id="user-1",
        content_text="active",
        expires_at=now + timedelta(days=1),
        now=now,
    )
    create_memory_record(
        session,
        memory_kind="long_term",
        scope="user",
        user_id="user-1",
        content_text="expired",
        expires_at=now - timedelta(seconds=1),
        now=now,
    )
    session.commit()

    assert soft_delete_memory_record(
        session,
        memory_id=active["memory_id"],
        user_id="user-1",
        now=now,
    )
    session.commit()

    assert list_memory_records(session, user_id="user-1", thread_id=None, now=now) == []
