from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.repositories.runtime_conversations import (
    append_conversation_message,
    create_conversation_summary,
    get_or_create_conversation_thread,
    list_conversation_messages,
    list_conversation_summaries,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_get_or_create_conversation_thread_reuses_user_scoped_thread():
    session = make_session()
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)

    first = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
        metadata={"source": "api"},
        now=now,
    )
    second = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
        metadata={"phase": "v4.1"},
        now=now,
    )

    assert first["thread_id"] == second["thread_id"]
    assert second["metadata"] == {"source": "api", "phase": "v4.1"}


def test_append_conversation_message_assigns_per_thread_sequence_and_touches_thread():
    session = make_session()
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    thread = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
        now=now,
    )

    first = append_conversation_message(
        session,
        thread_id=thread["thread_id"],
        user_id="user-1",
        role="user",
        content_text="hello",
        now=now,
    )
    second = append_conversation_message(
        session,
        thread_id=thread["thread_id"],
        user_id="user-1",
        role="assistant",
        content_text="hi",
        now=now,
    )
    session.commit()

    messages = list_conversation_messages(session, thread_id=thread["thread_id"])

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert [message["content_text"] for message in messages] == ["hello", "hi"]


def test_create_conversation_summary_tracks_message_range():
    session = make_session()
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    thread = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
        now=now,
    )
    append_conversation_message(
        session,
        thread_id=thread["thread_id"],
        user_id="user-1",
        role="user",
        content_text="first",
        now=now,
    )
    append_conversation_message(
        session,
        thread_id=thread["thread_id"],
        user_id="user-1",
        role="assistant",
        content_text="second",
        now=now,
    )

    summary = create_conversation_summary(
        session,
        thread_id=thread["thread_id"],
        user_id="user-1",
        start_message_sequence=1,
        end_message_sequence=2,
        summary_text="conversation summary",
        summary_json={"kind": "episodic"},
        now=now,
    )
    session.commit()

    summaries = list_conversation_summaries(session, thread_id=thread["thread_id"])

    assert summary["start_message_sequence"] == 1
    assert summary["end_message_sequence"] == 2
    assert summaries[0]["summary_text"] == "conversation summary"
