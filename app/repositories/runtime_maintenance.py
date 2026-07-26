"""Cleanup helpers for runtime persistence retention and lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRun,
    ConversationMessage,
    ConversationSummary,
    ConversationThread,
    IdempotencyRecord,
    MemoryRecord,
)
from app.repositories.governance_audit import (
    prune_expired_governance_audit_records,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class RuntimeCleanupReport:
    deleted_threads: int
    deleted_runs: int
    deleted_messages: int
    deleted_summaries: int
    deleted_idempotency_records: int
    deleted_memory_records: int
    deleted_governance_audit_records: int

    @property
    def deleted_total(self) -> int:
        return (
            self.deleted_threads
            + self.deleted_runs
            + self.deleted_messages
            + self.deleted_summaries
            + self.deleted_idempotency_records
            + self.deleted_memory_records
            + self.deleted_governance_audit_records
        )


def _is_expired_or_deleted(
    expires_at: datetime | None,
    deleted_at: datetime | None,
    now: datetime,
) -> bool:
    return (
        (expires_at is not None and _as_utc(expires_at) <= _as_utc(now))
        or (deleted_at is not None and _as_utc(deleted_at) <= _as_utc(now))
    )


def prune_runtime_persistence(
    session: Session,
    *,
    now: datetime | None = None,
) -> RuntimeCleanupReport:
    """Delete expired runtime rows according to retention and deleted-at fields."""

    current_time = now or _now()
    deleted_messages = 0
    deleted_summaries = 0
    deleted_runs = 0
    deleted_threads = 0
    deleted_idempotency_records = 0
    deleted_memory_records = 0

    messages = list(
        session.scalars(
            select(ConversationMessage).order_by(
                ConversationMessage.created_at.asc(),
                ConversationMessage.sequence.asc(),
            )
        )
    )
    for message in messages:
        if _is_expired_or_deleted(message.expires_at, message.deleted_at, current_time):
            session.delete(message)
            deleted_messages += 1

    summaries = list(
        session.scalars(
            select(ConversationSummary).order_by(ConversationSummary.created_at.asc())
        )
    )
    for summary in summaries:
        if _is_expired_or_deleted(summary.expires_at, summary.deleted_at, current_time):
            session.delete(summary)
            deleted_summaries += 1

    runs = list(
        session.scalars(select(AgentRun).order_by(AgentRun.started_at.asc()))
    )
    for run in runs:
        if run.expires_at is not None and _as_utc(run.expires_at) <= _as_utc(current_time):
            session.delete(run)
            deleted_runs += 1

    idempotency_records = list(
        session.scalars(
            select(IdempotencyRecord).order_by(IdempotencyRecord.created_at.asc())
        )
    )
    for record in idempotency_records:
        if record.expires_at is not None and _as_utc(record.expires_at) <= _as_utc(current_time):
            session.delete(record)
            deleted_idempotency_records += 1

    memory_records = list(
        session.scalars(select(MemoryRecord).order_by(MemoryRecord.created_at.asc()))
    )
    for record in memory_records:
        if _is_expired_or_deleted(record.expires_at, record.deleted_at, current_time):
            session.delete(record)
            deleted_memory_records += 1

    threads = list(
        session.scalars(select(ConversationThread).order_by(ConversationThread.created_at.asc()))
    )
    for thread in threads:
        if _is_expired_or_deleted(thread.expires_at, thread.deleted_at, current_time):
            session.delete(thread)
            deleted_threads += 1

    deleted_governance_audit_records = prune_expired_governance_audit_records(
        session,
        now=current_time,
    )
    session.flush()
    return RuntimeCleanupReport(
        deleted_threads=deleted_threads,
        deleted_runs=deleted_runs,
        deleted_messages=deleted_messages,
        deleted_summaries=deleted_summaries,
        deleted_idempotency_records=deleted_idempotency_records,
        deleted_memory_records=deleted_memory_records,
        deleted_governance_audit_records=deleted_governance_audit_records,
    )
