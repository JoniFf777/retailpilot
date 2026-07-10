"""Candidate context repository for V3 write handoff follow-up selections."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CandidateContext


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_blank(value: Optional[str]) -> bool:
    return value is None or not value.strip()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _context_to_dict(context: CandidateContext) -> dict[str, Any]:
    return {
        "user_id": context.user_id,
        "thread_id": context.thread_id,
        "product_ids": list(context.product_ids or []),
        "quantity": context.quantity,
        "expires_at": context.expires_at,
        "created_at": context.created_at,
        "updated_at": context.updated_at,
    }


def prune_candidate_contexts(
    session: Session,
    *,
    now: datetime | None = None,
    max_contexts: int = 100,
) -> int:
    """Delete expired contexts and oldest overflow rows."""

    current_time = now or _now()
    expired_result = session.execute(
        delete(CandidateContext).where(CandidateContext.expires_at <= current_time)
    )
    deleted_count = expired_result.rowcount or 0

    contexts = list(
        session.scalars(
            select(CandidateContext).order_by(
                CandidateContext.created_at.asc(),
                CandidateContext.user_id.asc(),
                CandidateContext.thread_id.asc(),
            )
        )
    )
    overflow_count = len(contexts) - max_contexts
    if overflow_count > 0:
        for context in contexts[:overflow_count]:
            session.delete(context)
        deleted_count += overflow_count

    session.flush()
    return deleted_count


def save_candidate_context(
    session: Session,
    *,
    user_id: str | None,
    thread_id: str | None,
    product_ids: list[str],
    quantity: int,
    ttl_seconds: int = 600,
    max_contexts: int = 100,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Create or replace a same-thread candidate context."""

    if _is_blank(user_id) or _is_blank(thread_id) or not product_ids or quantity <= 0:
        return None

    current_time = now or _now()
    normalized_user_id = str(user_id).strip()
    normalized_thread_id = str(thread_id).strip()
    context = session.get(
        CandidateContext,
        (normalized_user_id, normalized_thread_id),
    )
    if context is None:
        context = CandidateContext(
            user_id=normalized_user_id,
            thread_id=normalized_thread_id,
            product_ids=[],
            quantity=quantity,
            expires_at=current_time,
            created_at=current_time,
            updated_at=current_time,
        )
        session.add(context)

    context.product_ids = [str(product_id) for product_id in product_ids]
    context.quantity = quantity
    context.expires_at = current_time + timedelta(seconds=ttl_seconds)
    context.updated_at = current_time
    session.flush()
    prune_candidate_contexts(
        session,
        now=current_time,
        max_contexts=max_contexts,
    )
    return _context_to_dict(context)


def get_candidate_context(
    session: Session,
    *,
    user_id: str | None,
    thread_id: str | None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return a non-expired candidate context, deleting it if expired."""

    if _is_blank(user_id) or _is_blank(thread_id):
        return None

    context = session.get(
        CandidateContext,
        (str(user_id).strip(), str(thread_id).strip()),
    )
    if context is None:
        return None

    current_time = now or _now()
    if _as_utc(context.expires_at) <= _as_utc(current_time):
        session.delete(context)
        session.flush()
        return None

    return _context_to_dict(context)


def clear_candidate_context(
    session: Session,
    *,
    user_id: str | None,
    thread_id: str | None,
) -> bool:
    """Delete a candidate context for the user/thread pair."""

    if _is_blank(user_id) or _is_blank(thread_id):
        return False

    context = session.get(
        CandidateContext,
        (str(user_id).strip(), str(thread_id).strip()),
    )
    if context is None:
        return False

    session.delete(context)
    session.flush()
    return True
