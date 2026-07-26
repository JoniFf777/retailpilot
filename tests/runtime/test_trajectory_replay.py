from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import AgentRun, AgentRunEvent
from app.runtime import (
    RunOperation,
    RunRequest,
    RuntimeTrajectoryRecorder,
    RuntimeTrajectoryReplayer,
    ShopMindRuntimeHarness,
    TrajectoryReplayError,
)


def make_shared_session_factories():
    database_name = f"shopmind-replay-{uuid4()}"
    database_url = (
        f"sqlite+pysqlite:///file:{database_name}"
        "?mode=memory&cache=shared&uri=true"
    )
    writer_engine = create_engine(database_url)
    Base.metadata.create_all(writer_engine)
    reader_engine = create_engine(database_url)
    return (
        sessionmaker(bind=writer_engine, expire_on_commit=False),
        sessionmaker(bind=reader_engine, expire_on_commit=False),
        writer_engine,
        reader_engine,
    )


def persist_sample_run(writer_factory):
    harness = ShopMindRuntimeHarness(session_factory=writer_factory)

    def executor(context):
        context.emit_event(
            "provider.fallback",
            agent_name="supervisor",
            payload={
                "reason": "provider_error_or_invalid_contract",
                "private_detail": "provider secret must not be recorded",
            },
        )
        return {
            "answer": "safe deterministic answer",
            "status": "completed",
            "output_data": {"decision": "fallback"},
        }

    return harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="replay-user",
            thread_id="replay-client-thread",
            input_text="private user request",
            idempotency_key="replay-key",
        ),
        executor,
    )


def test_records_and_replays_persisted_trajectory_across_engine_boundary() -> None:
    writer_factory, reader_factory, writer_engine, reader_engine = (
        make_shared_session_factories()
    )
    result = persist_sample_run(writer_factory)
    recorded = RuntimeTrajectoryRecorder(writer_factory).record(
        run_id=result.run_id,
        user_id=result.user_id,
        runtime_thread_id=result.runtime_thread_id,
    )

    replay = RuntimeTrajectoryReplayer(reader_factory).replay(recorded)

    assert replay.matches is True
    assert replay.differences == ()
    assert replay.recorded_fingerprint == replay.observed_fingerprint
    assert [event.sequence for event in recorded.events] == list(
        range(1, recorded.event_count + 1)
    )
    assert recorded.events[0].event_type == "run.started"
    assert recorded.events[-1].event_type == "run.completed"
    fallback = next(
        event for event in recorded.events if event.event_type == "provider.fallback"
    )
    assert fallback.classification == {
        "reason": "provider_error_or_invalid_contract"
    }
    serialized = recorded.model_dump_json()
    assert "provider secret must not be recorded" not in serialized
    assert "private user request" not in serialized
    assert "safe deterministic answer" not in serialized
    writer_engine.dispose()
    reader_engine.dispose()


def test_recorder_rejects_cross_scope_and_non_terminal_runs() -> None:
    writer_factory, _, writer_engine, reader_engine = make_shared_session_factories()
    result = persist_sample_run(writer_factory)
    recorder = RuntimeTrajectoryRecorder(writer_factory)

    with pytest.raises(TrajectoryReplayError, match="scope is invalid"):
        recorder.record(
            run_id=result.run_id,
            user_id="other-user",
            runtime_thread_id=result.runtime_thread_id,
        )

    session = writer_factory()
    try:
        run = session.get(AgentRun, result.run_id)
        run.status = "started"
        session.commit()
    finally:
        session.close()

    with pytest.raises(TrajectoryReplayError, match="not terminal"):
        recorder.record(
            run_id=result.run_id,
            user_id=result.user_id,
            runtime_thread_id=result.runtime_thread_id,
        )
    writer_engine.dispose()
    reader_engine.dispose()


def test_recorder_rejects_broken_event_identity_and_sequence() -> None:
    writer_factory, _, writer_engine, reader_engine = make_shared_session_factories()
    result = persist_sample_run(writer_factory)
    recorder = RuntimeTrajectoryRecorder(writer_factory)
    session = writer_factory()
    try:
        event = (
            session.query(AgentRunEvent)
            .filter(AgentRunEvent.run_id == result.run_id)
            .order_by(AgentRunEvent.sequence.asc())
            .first()
        )
        event.trace_id = "different-trace"
        session.commit()
    finally:
        session.close()

    with pytest.raises(TrajectoryReplayError, match="identity is invalid"):
        recorder.record(
            run_id=result.run_id,
            user_id=result.user_id,
            runtime_thread_id=result.runtime_thread_id,
        )

    session = writer_factory()
    try:
        event = (
            session.query(AgentRunEvent)
            .filter(AgentRunEvent.run_id == result.run_id)
            .order_by(AgentRunEvent.sequence.asc())
            .first()
        )
        event.trace_id = result.trace_id
        event.sequence = 9
        session.commit()
    finally:
        session.close()

    with pytest.raises(TrajectoryReplayError, match="contract is invalid"):
        recorder.record(
            run_id=result.run_id,
            user_id=result.user_id,
            runtime_thread_id=result.runtime_thread_id,
        )
    writer_engine.dispose()
    reader_engine.dispose()


def test_replayer_reports_persisted_result_drift() -> None:
    writer_factory, reader_factory, writer_engine, reader_engine = (
        make_shared_session_factories()
    )
    result = persist_sample_run(writer_factory)
    recorded = RuntimeTrajectoryRecorder(writer_factory).record(
        run_id=result.run_id,
        user_id=result.user_id,
        runtime_thread_id=result.runtime_thread_id,
    )
    session = writer_factory()
    try:
        run = session.get(AgentRun, result.run_id)
        run.result_json = {"decision": "changed"}
        session.commit()
    finally:
        session.close()

    replay = RuntimeTrajectoryReplayer(reader_factory).replay(recorded)

    assert replay.matches is False
    assert replay.differences == ("result_fingerprint",)
    assert replay.recorded_fingerprint != replay.observed_fingerprint
    writer_engine.dispose()
    reader_engine.dispose()
