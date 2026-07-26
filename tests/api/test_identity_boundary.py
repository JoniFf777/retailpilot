import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.settings import Settings
from app.db.base import Base
from app.db.models import GovernanceAuditRecord as GovernanceAuditRecordModel
from app.dependencies import agent as agent_dependency
from app.dependencies import security as security_dependency
from app.governance import (
    GovernanceAuditEmissionMonitor,
    GovernanceAuditEmitter,
)
from app.main import app
from app.runtime import LocalRuntimeCoordinationBackend
from app.security import (
    AuditRequestOperation,
    build_identity_boundary,
    signed_identity_signature,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _enable_trusted_header(monkeypatch) -> None:
    monkeypatch.setattr(
        security_dependency,
        "get_settings",
        lambda: SimpleNamespace(shopmind_identity_provider="trusted_header"),
    )


SIGNED_IDENTITY_SECRET = "signed-api-identity-secret-32-bytes-minimum"


def _enable_signed_header(monkeypatch, *, audit_enabled: bool = False) -> None:
    monkeypatch.setattr(
        security_dependency,
        "get_settings",
        lambda: Settings(
            shopmind_identity_provider="signed_header",
            shopmind_identity_signing_secret=SIGNED_IDENTITY_SECRET,
            shopmind_identity_signature_max_age_seconds=60,
            shopmind_identity_signature_clock_skew_seconds=5,
            shopmind_governance_audit_enabled=audit_enabled,
        ),
    )
    monkeypatch.setattr(
        security_dependency,
        "identity_replay_backend",
        LocalRuntimeCoordinationBackend(),
    )


def _signed_request_headers(
    *,
    subject: str = "signed-api-user",
    issued_at: int | None = None,
    nonce: str = "signed-api-nonce-0123456789",
) -> dict[str, str]:
    timestamp = int(time.time()) if issued_at is None else issued_at
    return {
        "X-ShopMind-Authenticated-User": subject,
        "X-ShopMind-Identity-Timestamp": str(timestamp),
        "X-ShopMind-Identity-Nonce": nonce,
        "X-ShopMind-Identity-Signature": signed_identity_signature(
            secret=SIGNED_IDENTITY_SECRET,
            subject_id=subject,
            issued_at=timestamp,
            nonce=nonce,
        ),
    }


def _audit_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_trusted_header_identity_supplies_effective_user(monkeypatch) -> None:
    _enable_trusted_header(monkeypatch)
    captured: list[str | None] = []

    def fake_call_shopmind_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        captured.append(user_id)
        return {"answer": "ok", "status": "completed", "tool_calls": []}

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", fake_call_shopmind_agent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            headers={"X-ShopMind-Authenticated-User": "proxy-user"},
            json={"message": "recommend a keyboard"},
        )

    assert response.status_code == 200
    assert response.json()["user_id"] == "proxy-user"
    assert captured == ["proxy-user"]


@pytest.mark.anyio
async def test_signed_header_identity_authenticates_once_and_rejects_replay(
    monkeypatch,
) -> None:
    _enable_signed_header(monkeypatch)
    captured: list[str | None] = []

    def fake_call_shopmind_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        captured.append(user_id)
        return {"answer": "ok", "status": "completed", "tool_calls": []}

    monkeypatch.setattr(
        agent_dependency,
        "call_shopmind_agent",
        fake_call_shopmind_agent,
    )
    headers = _signed_request_headers()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post(
            "/api/chat",
            headers=headers,
            json={"message": "recommend a keyboard"},
        )
        replayed = await client.post(
            "/api/chat",
            headers=headers,
            json={"message": "recommend a keyboard"},
        )

    assert accepted.status_code == 200
    assert accepted.json()["user_id"] == "signed-api-user"
    assert captured == ["signed-api-user"]
    assert replayed.status_code == 401
    assert replayed.json() == {"detail": "Authentication required."}
    assert replayed.headers["www-authenticate"] == "ShopMindSignedHeader"
    for private_value in (
        SIGNED_IDENTITY_SECRET,
        headers["X-ShopMind-Identity-Nonce"],
        headers["X-ShopMind-Identity-Signature"],
    ):
        assert private_value not in accepted.text
        assert private_value not in replayed.text


