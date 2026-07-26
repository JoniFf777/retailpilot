from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ConversationMessage, ConversationThread
from app.repositories.runtime_conversations import (
    append_conversation_message,
    create_conversation_summary,
    get_or_create_conversation_thread,
)
from app.repositories.runtime_maintenance import prune_runtime_persistence
from app.repositories.runtime_runs import create_agent_run, save_idempotency_record
from app.repositories.runtime_memory import create_memory_record
from app.repositories.governance_audit import append_governance_audit_record
from app.security import (
    AuditDecision,
    AuditOperation,
    AuditReason,
    GovernanceAuditFactory,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_prune_runtime_persistence_deletes_expired_rows():
    session = make_session()
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    active_thread = get_or_create_conversation_thread(
        session,
        user_id="user-active",
        client_thread_id="thread-active",
        now=now,
        expires_at=now + timedelta(days=5),
    )
    expired_thread = get_or_create_conversation_thread(
        session,
        user_id="user-expired",
        client_thread_id="thread-expired",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    append_conversation_message(
        session,
        thread_id=active_thread["thread_id"],
        user_id="user-active",
        role="user",
        content_text="keep me",
        now=now,
        expires_at=now + timedelta(days=1),
    )
    append_conversation_message(
        session,
        thread_id=expired_thread["thread_id"],
        user_id="user-expired",
        role="user",
        content_text="delete me",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    create_agent_run(
        session,
        run_id="run-expired",
        thread_id=expired_thread["thread_id"],
        user_id="user-expired",
        operation="chat",
        mode="multi",
        status="started",
        request_id="request-expired",
        trace_id="trace-expired",
        started_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    create_conversation_summary(
        session,
        thread_id=expired_thread["thread_id"],
        user_id="user-expired",
        start_message_sequence=1,
        end_message_sequence=1,
        summary_text="expired summary",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    save_idempotency_record(
        session,
        user_id="user-expired",
        thread_id=expired_thread["thread_id"],
        run_id="run-expired",
        operation="chat",
        idempotency_key="idem-expired",
        request_hash="hash-expired",
        status="completed",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    create_memory_record(
        session,
        memory_kind="long_term",
        scope="user",
        user_id="user-expired",
        content_text="expired memory",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    audit = GovernanceAuditFactory(
        clock=lambda: now - timedelta(days=10)
    ).action_decision(
        operation=AuditOperation.ACTION_CONFIRM,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.COMPLETED,
        action_type="add_to_cart",
        action_id="expired-action",
        principal=None,
        owner_id="user-expired",
    )
    append_governance_audit_record(
        session,
        record=audit,
        expires_at=now - timedelta(days=1),
        now=now - timedelta(days=10),
    )
    session.commit()

    report = prune_runtime_persistence(session, now=now)
    session.commit()

    remaining_threads = list(session.scalars(select(ConversationThread)))
    remaining_messages = list(session.scalars(select(ConversationMessage)))

    assert report.deleted_threads == 1
    assert report.deleted_runs == 1
    assert report.deleted_messages == 1
    assert report.deleted_summaries == 1
    assert report.deleted_idempotency_records == 1
    assert report.deleted_memory_records == 1
    assert report.deleted_governance_audit_records == 1
    assert report.deleted_total == 7
    assert [thread.user_id for thread in remaining_threads] == ["user-active"]
    assert [message.content_text for message in remaining_messages] == ["keep me"]
