"""Repositories for runtime conversation threads, messages, and summaries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ConversationMessage, ConversationSummary, ConversationThread


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _merge_metadata(
    current: dict[str, Any] | None,
    new_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(current or {})
    if new_metadata:
        merged.update(new_metadata)
    return merged


def _thread_to_dict(thread: ConversationThread) -> dict[str, Any]:
    return {
        "thread_id": thread.id,
        "user_id": thread.user_id,
        "client_thread_id": thread.client_thread_id,
        "title": thread.title,
        "status": thread.status,
        "metadata": dict(thread.metadata_json or {}),
        "last_message_at": thread.last_message_at,
        "last_run_at": thread.last_run_at,
        "expires_at": thread.expires_at,
        "deleted_at": thread.deleted_at,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


def _message_to_dict(message: ConversationMessage) -> dict[str, Any]:
    return {
        "message_id": message.id,
        "thread_id": message.thread_id,
        "user_id": message.user_id,
        "run_id": message.run_id,
        "sequence": message.sequence,
        "role": message.role,
        "message_type": message.message_type,
        "content_text": message.content_text,
        "content_json": dict(message.content_json or {}),
        "metadata": dict(message.metadata_json or {}),
        "expires_at": message.expires_at,
        "deleted_at": message.deleted_at,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    }


def _summary_to_dict(summary: ConversationSummary) -> dict[str, Any]:
    return {
        "summary_id": summary.id,
        "thread_id": summary.thread_id,
        "user_id": summary.user_id,
        "source_run_id": summary.source_run_id,
        "start_message_sequence": summary.start_message_sequence,
        "end_message_sequence": summary.end_message_sequence,
        "summary_text": summary.summary_text,
        "summary_json": dict(summary.summary_json or {}),
        "status": summary.status,
        "expires_at": summary.expires_at,
        "deleted_at": summary.deleted_at,
        "created_at": summary.created_at,
        "updated_at": summary.updated_at,
    }


def get_or_create_conversation_thread(
    session: Session,
    *,
    user_id: str | None,
    client_thread_id: str | None,
    runtime_thread_id: str | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Return an existing scoped thread or create a new runtime thread."""

    current_time = now or _now()
    normalized_user_id = _clean_optional(user_id)
    normalized_client_thread_id = _clean_optional(client_thread_id)
    thread: ConversationThread | None = None

    if normalized_user_id and normalized_client_thread_id:
        thread = session.scalar(
            select(ConversationThread).where(
                ConversationThread.user_id == normalized_user_id,
                ConversationThread.client_thread_id == normalized_client_thread_id,
            )
        )

    if thread is None:
        thread = ConversationThread(
            id=runtime_thread_id or str(uuid4()),
            user_id=normalized_user_id,
            client_thread_id=normalized_client_thread_id,
            title=title,
            status="active",
            metadata_json=metadata or {},
            expires_at=expires_at,
            created_at=current_time,
            updated_at=current_time,
        )
        session.add(thread)
    else:
        if title is not None:
            thread.title = title
        thread.status = "active"
        thread.metadata_json = _merge_metadata(thread.metadata_json, metadata)
        thread.expires_at = expires_at
        thread.updated_at = current_time

    session.flush()
    return _thread_to_dict(thread)


def get_conversation_thread(
    session: Session,
    *,
    runtime_thread_id: str | None = None,
    user_id: str | None = None,
    client_thread_id: str | None = None,
) -> dict[str, Any] | None:
    """Look up a conversation thread by runtime ID or user/client scope."""

    thread: ConversationThread | None = None
    if runtime_thread_id:
        statement = select(ConversationThread).where(
            ConversationThread.id == runtime_thread_id
        )
        normalized_user_id = _clean_optional(user_id)
        if normalized_user_id is not None:
            statement = statement.where(ConversationThread.user_id == normalized_user_id)
        thread = session.scalar(statement)
    else:
        normalized_user_id = _clean_optional(user_id)
        normalized_client_thread_id = _clean_optional(client_thread_id)
        if normalized_user_id and normalized_client_thread_id:
            thread = session.scalar(
                select(ConversationThread).where(
                    ConversationThread.user_id == normalized_user_id,
                    ConversationThread.client_thread_id == normalized_client_thread_id,
                )
            )

    return None if thread is None else _thread_to_dict(thread)


