from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.repositories.runtime_conversations import (
    append_conversation_message,
    get_or_create_conversation_thread,
)
from app.repositories.runtime_memory import create_memory_record
from app.runtime import RunContext, RunOperation, RunRequest
from app.runtime.context import RuntimeContextManager


def make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_context_manager_builds_bounded_deduplicated_user_thread_slice():
    session_factory = make_session_factory()
    session = session_factory()
    thread = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
    )
    append_conversation_message(
        session,
        thread_id=thread["thread_id"],
        user_id="user-1",
        role="user",
        content_text="same preference",
    )
    create_memory_record(
        session,
        memory_kind="long_term",
        scope="user",
        user_id="user-1",
        content_text="same preference",
        priority=90,
        token_count=3,
    )
    create_memory_record(
        session,
        memory_kind="long_term",
        scope="user",
        user_id="user-2",
        content_text="private other user memory",
        priority=100,
        token_count=4,
    )
    session.commit()
    session.close()

    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
        input_text="current question",
        budget={"max_prompt_tokens": 20},
    )
    context = RunContext(
        request=request,
        runtime_thread_id=thread["thread_id"],
        started_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )

    result = RuntimeContextManager(session_factory).build(context)

    contents = [item.content for item in result.items]
    assert "current question" in contents
    assert contents.count("same preference") == 1
    assert "private other user memory" not in contents
    assert result.estimated_tokens <= 20
    assert context.memory_references
