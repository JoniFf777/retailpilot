"""FastAPI bridge for the server-owned request identity boundary."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.governance import GovernanceAuditEmitter
from app.runtime.coordination_factory import build_runtime_coordination_backend
from app.security import (
    AuditDecision,
    AuditReason,
    AuditRequestOperation,
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    GovernanceAuditFactory,
    IdentityBinding,
    IdentityBoundary,
    build_identity_boundary,
)


TRUSTED_SUBJECT_HEADER = "X-ShopMind-Authenticated-User"
SIGNED_IDENTITY_TIMESTAMP_HEADER = "X-ShopMind-Identity-Timestamp"
SIGNED_IDENTITY_NONCE_HEADER = "X-ShopMind-Identity-Nonce"
SIGNED_IDENTITY_SIGNATURE_HEADER = "X-ShopMind-Identity-Signature"
governance_audit_emitter = GovernanceAuditEmitter(SessionLocal)
identity_replay_backend = build_runtime_coordination_backend()


def get_identity_boundary(
    trusted_subject: Annotated[
        str | None,
        Header(
            alias=TRUSTED_SUBJECT_HEADER,
            include_in_schema=True,
        ),
    ] = None,
    signed_issued_at: Annotated[
        str | None,
        Header(
            alias=SIGNED_IDENTITY_TIMESTAMP_HEADER,
            include_in_schema=True,
        ),
    ] = None,
    signed_nonce: Annotated[
        str | None,
        Header(
            alias=SIGNED_IDENTITY_NONCE_HEADER,
            include_in_schema=True,
        ),
    ] = None,
    signed_signature: Annotated[
        str | None,
        Header(
            alias=SIGNED_IDENTITY_SIGNATURE_HEADER,
            include_in_schema=True,
        ),
    ] = None,
) -> IdentityBoundary:
    """Resolve identity using server mode; the request cannot select a provider."""

    return build_identity_boundary(
        get_settings(),
        trusted_subject=trusted_subject,
        signed_issued_at=signed_issued_at,
        signed_nonce=signed_nonce,
        signed_signature=signed_signature,
        replay_backend=identity_replay_backend,
    )


def bind_request_user(
    boundary: IdentityBoundary,
    requested_user_id: str | None,
    *,
    require_user: bool,
    request_operation: AuditRequestOperation | None = None,
    audit_enabled: bool | None = None,
    audit_emitter: GovernanceAuditEmitter | None = None,
) -> IdentityBinding:
    """Translate closed identity failures into stable HTTP authentication errors."""

    enabled = (
        bool(
            getattr(
                get_settings(),
                "shopmind_governance_audit_enabled",
                False,
            )
        )
        if audit_enabled is None
        else audit_enabled
    )
    emitter = audit_emitter or governance_audit_emitter
    try:
        binding = boundary.bind_user(requested_user_id, require_user=require_user)
    except AuthenticationRequiredError as exc:
        _emit_authentication_decision(
            emitter,
            enabled=enabled,
            boundary=boundary,
            request_operation=request_operation,
            requested_user_id=requested_user_id,
            decision=AuditDecision.DENIED,
            reason=AuditReason.AUTHENTICATION_REQUIRED,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": boundary.authentication_scheme},
        ) from exc
    except AuthorizationDeniedError as exc:
        _emit_authentication_decision(
            emitter,
            enabled=enabled,
            boundary=boundary,
            request_operation=request_operation,
            requested_user_id=requested_user_id,
            decision=AuditDecision.DENIED,
            reason=AuditReason.OWNER_MISMATCH,
            principal=boundary.authenticated_principal,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated principal is not authorized for this user.",
        ) from exc
    _emit_authentication_decision(
        emitter,
        enabled=enabled,
        boundary=boundary,
        request_operation=request_operation,
        requested_user_id=requested_user_id,
        decision=AuditDecision.ALLOWED,
        reason=(
            AuditReason.AUTHENTICATED
            if binding.principal is not None
            else AuditReason.ANONYMOUS_COMPATIBILITY
        ),
        principal=binding.principal,
    )
    return binding


def _emit_authentication_decision(
    emitter: GovernanceAuditEmitter,
    *,
    enabled: bool,
    boundary: IdentityBoundary,
    request_operation: AuditRequestOperation | None,
    requested_user_id: str | None,
    decision: AuditDecision,
    reason: AuditReason,
    principal=None,
) -> None:
    """Never let audit conversion/storage alter the identity decision."""

    if not enabled or request_operation is None:
        return
    try:
        record = GovernanceAuditFactory().authentication_decision(
            provider=boundary.provider_name,
            request_operation=request_operation,
            decision=decision,
            reason=reason,
            principal=principal,
            requested_user_id=requested_user_id,
        )
        emitter.emit(record)
    except Exception:
        pass


__all__ = [
    "SIGNED_IDENTITY_NONCE_HEADER",
    "SIGNED_IDENTITY_SIGNATURE_HEADER",
    "SIGNED_IDENTITY_TIMESTAMP_HEADER",
    "TRUSTED_SUBJECT_HEADER",
    "bind_request_user",
    "get_identity_boundary",
]
