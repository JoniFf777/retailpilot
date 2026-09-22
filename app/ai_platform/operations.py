"""Payload-free projections for the shopping AI operations console."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.core.logging import log_event


def project_trace_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only bounded, non-content trace metadata."""

    return {
        "sequence": int(event.get("sequence", 0)),
        "event_type": str(event.get("event_type", "unknown"))[:128],
        "agent_name": (
            str(event.get("agent_name"))[:64] if event.get("agent_name") else None
        ),
        "visibility": str(event.get("visibility", "internal"))[:32],
        "status": (
            str((event.get("payload") or {}).get("status", "unknown"))[:32]
            if isinstance(event.get("payload"), Mapping)
            else "unknown"
        ),
    }


def project_trace(
    events: Iterable[Mapping[str, Any]], *, limit: int = 100
) -> list[dict[str, Any]]:
    if limit <= 0 or limit > 100:
        raise ValueError("Trace projection limit must be between 1 and 100.")
    return [project_trace_event(event) for event in list(events)[:limit]]


def record_admin_operation(
    *,
    operation: str,
    resource_type: str,
    resource_key: str,
    version: int,
    audit_enabled: bool = False,
    session_factory=None,
) -> None:
    """Emit only a fingerprinted operational fact; failures never affect the write."""

    import hashlib

    log_event(
        f"admin.ai.{operation}",
        operation=operation,
        resource_type=resource_type,
        resource_fingerprint=hashlib.sha256(resource_key.encode("utf-8")).hexdigest(),
        version=version,
        status="committed",
    )
    if not audit_enabled or session_factory is None:
        return
    from app.governance.emitter import GovernanceAuditEmitter
    from app.security.audit import (
        AuditDecision,
        AuditOperation,
        AuditReason,
        GovernanceAuditFactory,
    )

    audit_operation = (
        AuditOperation.ADMIN_EXTENSION_PUBLISH
        if operation == "extension_published"
        else AuditOperation.ADMIN_EVIDENCE_REVOKE
    )
    audit_id = f"{resource_type}:{resource_key}:{version}:{operation}"
    record = GovernanceAuditFactory().action_decision(
        operation=audit_operation,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.COMPLETED,
        action_type=f"admin_{resource_type}",
        action_id=audit_id,
        principal=None,
        owner_id="admin",
    )
    # Audit is best effort by design; it cannot roll back a committed admin
    # operation or expose storage details to the HTTP caller.
    GovernanceAuditEmitter(session_factory).emit(record)


__all__ = ["project_trace", "project_trace_event", "record_admin_operation"]
