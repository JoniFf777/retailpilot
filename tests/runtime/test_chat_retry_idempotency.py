"""Focused runtime idempotency claim and recovery tests."""

from threading import Event, Thread

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.api.chat_response import build_chat_response
from app.runtime import RunOperation, RunRequest, RunStatus, ShopMindRuntimeHarness
from app.runtime.harness import RuntimeIdempotencyPersistenceError
from app.repositories.runtime_runs import claim_idempotency_record


def make_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_same_key_running_duplicate_returns_winner_and_does_not_execute_twice():
    factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=factory)
    entered = Event()
    release = Event()
    calls = []
    first_result = []

    def executor(context):
        calls.append(context.run_id)
        entered.set()
        assert release.wait(timeout=5)
        return {"answer": "authoritative", "status": "completed", "tool_calls": []}

    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="retry-user",
        thread_id="retry-thread",
        input_text="same message",
        idempotency_key="retry-key",
    )

    thread = Thread(target=lambda: first_result.append(harness.run(request, executor)))
    thread.start()
    assert entered.wait(timeout=5)
    duplicate = harness.run(request, executor)
    assert duplicate.error is not None
    assert duplicate.error.code == "runtime.idempotency_in_progress"
    assert duplicate.metadata["retry_state"] == "in_progress"
    assert duplicate.metadata["authoritative_run_id"] == calls[0]
    assert duplicate.run_id == calls[0]
    projected = build_chat_response(
        duplicate,
        user_id="retry-user",
        thread_id="retry-thread",
        include_debug=False,
    )
    assert projected.retry_state == "in_progress"
    assert projected.runtime_error_code == "runtime.idempotency_in_progress"
    assert projected.authoritative_run_id == calls[0]
    assert len(calls) == 1
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert first_result[0].run_id == calls[0]


@pytest.mark.parametrize("terminal_status", [RunStatus.FAILED, RunStatus.CANCELLED])
def test_terminal_same_key_replays_without_reexecution(terminal_status):
    factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=factory)
    calls = 0

    def executor(context):
        nonlocal calls
        calls += 1
        return {"answer": terminal_status.value, "status": terminal_status.value, "tool_calls": []}

    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="terminal-user",
        thread_id="terminal-thread",
        input_text="terminal message",
        idempotency_key=f"terminal-{terminal_status.value}",
    )
    first = harness.run(request, executor)
    second = harness.run(request, executor)
    assert calls == 1
    assert second.run_id == first.run_id
    assert second.status == terminal_status
    assert second.metadata["idempotency_replayed"] is True
    assert second.metadata["retry_state"] == "terminal"


def test_same_key_hash_conflict_is_machine_readable():
    factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=factory)
    calls = 0

    def executor(context):
        nonlocal calls
        calls += 1
        return {"answer": "ok", "status": "completed", "tool_calls": []}

    base = dict(operation=RunOperation.CHAT, user_id="hash-user", thread_id="hash-thread", idempotency_key="hash-key")
    harness.run(RunRequest(input_text="one", **base), executor)
    conflict = harness.run(RunRequest(input_text="two", **base), executor)
    assert calls == 1
    assert conflict.error is not None
    assert conflict.error.code == "runtime.idempotency_key_conflict"
    assert conflict.metadata["retry_state"] == "terminal"


def test_confirmation_required_replay_preserves_pending_action_identity():
    factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=factory)
    calls = 0

    def executor(context):
        nonlocal calls
        calls += 1
        return {
            "answer": "请确认加入购物车。",
            "status": "confirmation_required",
            "tool_calls": ["prepare_add_to_cart"],
            "pending_action_id": "pending-retry-1",
            "pending_action": {
                "pending_action_id": "pending-retry-1",
                "version": 3,
                "preview": "加入 SKU-1",
            },
        }

    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="pending-retry-user",
        thread_id="pending-retry-thread",
        input_text="add SKU-1",
        idempotency_key="pending-retry-key",
    )
    first = harness.run(request, executor)
    replay = harness.run(request, executor)

    assert calls == 1
    assert first.status == RunStatus.CONFIRMATION_REQUIRED
    assert replay.status == RunStatus.CONFIRMATION_REQUIRED
    assert replay.run_id == first.run_id
    assert replay.pending_action_id == "pending-retry-1"
    assert replay.output_data["pending_action"]["version"] == 3
    assert replay.metadata["idempotency_replayed"] is True


def test_claim_persistence_failure_fails_closed_before_executor(monkeypatch):
    factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=factory)
    calls = 0

    def fail_claim(*args, **kwargs):
        raise RuntimeIdempotencyPersistenceError("claim unavailable")

    monkeypatch.setattr("app.runtime.harness.claim_idempotency_record", fail_claim)

    def executor(context):
        nonlocal calls
        calls += 1
        return {"answer": "must not run", "status": "completed", "tool_calls": []}

    result = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="persist-user",
            thread_id="persist-thread",
            input_text="persist failure",
            idempotency_key="persist-key",
        ),
        executor,
    )
    assert calls == 0
    assert result.error is not None
    assert result.error.code == "runtime.idempotency_persistence_failed"
    assert result.metadata["retry_state"] == "in_progress"


def test_finish_persistence_failure_keeps_authoritative_run_recoverable(monkeypatch):
    factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=factory)
    calls = 0

    def fail_finish(*_args, **_kwargs):
        raise RuntimeIdempotencyPersistenceError("finish unavailable")

    monkeypatch.setattr(harness, "_persist_finish", fail_finish)

    def executor(_context):
        nonlocal calls
        calls += 1
        return {"answer": "authoritative", "status": "completed", "tool_calls": []}

    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="finish-persist-user",
        thread_id="finish-persist-thread",
        input_text="finish persistence",
        idempotency_key="finish-persist-key",
    )
    failed_persist = harness.run(request, executor)
    recovery = harness.run(request, executor)

    assert calls == 1
    assert failed_persist.error is not None
    assert failed_persist.error.code == "runtime.idempotency_persistence_failed"
    assert failed_persist.metadata["retry_state"] == "in_progress"
    assert recovery.error is not None
    assert recovery.error.code == "runtime.idempotency_in_progress"
    assert recovery.metadata["authoritative_run_id"] == failed_persist.run_id


def test_claim_record_savepoint_returns_existing_winner():
    factory = make_session_factory()
    session = factory()
    first = claim_idempotency_record(
        session,
        user_id="claim-user",
        operation="chat",
        idempotency_key="claim-key",
        request_hash="hash",
        run_id="winner-run",
    )
    session.commit()
    second = claim_idempotency_record(
        session,
        user_id="claim-user",
        operation="chat",
        idempotency_key="claim-key",
        request_hash="hash",
        run_id="loser-run",
    )
    assert first.claimed is True
    assert second.claimed is False
    # The claim is persisted before AgentRun exists; the harness binds the
    # authoritative run id in the same outer transaction.
    assert second.record["run_id"] is None
    session.close()