@pytest.mark.anyio
async def test_signed_header_rejects_owner_mismatch_before_agent_execution(
    monkeypatch,
) -> None:
    _enable_signed_header(monkeypatch)

    def must_not_run(*args, **kwargs):
        raise AssertionError("Agent execution must not start before authorization.")

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", must_not_run)
    headers = _signed_request_headers(nonce="owner-mismatch-nonce-012345")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            headers=headers,
            json={
                "message": "recommend a keyboard",
                "user_id": "different-owner",
            },
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authenticated principal is not authorized for this user."
    }
    assert "signed-api-user" not in response.text
    assert headers["X-ShopMind-Identity-Signature"] not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "headers",
    (
        {},
        {
            "X-ShopMind-Authenticated-User": "signed-api-user",
            "X-ShopMind-Identity-Timestamp": "invalid",
        },
        {
            **_signed_request_headers(
                issued_at=int(time.time()) - 61,
                nonce="expired-signed-nonce-012345",
            ),
        },
        {
            "X-ShopMind-Authenticated-User": "signed-api-user",
            "X-ShopMind-Identity-Timestamp": str(int(time.time())),
            "X-ShopMind-Identity-Nonce": "n" * 129,
            "X-ShopMind-Identity-Signature": "0" * 65,
        },
    ),
)
async def test_signed_header_mode_fails_closed_with_stable_public_401(
    monkeypatch,
    headers: dict[str, str],
) -> None:
    _enable_signed_header(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            headers=headers,
            json={"message": "recommend a keyboard"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}
    assert response.headers["www-authenticate"] == "ShopMindSignedHeader"


@pytest.mark.anyio
async def test_chat_route_emits_authentication_audit_when_enabled(
    monkeypatch,
) -> None:
    Session = _audit_session_factory()
    monkeypatch.setattr(
        security_dependency,
        "get_settings",
        lambda: SimpleNamespace(
            shopmind_identity_provider="development_payload",
            shopmind_governance_audit_enabled=True,
        ),
    )
    monkeypatch.setattr(
        security_dependency,
        "governance_audit_emitter",
        GovernanceAuditEmitter(Session),
    )
    monkeypatch.setattr(
        agent_dependency,
        "call_shopmind_agent",
        lambda message, user_id=None, thread_id=None: {
            "answer": "ok",
            "status": "completed",
            "tool_calls": [],
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "recommend a keyboard",
                "user_id": "private-route-owner",
            },
        )
    session = Session()
    try:
        row = session.query(GovernanceAuditRecordModel).one()
    finally:
        session.close()

    assert response.status_code == 200
    assert row.operation == "authentication.bind"
    assert row.metadata_json == {
        "provider": "development_payload",
        "request_operation": "chat",
    }
    assert "private-route-owner" not in str(row.metadata_json)


@pytest.mark.anyio
async def test_signed_identity_audit_is_fingerprint_only(monkeypatch) -> None:
    Session = _audit_session_factory()
    _enable_signed_header(monkeypatch, audit_enabled=True)
    monkeypatch.setattr(
        security_dependency,
        "governance_audit_emitter",
        GovernanceAuditEmitter(Session),
    )
    monkeypatch.setattr(
        agent_dependency,
        "call_shopmind_agent",
        lambda message, user_id=None, thread_id=None: {
            "answer": "ok",
            "status": "completed",
            "tool_calls": [],
        },
    )
    headers = _signed_request_headers(nonce="signed-audit-nonce-01234567")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            headers=headers,
            json={"message": "recommend a keyboard"},
        )
    session = Session()
    try:
        row = session.query(GovernanceAuditRecordModel).one()
    finally:
        session.close()

    assert response.status_code == 200
    assert row.actor_fingerprint is not None
    assert row.metadata_json == {
        "provider": "signed_header",
        "request_operation": "chat",
    }
    serialized = f"{row.metadata_json!r} {row.actor_fingerprint}"
    for private_value in (
        "signed-api-user",
        SIGNED_IDENTITY_SECRET,
        headers["X-ShopMind-Identity-Nonce"],
        headers["X-ShopMind-Identity-Signature"],
    ):
        assert private_value not in serialized


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "payload"),
    (
        (
            "/api/chat",
            {
                "message": "recommend a keyboard",
                "user_id": "payload-user",
                "roles": ["admin"],
            },
        ),
        (
            "/api/chat/confirm",
            {
                "pending_action_id": "pending-identity-test",
                "confirmed": True,
                "user_id": "payload-user",
                "scopes": ["actions:write"],
            },
        ),
        (
            "/api/chat/stream",
            {
                "message": "recommend a keyboard",
                "user_id": "payload-user",
                "roles": ["admin"],
            },
        ),
    ),
)
async def test_trusted_header_rejects_payload_owner_impersonation(
    monkeypatch,
    path: str,
    payload: dict,
) -> None:
    _enable_trusted_header(monkeypatch)

    def must_not_run(*args, **kwargs):
        raise AssertionError("Agent execution must not start before authorization.")

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", must_not_run)
    monkeypatch.setattr(agent_dependency, "confirm_pending_action", must_not_run)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            path,
            headers={"X-ShopMind-Authenticated-User": "proxy-user"},
            json=payload,
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authenticated principal is not authorized for this user."
    }
    assert "payload-user" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "payload"),
    (
        ("/api/chat", {"message": "recommend a keyboard"}),
        (
            "/api/chat/confirm",
            {
                "pending_action_id": "pending-identity-test",
                "confirmed": True,
                "user_id": "payload-user",
            },
        ),
        ("/api/chat/stream", {"message": "recommend a keyboard"}),
    ),
)
async def test_trusted_header_mode_requires_authentication(
    monkeypatch,
    path: str,
    payload: dict,
) -> None:
    _enable_trusted_header(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(path, json=payload)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}
    assert response.headers["www-authenticate"] == "ShopMindTrustedHeader"


