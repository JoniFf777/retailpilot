from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.operations import load_runtime_cleanup_evidence
from app.repositories.runtime_conversations import (
    append_conversation_message,
    get_or_create_conversation_thread,
)
from app.repositories.runtime_runs import create_agent_run, save_idempotency_record
from scripts import cleanup_runtime_persistence


def make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_run_cleanup_deletes_expired_runtime_rows(
    monkeypatch,
    capsys,
    tmp_path,
):
    Session = make_session_factory()
    session = Session()
    now = datetime.now(timezone.utc)
    thread = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    append_conversation_message(
        session,
        thread_id=thread["thread_id"],
        user_id="user-1",
        role="user",
        content_text="expired",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    create_agent_run(
        session,
        run_id="run-1",
        thread_id=thread["thread_id"],
        user_id="user-1",
        operation="chat",
        mode="multi",
        status="started",
        request_id="request-1",
        trace_id="trace-1",
        started_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    save_idempotency_record(
        session,
        user_id="user-1",
        thread_id=thread["thread_id"],
        run_id="run-1",
        operation="chat",
        idempotency_key="idem-1",
        request_hash="hash-1",
        status="started",
        now=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        cleanup_runtime_persistence,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=(
                "postgresql+psycopg://user:secret@127.0.0.1:5432/app"
            ),
            shopmind_runtime_cleanup_evidence_path=str(
                tmp_path / "cleanup-evidence.json"
            ),
        ),
    )

    report = cleanup_runtime_persistence.run_cleanup(session_factory=Session)
    output = capsys.readouterr().out

    assert report.deleted_threads == 1
    assert report.deleted_runs == 1
    assert report.deleted_messages == 1
    assert report.deleted_idempotency_records == 1
    assert report.deleted_memory_records == 0
    assert report.deleted_governance_audit_records == 0
    assert report.deleted_total == 4
    assert "user:***" in output
    evidence = load_runtime_cleanup_evidence(
        tmp_path / "cleanup-evidence.json"
    )
    assert evidence is not None
    assert evidence.status == "succeeded"
