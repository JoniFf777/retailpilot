from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import owner_data as owner_data_route
from app.db.base import Base
from app.db.models import MemoryRecord, UserPreference
from app.dependencies import security as security_dependency
from app.governance import GovernanceAuditEmitter, OwnerDataService
from app.main import app
from app.repositories.runtime_memory import create_memory_record
from app.repositories.runtime_conversations import (
    get_or_create_conversation_thread,
)
from app.repositories.runtime_runs import (
    append_agent_run_event,
    create_agent_run,
    finalize_agent_run,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _configure_owner_data_api(
    monkeypatch,
    *,
    Session,
    identity_provider: str = "development_payload",
    audit_enabled: bool = True,
) -> None:
    settings = SimpleNamespace(
        shopmind_identity_provider=identity_provider,
        shopmind_governance_audit_enabled=audit_enabled,
    )
    emitter = GovernanceAuditEmitter(Session)
    monkeypatch.setattr(security_dependency, "get_settings", lambda: settings)
    monkeypatch.setattr(
        security_dependency,
        "governance_audit_emitter",
        emitter,
    )
    monkeypatch.setattr(owner_data_route, "get_settings", lambda: settings)
    app.dependency_overrides[owner_data_route.get_owner_data_service] = (
        lambda: OwnerDataService(Session, audit_emitter=emitter)
    )


def _seed_memory(Session, *, owner_id: str, memory_id: str, content: str):
    session = Session()
    try:
        create_memory_record(
            session,
            memory_id=memory_id,
            memory_kind="long_term",
            scope="user",
            user_id=owner_id,
            content_text=content,
            content_json={"stale": True},
        )
        session.commit()
    finally:
        session.close()


def _seed_run(Session, *, owner_id: str) -> tuple[str, str]:
    session = Session()
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    run_id = "api-owner-run"
    trace_id = "api-owner-trace"
    try:
        thread = get_or_create_conversation_thread(
            session,
            user_id=owner_id,
            client_thread_id="api-owner-thread",
            now=now,
        )
        create_agent_run(
            session,
            run_id=run_id,
            thread_id=thread["thread_id"],
            user_id=owner_id,
            operation="chat",
            mode="multi",
            status="started",
            request_id="api-private-request",
            trace_id=trace_id,
            started_at=now,
            input_text="api private input",
            request_json={"message": "api private input"},
        )
        append_agent_run_event(
            session,
            run_id=run_id,
            thread_id=thread["thread_id"],
            user_id=owner_id,
            event_type="run.started",
            visibility="client",
            trace_id=trace_id,
            payload_json={"private": "client event payload"},
        )
        append_agent_run_event(
            session,
            run_id=run_id,
            thread_id=thread["thread_id"],
            user_id=owner_id,
            event_type="context.built",
            visibility="internal",
            trace_id=trace_id,
            payload_json={"private": "internal event payload"},
        )
        finalize_agent_run(
            session,
            run_id=run_id,
            status="completed",
            completed_at=now,
            output_text="api private output",
            result_json={"answer": "api private output"},
            usage_json={"step_count": 2, "tool_call_count": 1},
            debug_json={"private": "api debug"},
        )
        session.commit()
    finally:
        session.close()
    return run_id, trace_id


@pytest.mark.anyio
async def test_owner_memory_api_inspects_corrects_and_hard_deletes(
    monkeypatch,
) -> None:
    Session = _session_factory()
    owner_id = "api-private-owner"
    memory_id = "api-owner-memory"
    _seed_memory(
        Session,
        owner_id=owner_id,
        memory_id=memory_id,
        content="private old memory",
    )
    _configure_owner_data_api(monkeypatch, Session=Session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            inspected = await client.post(
                "/api/owner-data/inspect",
                json={"user_id": owner_id, "memory_limit": 10},
            )
            corrected = await client.post(
                "/api/owner-data/memory/correct",
                json={
                    "user_id": owner_id,
                    "memory_id": memory_id,
                    "content": "explicit corrected memory",
                },
            )
            deleted = await client.post(
                "/api/owner-data/memory/delete",
                json={"user_id": owner_id, "memory_id": memory_id},
            )
            missing = await client.post(
                "/api/owner-data/memory/delete",
                json={"user_id": owner_id, "memory_id": memory_id},
            )
    finally:
        app.dependency_overrides.clear()

    assert inspected.status_code == 200
    assert inspected.json()["memories"][0]["content"] == "private old memory"
    assert corrected.status_code == 200
    assert corrected.json()["memory"]["content"] == "explicit corrected memory"
    assert corrected.json()["memory"]["content_json"] == {}
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted", "memory_id": memory_id}
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Owner memory record not found."}

    session = Session()
    try:
        assert session.get(MemoryRecord, memory_id) is None
    finally:
        session.close()


@pytest.mark.anyio
async def test_owner_run_api_inspects_by_run_or_trace_without_payloads(
    monkeypatch,
) -> None:
    Session = _session_factory()
    owner_id = "api-run-owner"
    run_id, trace_id = _seed_run(Session, owner_id=owner_id)
    _configure_owner_data_api(monkeypatch, Session=Session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            by_run = await client.post(
                "/api/owner-data/runs/inspect",
                json={
                    "user_id": owner_id,
                    "run_id": run_id,
                    "event_limit": 10,
                },
            )
            by_trace = await client.post(
                "/api/owner-data/runs/inspect",
                json={
                    "user_id": owner_id,
                    "trace_id": trace_id,
                    "event_limit": 10,
                },
            )
            missing = await client.post(
                "/api/owner-data/runs/inspect",
                json={"user_id": "different-owner", "run_id": run_id},
            )
            invalid = await client.post(
                "/api/owner-data/runs/inspect",
                json={
                    "user_id": owner_id,
                    "run_id": run_id,
                    "trace_id": trace_id,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert by_run.status_code == by_trace.status_code == 200
    payload = by_run.json()
    assert payload["schema_version"] == "shopmind.owner-run-inspection.v1"
    assert payload["run_id"] == run_id
    assert payload["trace_id"] == trace_id
    assert payload["client_event_count"] == 1
    assert [event["event_type"] for event in payload["events"]] == [
        "run.started"
    ]
    assert payload == by_trace.json()
    serialized = by_run.text
    for forbidden in (
        "api private input",
        "api private output",
        "client event payload",
        "internal event payload",
        "api-private-request",
        "payload_json",
        "debug_json",
    ):
        assert forbidden not in serialized
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Owner run not found."}
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_full_owner_data_api_requires_explicit_confirmation_and_is_bounded(
    monkeypatch,
) -> None:
    Session = _session_factory()
    owner_id = "api-delete-owner"
    other_owner = "api-delete-other"
    _seed_memory(
        Session,
        owner_id=owner_id,
        memory_id="api-delete-memory",
        content="private delete content",
    )
    session = Session()
    try:
        session.add_all(
            [
                UserPreference(
                    user_id=owner_id,
                    preference_type="style",
                    preference_value="private deleted preference",
                ),
                UserPreference(
                    user_id=other_owner,
                    preference_type="style",
                    preference_value="private retained preference",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()
    _configure_owner_data_api(monkeypatch, Session=Session)
    request_id = str(uuid4())

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            unconfirmed = await client.post(
                "/api/owner-data/delete",
                json={
                    "user_id": owner_id,
                    "deletion_request_id": request_id,
                    "confirmed": False,
                },
            )
            deleted = await client.post(
                "/api/owner-data/delete",
                json={
                    "user_id": owner_id,
                    "deletion_request_id": request_id,
                    "confirmed": True,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert unconfirmed.status_code == 422
    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload["status"] == "deleted"
    assert payload["records_affected"] == 2
    assert payload["counts"]["memory_records"] == 1
    assert payload["counts"]["preferences"] == 1

    session = Session()
    try:
        retained = list(
            session.scalars(
                select(UserPreference).where(
                    UserPreference.user_id == other_owner
                )
            )
        )
    finally:
        session.close()
    assert len(retained) == 1


@pytest.mark.anyio
async def test_owner_data_api_rejects_cross_owner_before_storage(
    monkeypatch,
) -> None:
    Session = _session_factory()
    _configure_owner_data_api(
        monkeypatch,
        Session=Session,
        identity_provider="trusted_header",
        audit_enabled=False,
    )

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/owner-data/inspect",
                headers={
                    "X-ShopMind-Authenticated-User": "trusted-private-owner"
                },
                json={"user_id": "different-private-owner"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authenticated principal is not authorized for this user."
    }
    assert "different-private-owner" not in response.text


@pytest.mark.anyio
async def test_owner_data_api_sanitizes_storage_failure(monkeypatch) -> None:
    Session = _session_factory()
    _configure_owner_data_api(monkeypatch, Session=Session)

    def unavailable_session():
        raise RuntimeError("private database URL")

    app.dependency_overrides[owner_data_route.get_owner_data_service] = (
        lambda: OwnerDataService(unavailable_session)
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/owner-data/inspect",
                json={"user_id": "private-storage-owner"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Owner data storage unavailable."}
    assert "database URL" not in response.text


def test_openapi_exposes_closed_owner_data_workflows() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    for path in (
        "/api/owner-data/inspect",
        "/api/owner-data/runs/inspect",
        "/api/owner-data/memory/correct",
        "/api/owner-data/memory/delete",
        "/api/owner-data/delete",
    ):
        operation = paths[path]["post"]
        headers = {
            parameter["name"]
            for parameter in operation["parameters"]
            if parameter["in"] == "header"
        }
        assert "X-ShopMind-Authenticated-User" in headers

    deletion_schema = schema["components"]["schemas"]["OwnerDataDeletionRequest"]
    assert deletion_schema["properties"]["confirmed"]["const"] is True
