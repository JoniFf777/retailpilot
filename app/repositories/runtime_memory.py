"""Scoped persistence for explicit runtime memory records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db.models import MemoryRecord


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _memory_to_dict(record: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": record.id,
        "user_id": record.user_id,
        "thread_id": record.thread_id,
        "source_run_id": record.source_run_id,
        "source_message_id": record.source_message_id,
        "kind": record.memory_kind,
        "scope": record.scope,
        "content": record.content_text,
        "content_json": dict(record.content_json or {}),
        "provenance": dict(record.provenance_json or {}),
        "priority": record.priority,
        "token_count": record.token_count,
        "confidence": record.confidence,
        "status": record.status,
        "expires_at": record.expires_at,
        "deleted_at": record.deleted_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_memory_record(
    session: Session,
    *,
    memory_kind: str,
    scope: str,
    content_text: str,
    user_id: str | None = None,
    thread_id: str | None = None,
    source_run_id: str | None = None,
    source_message_id: str | None = None,
    content_json: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    priority: int = 0,
    token_count: int = 0,
    confidence: float | None = None,
    expires_at: datetime | None = None,
    memory_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or _now()
    record = MemoryRecord(
        id=memory_id or str(uuid4()),
        user_id=user_id,
        thread_id=thread_id,
        source_run_id=source_run_id,
        source_message_id=source_message_id,
        memory_kind=memory_kind,
        scope=scope,
        content_text=content_text,
        content_json=content_json or {},
        provenance_json=provenance or {},
        priority=priority,
        token_count=token_count,
        confidence=confidence,
        status="active",
        expires_at=expires_at,
        created_at=current_time,
        updated_at=current_time,
    )
    session.add(record)
    session.flush()
    return _memory_to_dict(record)


def list_memory_records(
    session: Session,
    *,
    user_id: str | None,
    thread_id: str | None,
    memory_kinds: list[str] | None = None,
    include_operational: bool = False,
    now: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    current_time = now or _now()
    conditions = [
        MemoryRecord.status == "active",
        MemoryRecord.deleted_at.is_(None),
        or_(MemoryRecord.expires_at.is_(None), MemoryRecord.expires_at > current_time),
    ]
    if memory_kinds:
        conditions.append(MemoryRecord.memory_kind.in_(memory_kinds))

    scoped_records = []
    if user_id is not None:
        scoped_records.extend(
            [
                (MemoryRecord.user_id == user_id)
                & MemoryRecord.thread_id.is_(None),
            ]
        )
        if thread_id is not None:
            scoped_records.append(
                (MemoryRecord.user_id == user_id)
                & (MemoryRecord.thread_id == thread_id)
            )
    elif thread_id is not None:
        scoped_records.append(
            MemoryRecord.user_id.is_(None) & (MemoryRecord.thread_id == thread_id)
        )
    if include_operational:
        scoped_records.append(
            MemoryRecord.user_id.is_(None) & MemoryRecord.thread_id.is_(None)
        )
    if not scoped_records:
        return []

    statement = (
        select(MemoryRecord)
        .where(*conditions, or_(*scoped_records))
        .order_by(MemoryRecord.priority.desc(), MemoryRecord.created_at.desc())
        .limit(limit)
    )
    return [_memory_to_dict(record) for record in session.scalars(statement).all()]


def soft_delete_memory_record(
    session: Session,
    *,
    memory_id: str,
    user_id: str | None,
    thread_id: str | None = None,
    now: datetime | None = None,
) -> bool:
    current_time = now or _now()
    scope = [MemoryRecord.id == memory_id, MemoryRecord.deleted_at.is_(None)]
    if user_id is None:
        scope.append(MemoryRecord.user_id.is_(None))
    else:
        scope.append(MemoryRecord.user_id == user_id)
    if thread_id is not None:
        scope.append(MemoryRecord.thread_id == thread_id)
    result = session.execute(
        update(MemoryRecord)
        .where(*scope)
        .values(status="deleted", deleted_at=current_time, updated_at=current_time)
    )
    session.flush()
    return bool(result.rowcount)
