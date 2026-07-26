"""Owner-scoped persistence and retention for PII-safe governance audits."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import GovernanceAuditRecord as GovernanceAuditRecordModel
from app.security.audit import (
    AuditCategory,
    AuditOperation,
    GovernanceAuditMetadata,
    GovernanceAuditRecord,
)


DEFAULT_GOVERNANCE_AUDIT_RETENTION_DAYS = 90
MAX_GOVERNANCE_AUDIT_INSPECTION_LIMIT = 200
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class GovernanceAuditConflictError(RuntimeError):
    """Raised when an append would reuse an existing immutable audit ID."""


@dataclass(frozen=True)
class PersistedGovernanceAuditRecord:
    record: GovernanceAuditRecord
    expires_at: datetime
    created_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_owner_fingerprint(owner_fingerprint: str) -> str:
    if not isinstance(owner_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(
        owner_fingerprint
    ):
        raise ValueError("Governance audit owner fingerprint is invalid.")
    return owner_fingerprint


def _to_persisted(
    row: GovernanceAuditRecordModel,
) -> PersistedGovernanceAuditRecord:
    record = GovernanceAuditRecord(
        schema_version=row.schema_version,
        audit_id=row.audit_id,
        occurred_at=_as_utc(row.occurred_at),
        category=row.category,
        operation=row.operation,
        decision=row.decision,
        reason=row.reason,
        actor_kind=row.actor_kind,
        actor_fingerprint=row.actor_fingerprint,
        owner_fingerprint=row.owner_fingerprint,
        thread_fingerprint=row.thread_fingerprint,
        run_fingerprint=row.run_fingerprint,
        resource_fingerprint=row.resource_fingerprint,
        metadata=GovernanceAuditMetadata.model_validate(
            dict(row.metadata_json or {})
        ),
    )
    return PersistedGovernanceAuditRecord(
        record=record,
        expires_at=_as_utc(row.expires_at),
        created_at=_as_utc(row.created_at),
    )


def append_governance_audit_record(
    session: Session,
    *,
    record: GovernanceAuditRecord,
    expires_at: datetime | None = None,
    retention_days: int = DEFAULT_GOVERNANCE_AUDIT_RETENTION_DAYS,
    now: datetime | None = None,
) -> PersistedGovernanceAuditRecord:
    """Append one immutable audit record and assign a bounded retention window."""

    if retention_days < 1:
        raise ValueError("Governance audit retention must be at least one day.")
    audit_id = str(record.audit_id)
    if session.get(GovernanceAuditRecordModel, audit_id) is not None:
        raise GovernanceAuditConflictError("Governance audit record already exists.")

    resolved_expires_at = expires_at or (
        record.occurred_at + timedelta(days=retention_days)
    )
    if (
        resolved_expires_at.tzinfo is None
        or resolved_expires_at.utcoffset() is None
        or resolved_expires_at <= record.occurred_at
    ):
        raise ValueError("Governance audit expiration is invalid.")
    created_at = now or _now()
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("Governance audit creation timestamp must be timezone-aware.")

    row = GovernanceAuditRecordModel(
        audit_id=audit_id,
        schema_version=record.schema_version,
        category=record.category,
        operation=record.operation,
        decision=record.decision,
        reason=record.reason,
        actor_kind=record.actor_kind,
        actor_fingerprint=record.actor_fingerprint,
        owner_fingerprint=record.owner_fingerprint,
        thread_fingerprint=record.thread_fingerprint,
        run_fingerprint=record.run_fingerprint,
        resource_fingerprint=record.resource_fingerprint,
        metadata_json=record.metadata.model_dump(exclude_none=True, mode="json"),
        occurred_at=record.occurred_at,
        expires_at=resolved_expires_at,
        created_at=created_at,
    )
    session.add(row)
    session.flush()
    return _to_persisted(row)


def get_owner_governance_audit_record(
    session: Session,
    *,
    audit_id: str,
    owner_fingerprint: str,
    now: datetime | None = None,
) -> PersistedGovernanceAuditRecord | None:
    """Load one unexpired audit record only through its exact owner fingerprint."""

    validated_owner = _validate_owner_fingerprint(owner_fingerprint)
    current_time = now or _now()
    statement = select(GovernanceAuditRecordModel).where(
        GovernanceAuditRecordModel.audit_id == audit_id,
        GovernanceAuditRecordModel.owner_fingerprint == validated_owner,
        GovernanceAuditRecordModel.expires_at > current_time,
    )
    row = session.scalar(statement)
    return _to_persisted(row) if row is not None else None


def list_owner_governance_audit_records(
    session: Session,
    *,
    owner_fingerprint: str,
    category: AuditCategory | None = None,
    operation: AuditOperation | None = None,
    since: datetime | None = None,
    before: datetime | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> list[PersistedGovernanceAuditRecord]:
    """Inspect a bounded, newest-first owner view without accepting raw IDs."""

    validated_owner = _validate_owner_fingerprint(owner_fingerprint)
    if not 1 <= limit <= MAX_GOVERNANCE_AUDIT_INSPECTION_LIMIT:
        raise ValueError("Governance audit inspection limit is invalid.")
    if since is not None and before is not None and since >= before:
        raise ValueError("Governance audit inspection time range is invalid.")

    current_time = now or _now()
    conditions = [
        GovernanceAuditRecordModel.owner_fingerprint == validated_owner,
        GovernanceAuditRecordModel.expires_at > current_time,
    ]
    if category is not None:
        conditions.append(
            GovernanceAuditRecordModel.category == AuditCategory(category).value
        )
    if operation is not None:
        conditions.append(
            GovernanceAuditRecordModel.operation == AuditOperation(operation).value
        )
    if since is not None:
        conditions.append(GovernanceAuditRecordModel.occurred_at >= since)
    if before is not None:
        conditions.append(GovernanceAuditRecordModel.occurred_at < before)

    statement = (
        select(GovernanceAuditRecordModel)
        .where(*conditions)
        .order_by(
            GovernanceAuditRecordModel.occurred_at.desc(),
            GovernanceAuditRecordModel.audit_id.desc(),
        )
        .limit(limit)
    )
    return [_to_persisted(row) for row in session.scalars(statement).all()]


def prune_expired_governance_audit_records(
    session: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Hard-delete only audit records whose explicit retention has expired."""

    current_time = now or _now()
    result = session.execute(
        delete(GovernanceAuditRecordModel).where(
            GovernanceAuditRecordModel.expires_at <= current_time
        )
    )
    session.flush()
    return int(result.rowcount or 0)


__all__ = [
    "DEFAULT_GOVERNANCE_AUDIT_RETENTION_DAYS",
    "MAX_GOVERNANCE_AUDIT_INSPECTION_LIMIT",
    "GovernanceAuditConflictError",
    "PersistedGovernanceAuditRecord",
    "append_governance_audit_record",
    "get_owner_governance_audit_record",
    "list_owner_governance_audit_records",
    "prune_expired_governance_audit_records",
]
