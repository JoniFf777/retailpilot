from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.repositories.runtime_conversations import get_or_create_conversation_thread
from app.repositories.runtime_runs import (
    append_agent_run_event,
    create_agent_run,
    finalize_agent_run,
    get_agent_run,
    get_idempotency_record,
    inspect_owner_agent_run,
    list_agent_run_events,
    save_idempotency_record,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_create_and_finalize_agent_run_with_events():
    session = make_session()
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    thread = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
        now=now,
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
        started_at=now,
        input_text="recommend a keyboard",
        request_json={"message": "recommend a keyboard"},
    )
    append_agent_run_event(
        session,
        run_id="run-1",
        thread_id=thread["thread_id"],
        user_id="user-1",
        event_type="run.started",
        visibility="client",
        trace_id="trace-1",
    )
    finalized = finalize_agent_run(
        session,
        run_id="run-1",
        status="completed",
        completed_at=now,
        output_text="Try MX Keys.",
        result_json={"status": "completed"},
        usage_json={"step_count": 3},
        tool_call_records_json=[{"tool_name": "search_products"}],
    )
    session.commit()

    events = list_agent_run_events(session, run_id="run-1")

    assert finalized is not None
    assert finalized["status"] == "completed"
    assert finalized["output_text"] == "Try MX Keys."
    assert events[0]["sequence"] == 1
    assert events[0]["event_type"] == "run.started"
    assert get_agent_run(session, run_id="run-1")["output_text"] == "Try MX Keys."


def test_save_idempotency_record_upserts_same_scope():
    session = make_session()
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    thread = get_or_create_conversation_thread(
        session,
        user_id="user-1",
        client_thread_id="thread-1",
        now=now,
    )

    first = save_idempotency_record(
        session,
        user_id="user-1",
        thread_id=thread["thread_id"],
        run_id="run-1",
        operation="chat",
        idempotency_key="idem-1",
        request_hash="hash-1",
        status="started",
        metadata={"attempt": 1},
        now=now,
    )
    second = save_idempotency_record(
        session,
        user_id="user-1",
        thread_id=thread["thread_id"],
        run_id="run-1",
        operation="chat",
        idempotency_key="idem-1",
        request_hash="hash-1",
        status="completed",
        response_fingerprint="response-1",
        metadata={"attempt": 2},
        now=now,
    )
    session.commit()

    record = get_idempotency_record(
        session,
        user_id="user-1",
        operation="chat",
        idempotency_key="idem-1",
    )

    assert first["idempotency_record_id"] == second["idempotency_record_id"]
    assert record is not None
    assert record["status"] == "completed"
    assert record["response_fingerprint"] == "response-1"
    assert record["metadata"] == {"attempt": 2}


def test_owner_run_inspection_is_exact_scoped_bounded_and_payload_free():
    session = make_session()
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    thread = get_or_create_conversation_thread(
        session,
        user_id="owner-1",
        client_thread_id="thread-1",
        now=now,
    )
    create_agent_run(
        session,
        run_id="run-private-1",
        thread_id=thread["thread_id"],
        user_id="owner-1",
        operation="chat",
        mode="multi",
        status="started",
        request_id="private-request-id",
        trace_id="trace-private-1",
        started_at=now,
        input_text="private input",
        request_json={"message": "private input"},
    )
    append_agent_run_event(
        session,
        run_id="run-private-1",
        thread_id=thread["thread_id"],
        user_id="owner-1",
        event_type="run.started",
        visibility="client",
        trace_id="trace-private-1",
        payload_json={"private": "client payload"},
    )
    append_agent_run_event(
        session,
        run_id="run-private-1",
        thread_id=thread["thread_id"],
        user_id="owner-1",
        event_type="context.built",
        visibility="internal",
        trace_id="trace-private-1",
        payload_json={"private": "internal payload"},
    )
    append_agent_run_event(
        session,
        run_id="run-private-1",
        thread_id=thread["thread_id"],
        user_id="owner-1",
        event_type="run.completed",
        visibility="client",
        trace_id="trace-private-1",
        payload_json={"private": "terminal payload"},
    )
    finalize_agent_run(
        session,
        run_id="run-private-1",
        status="completed",
        completed_at=now,
        output_text="private output",
        result_json={"answer": "private output"},
        error_json={"message": "private error"},
        usage_json={"step_count": 2, "tool_call_count": 1},
        debug_json={"private": "debug"},
        metadata={"private": "metadata"},
    )
    session.commit()

    by_run = inspect_owner_agent_run(
        session,
        owner_id="owner-1",
        run_id="run-private-1",
        event_limit=1,
    )
    by_trace = inspect_owner_agent_run(
        session,
        owner_id="owner-1",
        trace_id="trace-private-1",
        event_limit=10,
    )
    denied = inspect_owner_agent_run(
        session,
        owner_id="owner-2",
        run_id="run-private-1",
        event_limit=10,
    )

    assert by_run is not None
    assert by_run["client_event_count"] == 2
    assert by_run["events_truncated"] is True
    assert [event["event_type"] for event in by_run["events"]] == [
        "run.started"
    ]
    assert by_trace is not None
    assert [event["event_type"] for event in by_trace["events"]] == [
        "run.started",
        "run.completed",
    ]
    assert denied is None
    serialized = str(by_trace)
    for forbidden in (
        "private input",
        "private output",
        "private error",
        "client payload",
        "internal payload",
        "private-request-id",
        "debug",
        "metadata",
        "payload_json",
    ):
        assert forbidden not in serialized
