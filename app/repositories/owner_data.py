"""Exact-owner inspection, correction, and deletion persistence operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRun,
    AgentRunEvent,
    CandidateContext,
    CartItem,
    ConversationMessage,
    ConversationSummary,
    ConversationThread,
    IdempotencyRecord,
    MemoryRecord,
    PendingAction,
    UserPreference,
)


MAX_OWNER_MEMORY_INSPECTION_RECORDS = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _memory_to_dict(record: MemoryRecord) -> dict[str, Any]:
    confidence = (
        float(record.confidence) if record.confidence is not None else None
    )
    return {
        "memory_id": record.id,
        "thread_id": record.thread_id,
        "kind": record.memory_kind,
        "scope": record.scope,
        "content": record.content_text,
        "content_json": dict(record.content_json or {}),
        "priority": record.priority,
        "token_count": record.token_count,
        "confidence": confidence,
        "status": record.status,
        "expires_at": record.expires_at,
        "deleted_at": record.deleted_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _count(session: Session, model: type, condition) -> int:
    return int(
        session.scalar(select(func.count()).select_from(model).where(condition))
        or 0
    )


def inspect_owner_data(
    session: Session,
    *,
    owner_id: str,
    memory_limit: int = 50,
) -> dict[str, Any]:
    """Return a bounded owner inventory and inspectable active memory records."""

    if not 1 <= memory_limit <= MAX_OWNER_MEMORY_INSPECTION_RECORDS:
        raise ValueError("Owner memory inspection limit is invalid.")
    owner_threads = select(ConversationThread.id).where(
        ConversationThread.user_id == owner_id
    )
    owner_runs = select(AgentRun.id).where(
        or_(
            AgentRun.user_id == owner_id,
            AgentRun.thread_id.in_(owner_threads),
        )
    )
    counts = {
        "preferences": _count(
            session,
            UserPreference,
            UserPreference.user_id == owner_id,
        ),
        "cart_items": _count(session, CartItem, CartItem.user_id == owner_id),
        "pending_actions": _count(
            session,
            PendingAction,
            PendingAction.user_id == owner_id,
        ),
        "candidate_contexts": _count(
            session,
            CandidateContext,
            CandidateContext.user_id == owner_id,
        ),
        "conversation_threads": _count(
            session,
            ConversationThread,
            ConversationThread.user_id == owner_id,
        ),
        "conversation_messages": _count(
            session,
            ConversationMessage,
            or_(
                ConversationMessage.user_id == owner_id,
                ConversationMessage.thread_id.in_(owner_threads),
            ),
        ),
        "agent_runs": _count(
            session,
            AgentRun,
            or_(
                AgentRun.user_id == owner_id,
                AgentRun.thread_id.in_(owner_threads),
            ),
        ),
        "agent_run_events": _count(
            session,
            AgentRunEvent,
            or_(
                AgentRunEvent.user_id == owner_id,
                AgentRunEvent.run_id.in_(owner_runs),
            ),
        ),
        "conversation_summaries": _count(
            session,
            ConversationSummary,
            or_(
                ConversationSummary.user_id == owner_id,
                ConversationSummary.thread_id.in_(owner_threads),
            ),
        ),
        "idempotency_records": _count(
            session,
            IdempotencyRecord,
            or_(
                IdempotencyRecord.user_id == owner_id,
                IdempotencyRecord.thread_id.in_(owner_threads),
            ),
        ),
        "memory_records": _count(
            session,
            MemoryRecord,
            (MemoryRecord.user_id == owner_id)
            & (MemoryRecord.scope != "operational"),
        ),
    }
    memories = list(
        session.scalars(
            select(MemoryRecord)
            .where(
                MemoryRecord.user_id == owner_id,
                MemoryRecord.scope != "operational",
            )
            .order_by(
                MemoryRecord.priority.desc(),
                MemoryRecord.created_at.desc(),
                MemoryRecord.id.asc(),
            )
            .limit(memory_limit)
        )
    )
    return {
        "counts": counts,
        "total_records": sum(counts.values()),
        "memories": [_memory_to_dict(record) for record in memories],
        "memory_limit": memory_limit,
        "memory_truncated": counts["memory_records"] > len(memories),
    }


def correct_owner_memory_record(
    session: Session,
    *,
    owner_id: str,
    memory_id: str,
    content: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Replace one active owner memory and discard stale derived structure."""

    current_time = now or _now()
    record = session.scalar(
        select(MemoryRecord).where(
            MemoryRecord.id == memory_id,
            MemoryRecord.user_id == owner_id,
            MemoryRecord.scope != "operational",
            MemoryRecord.status == "active",
            MemoryRecord.deleted_at.is_(None),
            or_(
                MemoryRecord.expires_at.is_(None),
                MemoryRecord.expires_at > current_time,
            ),
        )
    )
    if record is None:
        return None
    record.content_text = content
    record.content_json = {}
    record.provenance_json = {"source": "owner_correction"}
    record.token_count = max(1, (len(content) + 3) // 4)
    record.confidence = 1.0
    record.updated_at = current_time
    session.flush()
    return _memory_to_dict(record)


def delete_owner_memory_record(
    session: Session,
    *,
    owner_id: str,
    memory_id: str,
) -> dict[str, Any] | None:
    """Hard-delete one exact-owner memory and return its closed classification."""

    record = session.scalar(
        select(MemoryRecord).where(
            MemoryRecord.id == memory_id,
            MemoryRecord.user_id == owner_id,
            MemoryRecord.scope != "operational",
        )
    )
    if record is None:
        return None
    result = {
        "memory_id": record.id,
        "kind": record.memory_kind,
        "scope": record.scope,
        "thread_id": record.thread_id,
    }
    session.delete(record)
    session.flush()
    return result


def _delete_count(session: Session, model: type, condition) -> int:
    result = session.execute(
        delete(model)
        .where(condition)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def delete_all_owner_data(
    session: Session,
    *,
    owner_id: str,
) -> dict[str, int]:
    """Hard-delete ShopMind owner data while retaining independent audit facts."""

    thread_ids = list(
        session.scalars(
            select(ConversationThread.id).where(
                ConversationThread.user_id == owner_id
            )
        )
    )
    run_scope = AgentRun.user_id == owner_id
    if thread_ids:
        run_scope = or_(run_scope, AgentRun.thread_id.in_(thread_ids))
    run_ids = list(session.scalars(select(AgentRun.id).where(run_scope)))

    event_scope = AgentRunEvent.user_id == owner_id
    message_scope = ConversationMessage.user_id == owner_id
    summary_scope = ConversationSummary.user_id == owner_id
    idempotency_scope = IdempotencyRecord.user_id == owner_id
    memory_scope = MemoryRecord.user_id == owner_id
    if run_ids:
        event_scope = or_(event_scope, AgentRunEvent.run_id.in_(run_ids))
    if thread_ids:
        message_scope = or_(
            message_scope,
            ConversationMessage.thread_id.in_(thread_ids),
        )
        summary_scope = or_(
            summary_scope,
            ConversationSummary.thread_id.in_(thread_ids),
        )
        idempotency_scope = or_(
            idempotency_scope,
            IdempotencyRecord.thread_id.in_(thread_ids),
        )
        memory_scope = or_(
            memory_scope,
            MemoryRecord.thread_id.in_(thread_ids),
        )

    counts = {
        "agent_run_events": _delete_count(
            session,
            AgentRunEvent,
            event_scope,
        ),
        "conversation_summaries": _delete_count(
            session,
            ConversationSummary,
            summary_scope,
        ),
        "idempotency_records": _delete_count(
            session,
            IdempotencyRecord,
            idempotency_scope,
        ),
        "memory_records": _delete_count(
            session,
            MemoryRecord,
            memory_scope,
        ),
        "conversation_messages": _delete_count(
            session,
            ConversationMessage,
            message_scope,
        ),
        "agent_runs": _delete_count(session, AgentRun, run_scope),
        "conversation_threads": (
            _delete_count(
                session,
                ConversationThread,
                ConversationThread.id.in_(thread_ids),
            )
            if thread_ids
            else 0
        ),
        "candidate_contexts": _delete_count(
            session,
            CandidateContext,
            CandidateContext.user_id == owner_id,
        ),
        "pending_actions": _delete_count(
            session,
            PendingAction,
            PendingAction.user_id == owner_id,
        ),
        "cart_items": _delete_count(
            session,
            CartItem,
            CartItem.user_id == owner_id,
        ),
        "preferences": _delete_count(
            session,
            UserPreference,
            UserPreference.user_id == owner_id,
        ),
    }
    session.flush()
    return counts


__all__ = [
    "MAX_OWNER_MEMORY_INSPECTION_RECORDS",
    "correct_owner_memory_record",
    "delete_all_owner_data",
    "delete_owner_memory_record",
    "inspect_owner_data",
]