def _next_message_sequence(session: Session, *, thread_id: str) -> int:
    sequence = session.scalar(
        select(func.max(ConversationMessage.sequence)).where(
            ConversationMessage.thread_id == thread_id
        )
    )
    return int(sequence or 0) + 1


def append_conversation_message(
    session: Session,
    *,
    thread_id: str,
    role: str,
    user_id: str | None = None,
    run_id: str | None = None,
    sequence: int | None = None,
    message_type: str = "message",
    content_text: str | None = None,
    content_json: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    message_id: str | None = None,
    now: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or _now()
    message = ConversationMessage(
        id=message_id or str(uuid4()),
        thread_id=thread_id,
        user_id=_clean_optional(user_id),
        run_id=run_id,
        sequence=sequence or _next_message_sequence(session, thread_id=thread_id),
        role=role,
        message_type=message_type,
        content_text=content_text,
        content_json=content_json or {},
        metadata_json=metadata or {},
        expires_at=expires_at,
        created_at=current_time,
        updated_at=current_time,
    )
    session.add(message)

    thread = session.get(ConversationThread, thread_id)
    if thread is not None:
        thread.last_message_at = current_time
        thread.updated_at = current_time

    session.flush()
    return _message_to_dict(message)


def list_conversation_messages(
    session: Session,
    *,
    thread_id: str,
    user_id: str | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    statement = select(ConversationMessage).where(
        ConversationMessage.thread_id == thread_id
    )
    normalized_user_id = _clean_optional(user_id)
    if normalized_user_id is not None:
        statement = statement.where(ConversationMessage.user_id == normalized_user_id)
    if not include_deleted:
        statement = statement.where(ConversationMessage.deleted_at.is_(None))
    statement = statement.order_by(ConversationMessage.sequence.asc())
    if limit is not None:
        statement = statement.limit(limit)
    return [_message_to_dict(message) for message in session.scalars(statement).all()]


def create_conversation_summary(
    session: Session,
    *,
    thread_id: str,
    user_id: str | None,
    start_message_sequence: int,
    end_message_sequence: int,
    summary_text: str,
    source_run_id: str | None = None,
    summary_json: dict[str, Any] | None = None,
    status: str = "active",
    summary_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or _now()
    payload = dict(summary_json or {})
    if metadata:
        payload.setdefault("metadata", {}).update(metadata)

    summary = ConversationSummary(
        id=summary_id or str(uuid4()),
        thread_id=thread_id,
        user_id=_clean_optional(user_id),
        source_run_id=source_run_id,
        start_message_sequence=start_message_sequence,
        end_message_sequence=end_message_sequence,
        summary_text=summary_text,
        summary_json=payload,
        status=status,
        expires_at=expires_at,
        created_at=current_time,
        updated_at=current_time,
    )
    session.add(summary)
    session.flush()
    return _summary_to_dict(summary)


def list_conversation_summaries(
    session: Session,
    *,
    thread_id: str,
    user_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    statement = select(ConversationSummary).where(
        ConversationSummary.thread_id == thread_id
    )
    normalized_user_id = _clean_optional(user_id)
    if normalized_user_id is not None:
        statement = statement.where(ConversationSummary.user_id == normalized_user_id)
    if status is not None:
        statement = statement.where(ConversationSummary.status == status)
    statement = statement.order_by(
        ConversationSummary.start_message_sequence.asc(),
        ConversationSummary.created_at.asc(),
    )
    return [_summary_to_dict(summary) for summary in session.scalars(statement).all()]
