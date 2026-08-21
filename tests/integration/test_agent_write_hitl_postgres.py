"""PostgreSQL concurrency proof for canonical preference HITL confirmation."""

from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings
from app.db.models import PendingAction, UserPreference
from app.services.pending_actions import (
    confirm_save_preference,
    prepare_save_preference_pending_action,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for preference HITL PostgreSQL checks",
)


def _config(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="function")
def pg_factory():
    engine_url = get_settings().test_database_url
    schema = f"shopmind_agent_hitl_{uuid4().hex}"
    bootstrap = create_engine(engine_url, pool_pre_ping=True)
    with bootstrap.connect() as connection:
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
    bootstrap.dispose()
    engine = create_engine(engine_url, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    @event.listens_for(engine, "checkout")
    def _restore_search_path(dbapi_connection, _record, _proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    with engine.begin() as connection:
        command.stamp(_config(connection), "0007_governance_audit")
        command.upgrade(_config(connection), "0011_shopmind_cart")
        UserPreference.__table__.create(connection, checkfirst=True)
        PendingAction.__table__.create(connection, checkfirst=True)

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def test_concurrent_preference_confirmation_is_exactly_once(pg_factory) -> None:
    seed: Session = pg_factory()
    action = prepare_save_preference_pending_action(
        seed,
        user_id="pg-hitl-user",
        thread_id="pg-hitl-thread",
        preference_type="avoid",
        preference_value="高噪声键盘",
    )
    seed.commit()
    seed.close()

    barrier = threading.Barrier(2)
    results: list[tuple[str, bool]] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker() -> None:
        session: Session = pg_factory()
        try:
            barrier.wait(timeout=15)
            result = confirm_save_preference(
                session,
                pending_action_id=action.pending_action_id,
                user_id="pg-hitl-user",
                thread_id="pg-hitl-thread",
                expected_version=1,
            )
            session.commit()
            with lock:
                results.append((result.pending_action.status, result.idempotent_replay))
        except Exception as exc:  # pragma: no cover - assertion below reports it
            session.rollback()
            with lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors
    assert len(results) == 2
    assert [status for status, _replay in results] == ["confirmed", "confirmed"]
    assert sorted(replay for _status, replay in results) == [False, True]

    check: Session = pg_factory()
    try:
        assert check.query(UserPreference).filter_by(user_id="pg-hitl-user").count() == 1
        stored = check.get(PendingAction, action.pending_action_id)
        assert stored is not None
        assert stored.status == "confirmed"
        assert stored.version == 2
    finally:
        check.close()
