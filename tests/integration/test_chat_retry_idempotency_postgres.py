"""Isolated PostgreSQL proof for concurrent Chat idempotency claims."""

from __future__ import annotations

import os
import threading
import time
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings
from app.db.models import (
    AgentRun,
    AgentRunEvent,
    ConversationMessage,
    ConversationSummary,
    ConversationThread,
    IdempotencyRecord,
)
from app.repositories.runtime_runs import get_agent_run
from app.runtime import RunOperation, RunRequest, ShopMindRuntimeHarness


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for Chat retry PostgreSQL checks",
)


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def _bootstrap_schema(engine, schema: str) -> None:
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".alembic_version (
                    version_num VARCHAR(32) NOT NULL PRIMARY KEY
                )'''
            )
        )
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".pending_actions (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    thread_id VARCHAR,
                    action_type VARCHAR(64) NOT NULL,
                    payload_json JSONB NOT NULL,
                    risk_class VARCHAR NOT NULL DEFAULT 'high',
                    preview_text TEXT NOT NULL DEFAULT '',
                    status VARCHAR(32) NOT NULL,
                    expires_at TIMESTAMPTZ,
                    metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )'''
            )
        )
        connection.commit()


@pytest.fixture(scope="function")
def pg_factory():
    engine_url = get_settings().test_database_url
    schema = f"shopmind_chat_retry_{uuid4().hex}"
    bootstrap = create_engine(engine_url, pool_pre_ping=True)
    _bootstrap_schema(bootstrap, schema)
    bootstrap.dispose()
    engine = create_engine(engine_url, pool_pre_ping=True)

    @event.listens_for(engine, "checkout")
    def _set_private_search_path(dbapi_connection, _connection_record, _proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    with engine.connect() as connection:
        command.stamp(_alembic(connection), "0007_governance_audit")
        command.upgrade(_alembic(connection), "0015_shopmind_order_expiration")
        connection.execute(text(f'SET search_path TO "{schema}", public'))
        for table in (
            ConversationThread.__table__,
            ConversationMessage.__table__,
            AgentRun.__table__,
            AgentRunEvent.__table__,
            ConversationSummary.__table__,
            IdempotencyRecord.__table__,
        ):
            table.create(connection, checkfirst=False)
        connection.commit()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory, engine, schema
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def test_concurrent_same_key_has_one_winner_run_and_thread(pg_factory) -> None:
    factory, engine, schema = pg_factory
    harness = ShopMindRuntimeHarness(session_factory=factory)
    barrier = threading.Barrier(2)
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    executor_runs: list[str] = []
    results = []
    errors = []

    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="pg-retry-user",
        thread_id="pg-retry-thread",
        input_text="same request",
        idempotency_key="pg-retry-key",
    )

    def executor(context):
        with lock:
            executor_runs.append(context.run_id)
        entered.set()
        assert release.wait(timeout=15)
        return {"answer": "authoritative", "status": "completed", "tool_calls": []}

    def worker():
        try:
            barrier.wait(timeout=15)
            result = harness.run(request, executor)
            with lock:
                results.append(result)
        except Exception as exc:  # pragma: no cover - assertion below reports it
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    if not entered.wait(timeout=15):
        release.set()
        for thread in threads:
            thread.join(timeout=15)
        assert not errors, errors
        pytest.fail(f"no worker reached the executor; results={results!r}")
    time.sleep(0.5)
    release.set()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert not errors
    assert len(executor_runs) == 1
    assert len(results) == 2
    winner_run_id = executor_runs[0]
    assert {result.run_id for result in results} == {winner_run_id}
    assert any(result.metadata.get("retry_state") == "in_progress" for result in results)
    assert any(result.answer == "authoritative" for result in results)

    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        session = Session(bind=connection)
        try:
            assert session.query(AgentRun).count() == 1
            assert session.query(IdempotencyRecord).count() == 1
            assert session.query(ConversationThread).count() == 1
            record = session.query(IdempotencyRecord).one()
            assert record.run_id == winner_run_id
            assert record.status == "completed"
            assert get_agent_run(session, run_id=winner_run_id)["status"] == "completed"
            assert inspect(connection).has_table("idempotency_records", schema=schema)
        finally:
            session.close()


def test_postgres_terminal_replay_and_hash_conflict(pg_factory) -> None:
    factory, _engine, _schema = pg_factory
    harness = ShopMindRuntimeHarness(session_factory=factory)
    calls = 0

    def executor(_context):
        nonlocal calls
        calls += 1
        return {"answer": "authoritative", "status": "completed", "tool_calls": []}

    base = dict(
        operation=RunOperation.CHAT,
        user_id="pg-replay-user",
        thread_id="pg-replay-thread",
        idempotency_key="pg-replay-key",
    )
    first = harness.run(RunRequest(input_text="same", **base), executor)
    replay = harness.run(RunRequest(input_text="same", **base), executor)
    conflict = harness.run(RunRequest(input_text="different", **base), executor)

    assert calls == 1
    assert replay.run_id == first.run_id
    assert replay.metadata["idempotency_replayed"] is True
    assert conflict.error is not None
    assert conflict.error.code == "runtime.idempotency_key_conflict"
    assert conflict.run_id == first.run_id
