"""Owner-scoped persistence for the latest validated shopping session state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import ConversationThread
from app.recommendation.session_state import ShoppingSessionState


class ShoppingSessionStateConflict(ValueError):
    """Raised when a stale run attempts to replace a newer thread state."""


MAX_SHOPPING_STATE_PATCHES = 20


def _patch_summary(
    previous: ShoppingSessionState | None,
    current: ShoppingSessionState,
) -> dict[str, Any]:
    """Create a bounded, PII-free state transition record."""

    if previous is None:
        changed = ["initial_state"]
        cleared: list[str] = []
    else:
        old = previous.model_dump(mode="json")
        new = current.model_dump(mode="json")
        ignored = {"version", "updated_at", "candidate_expires_at"}
        changed = sorted(
            key for key in new if key not in ignored and old.get(key) != new.get(key)
        )
        cleared = sorted(
            key
            for key in new
            if key not in ignored
            and old.get(key) not in (None, {}, [], "")
            and new.get(key) in (None, {}, [], "")
        )
    return {
        "version": current.version,
        "changed_fields": changed,
        "cleared_fields": cleared,
        "category": current.category,
        "recorded_at": (current.updated_at or datetime.now(timezone.utc)).isoformat(),
    }


def persist_shopping_session_state(
    session: Session,
    *,
    runtime_thread_id: str,
    user_id: str | None,
    state: ShoppingSessionState | dict[str, Any],
) -> ShoppingSessionState:
    """Atomically store one monotonically versioned state in thread metadata."""

    validated = (
        state
        if isinstance(state, ShoppingSessionState)
        else ShoppingSessionState.model_validate(state)
    )
    if user_id is not None and validated.owner_id not in (None, user_id):
        raise ShoppingSessionStateConflict("shopping session state owner does not match user")
    if validated.owner_id is None and user_id is not None:
        validated = validated.model_copy(update={"owner_id": user_id})
    if validated.updated_at is None:
        validated = validated.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    statement = select(ConversationThread).where(
        ConversationThread.id == runtime_thread_id,
    )
    if user_id is not None:
        statement = statement.where(ConversationThread.user_id == user_id)
    thread = session.scalar(statement)
    if thread is None:
        raise ShoppingSessionStateConflict("shopping session thread is not owned by user")
    current = (thread.metadata_json or {}).get("shopping_session_state")
    current_state = None
    if isinstance(current, dict):
        try:
            current_state = ShoppingSessionState.model_validate(current)
        except Exception as exc:
            raise ShoppingSessionStateConflict("stored shopping session state is invalid") from exc
    expected_version = (current_state.version + 1) if current_state else 1
    if validated.version == (current_state.version if current_state else 0):
        if current_state and validated.model_dump(mode="json") == current_state.model_dump(mode="json"):
            return current_state
        raise ShoppingSessionStateConflict("shopping session state version is stale")
    if validated.version != expected_version:
        raise ShoppingSessionStateConflict("shopping session state version conflict")
    metadata = dict(thread.metadata_json or {})
    patch_history = metadata.get("shopping_session_state_patches")
    if not isinstance(patch_history, list):
        patch_history = []
    patch_history = [item for item in patch_history if isinstance(item, dict)]
    patch_history.append(_patch_summary(current_state, validated))
    metadata["shopping_session_state_patches"] = patch_history[-MAX_SHOPPING_STATE_PATCHES:]
    metadata["shopping_session_state"] = validated.model_dump(mode="json")
    # Optimistic compare-and-swap prevents two processes from silently losing a
    # state transition.  PostgreSQL and SQLite both support JSON equality here;
    # the row lock is an additional guard on databases that implement it.
    try:
        session.execute(
            select(ConversationThread)
            .where(ConversationThread.id == runtime_thread_id)
            .with_for_update()
        )
    except Exception:
        pass
    current_metadata = dict(thread.metadata_json or {})
    result = session.execute(
        update(ConversationThread)
        .where(
            ConversationThread.id == runtime_thread_id,
            ConversationThread.metadata_json == current_metadata,
        )
        .values(metadata_json=metadata)
    )
    if result.rowcount != 1:
        raise ShoppingSessionStateConflict("shopping session state changed concurrently")
    thread.metadata_json = metadata
    session.flush()
    return validated


__all__ = ["ShoppingSessionStateConflict", "persist_shopping_session_state"]