def test_openapi_exposes_fixed_identity_header_without_role_payloads() -> None:
    schema = app.openapi()

    for path in ("/api/chat", "/api/chat/confirm", "/api/chat/stream"):
        operation = schema["paths"][path]["post"]
        headers = {
            parameter["name"]
            for parameter in operation["parameters"]
            if parameter["in"] == "header"
        }
        assert headers.issuperset(
            {
                "X-ShopMind-Authenticated-User",
                "X-ShopMind-Identity-Timestamp",
                "X-ShopMind-Identity-Nonce",
                "X-ShopMind-Identity-Signature",
            }
        )
    serialized = str(schema)
    assert '"roles"' not in serialized
    assert '"scopes"' not in serialized


def test_identity_binding_emits_allowed_audit_when_server_switch_is_enabled():
    Session = _audit_session_factory()
    emitter = GovernanceAuditEmitter(Session)
    boundary = build_identity_boundary(Settings())

    binding = security_dependency.bind_request_user(
        boundary,
        "private-identity-owner",
        require_user=False,
        request_operation=AuditRequestOperation.CHAT,
        audit_enabled=True,
        audit_emitter=emitter,
    )
    session = Session()
    try:
        row = session.query(GovernanceAuditRecordModel).one()
    finally:
        session.close()

    assert binding.effective_user_id == "private-identity-owner"
    assert row.category == "authentication"
    assert row.decision == "allowed"
    assert row.reason == "authenticated"
    assert row.actor_kind == "principal"
    assert row.owner_fingerprint != "private-identity-owner"
    assert "private-identity-owner" not in str(row.metadata_json)


def test_identity_denial_audit_is_principal_scoped_and_keeps_http_403():
    Session = _audit_session_factory()
    emitter = GovernanceAuditEmitter(Session)
    boundary = build_identity_boundary(
        Settings(shopmind_identity_provider="trusted_header"),
        trusted_subject="private-trusted-owner",
    )

    with pytest.raises(HTTPException) as raised:
        security_dependency.bind_request_user(
            boundary,
            "private-other-owner",
            require_user=True,
            request_operation=AuditRequestOperation.CONFIRM_PENDING_ACTION,
            audit_enabled=True,
            audit_emitter=emitter,
        )
    session = Session()
    try:
        row = session.query(GovernanceAuditRecordModel).one()
    finally:
        session.close()

    assert raised.value.status_code == 403
    assert row.decision == "denied"
    assert row.reason == "owner_mismatch"
    assert row.actor_kind == "principal"
    assert row.actor_fingerprint is not None
    assert "private-trusted-owner" not in str(row.metadata_json)
    assert "private-other-owner" not in str(row.metadata_json)


def test_identity_audit_storage_failure_does_not_change_http_401():
    def unavailable_session():
        raise RuntimeError("private audit database failure")

    boundary = build_identity_boundary(
        Settings(shopmind_identity_provider="trusted_header")
    )
    monitor = GovernanceAuditEmissionMonitor(alert_failure_threshold=1)
    with pytest.raises(HTTPException) as raised:
        security_dependency.bind_request_user(
            boundary,
            None,
            require_user=True,
            request_operation=AuditRequestOperation.CHAT,
            audit_enabled=True,
            audit_emitter=GovernanceAuditEmitter(
                unavailable_session,
                monitor=monitor,
            ),
        )

    assert raised.value.status_code == 401
    assert monitor.snapshot().failed_calls_total == 1
    assert monitor.snapshot().alert_active is True
