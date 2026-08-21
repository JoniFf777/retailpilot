"""Repositories for runtime runs, events, and idempotency records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AgentRun, AgentRunEvent, ConversationThread, IdempotencyRecord
from app.schemas.recommendation import RecommendationResult


class RuntimeIdempotencyPersistenceError(RuntimeError):
    """The runtime could not establish or read an authoritative claim."""


@dataclass(frozen=True)
class IdempotencyClaim:
    claimed: bool
    record: dict[str, Any]


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


def _run_to_dict(run: AgentRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "thread_id": run.thread_id,
        "user_id": run.user_id,
        "parent_run_id": run.parent_run_id,
        "operation": run.operation,
        "mode": run.mode,
        "status": run.status,
        "request_id": run.request_id,
        "trace_id": run.trace_id,
        "idempotency_key": run.idempotency_key,
        "pending_action_id": run.pending_action_id,
        "input_text": run.input_text,
        "output_text": run.output_text,
        "request_json": dict(run.request_json or {}),
        "result_json": dict(run.result_json or {}),
        "error_json": None if run.error_json is None else dict(run.error_json),
        "usage_json": dict(run.usage_json or {}),
        "debug_json": None if run.debug_json is None else dict(run.debug_json),
        "tool_call_records_json": list(run.tool_call_records_json or []),
        "metadata": dict(run.metadata_json or {}),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "expires_at": run.expires_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def get_agent_run(session: Session, *, run_id: str) -> dict[str, Any] | None:
    """Return one persisted runtime run for replay or operational inspection."""

    run = session.get(AgentRun, run_id)
    return None if run is None else _run_to_dict(run)


def get_owned_recommendation_run(
    session: Session,
    *,
    run_id: str,
    user_id: str,
    thread_id: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return a validated recommendation only when the run is fully in scope.

    This is deliberately the sole authority for recommendation-backed writes.
    A mismatch, missing run, expired run, or corrupt/non-recommended result all
    return ``None`` so API callers can use one non-enumerating 404 response.
    """

    normalized_run = run_id.strip()
    normalized_user = user_id.strip()
    normalized_thread = thread_id.strip()
    if not normalized_run or not normalized_user or not normalized_thread:
        return None
    # Public APIs carry the stable client thread id, while the runtime
    # persistence layer stores its own UUID thread id. Accept either exact
    # form only within the same owner-scoped ConversationThread.
    run = session.scalar(
        select(AgentRun)
        .join(ConversationThread, ConversationThread.id == AgentRun.thread_id)
        .where(
            AgentRun.id == normalized_run,
            AgentRun.user_id == normalized_user,
            AgentRun.operation == "chat",
            AgentRun.status == "completed",
            or_(
                AgentRun.thread_id == normalized_thread,
                ConversationThread.client_thread_id == normalized_thread,
            ),
        )
    )
    if run is None:
        return None
    current_time = now or _now()
    if run.expires_at is not None:
        expiry = run.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= current_time:
            return None
    raw_recommendation = (run.result_json or {}).get("recommendation")
    if raw_recommendation is None:
        return None
    try:
        recommendation = RecommendationResult.model_validate(raw_recommendation)
    except Exception:
        return None
    if recommendation.outcome != "recommended":
        return None
    return {"run": _run_to_dict(run), "recommendation": recommendation}


def _event_to_dict(event: AgentRunEvent) -> dict[str, Any]:
    return {
        "event_id": event.id,
        "run_id": event.run_id,
        "thread_id": event.thread_id,
        "user_id": event.user_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "agent_name": event.agent_name,
        "visibility": event.visibility,
        "payload_json": dict(event.payload_json or {}),
        "trace_id": event.trace_id,
        "tool_call_id": event.tool_call_id,
        "created_at": event.created_at,
    }


def _idempotency_to_dict(record: IdempotencyRecord) -> dict[str, Any]:
    return {
        "idempotency_record_id": record.id,
        "user_id": record.user_id,
        "thread_id": record.thread_id,
        "run_id": record.run_id,
        "operation": record.operation,
        "idempotency_key": record.idempotency_key,
        "request_hash": record.request_hash,
        "status": record.status,
        "response_fingerprint": record.response_fingerprint,
        "metadata": dict(record.metadata_json or {}),
        "expires_at": record.expires_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_agent_run(
    session: Session,
    *,
    run_id: str,
    thread_id: str,
    operation: str,
    mode: str,
    status: str,
    request_id: str,
    trace_id: str,
    started_at: datetime,
    user_id: str | None = None,
    parent_run_id: str | None = None,
    idempotency_key: str | None = None,
    pending_action_id: str | None = None,
    input_text: str | None = None,
    request_json: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = AgentRun(
        id=run_id,
        thread_id=thread_id,
        user_id=_clean_optional(user_id),
        parent_run_id=parent_run_id,
        operation=operation,
        mode=mode,
        status=status,
        request_id=request_id,
        trace_id=trace_id,
        idempotency_key=_clean_optional(idempotency_key),
        pending_action_id=pending_action_id,
        input_text=input_text,
        request_json=request_json or {},
        result_json={},
        usage_json={},
        tool_call_records_json=[],
        metadata_json=metadata or {},
        started_at=started_at,
        expires_at=expires_at,
        created_at=started_at,
        updated_at=started_at,
    )
    session.add(run)

    thread = session.get(ConversationThread, thread_id)
    if thread is not None:
        thread.last_run_at = started_at
        thread.updated_at = started_at

    session.flush()
    return _run_to_dict(run)


def finalize_agent_run(
    session: Session,
    *,
    run_id: str,
    status: str,
    completed_at: datetime | None = None,
    output_text: str | None = None,
    result_json: dict[str, Any] | None = None,
    error_json: dict[str, Any] | None = None,
    usage_json: dict[str, Any] | None = None,
    debug_json: dict[str, Any] | None = None,
    pending_action_id: str | None = None,
    tool_call_records_json: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    run = session.get(AgentRun, run_id)
    if run is None:
        return None

    finished_at = completed_at or _now()
    run.status = status
    run.completed_at = finished_at
    run.updated_at = finished_at
    run.output_text = output_text
    run.result_json = result_json or {}
    run.error_json = error_json
    run.usage_json = usage_json or {}
    run.debug_json = debug_json
    run.pending_action_id = pending_action_id
    run.tool_call_records_json = tool_call_records_json or []
    run.metadata_json = _merge_metadata(run.metadata_json, metadata)

    thread = session.get(ConversationThread, run.thread_id)
    if thread is not None:
        thread.last_run_at = finished_at
        thread.updated_at = finished_at

    session.flush()
    return _run_to_dict(run)


def _next_event_sequence(session: Session, *, run_id: str) -> int:
    sequence = session.scalar(
        select(func.max(AgentRunEvent.sequence)).where(AgentRunEvent.run_id == run_id)
    )
    return int(sequence or 0) + 1


def append_agent_run_event(
    session: Session,
    *,
    run_id: str,
    thread_id: str,
    event_type: str,
    visibility: str,
    user_id: str | None = None,
    sequence: int | None = None,
    agent_name: str | None = None,
    payload_json: dict[str, Any] | None = None,
    trace_id: str | None = None,
    tool_call_id: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    event = AgentRunEvent(
        run_id=run_id,
        thread_id=thread_id,
        user_id=_clean_optional(user_id),
        sequence=sequence or _next_event_sequence(session, run_id=run_id),
        event_type=event_type,
        agent_name=agent_name,
        visibility=visibility,
        payload_json=payload_json or {},
        trace_id=trace_id,
        tool_call_id=tool_call_id,
        created_at=created_at or _now(),
    )
    session.add(event)
    session.flush()
    return _event_to_dict(event)


def list_agent_run_events(session: Session, *, run_id: str) -> list[dict[str, Any]]:
    statement = (
        select(AgentRunEvent)
        .where(AgentRunEvent.run_id == run_id)
        .order_by(AgentRunEvent.sequence.asc(), AgentRunEvent.id.asc())
    )
    return [_event_to_dict(event) for event in session.scalars(statement).all()]


def inspect_owner_agent_run(
    session: Session,
    *,
    owner_id: str,
    event_limit: int,
    run_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any] | None:
    """Project one exact-owner run without content or internal event payloads."""

    if (run_id is None) == (trace_id is None):
        raise ValueError("Exactly one run selector is required.")
    if not 1 <= event_limit <= 100:
        raise ValueError("Run inspection event limit is out of bounds.")

    statement = select(AgentRun).where(
        AgentRun.user_id == owner_id.strip(),
    )
    if run_id is not None:
        statement = statement.where(AgentRun.id == run_id.strip())
    else:
        statement = statement.where(AgentRun.trace_id == trace_id.strip())
    statement = statement.order_by(
        AgentRun.started_at.desc(),
        AgentRun.id.desc(),
    ).limit(1)
    run = session.scalar(statement)
    if run is None:
        return None

    event_filter = (
        AgentRunEvent.run_id == run.id,
        AgentRunEvent.visibility == "client",
    )
    client_event_count = int(
        session.scalar(
            select(func.count(AgentRunEvent.id)).where(*event_filter)
        )
        or 0
    )
    events = session.scalars(
        select(AgentRunEvent)
        .where(*event_filter)
        .order_by(AgentRunEvent.sequence.asc(), AgentRunEvent.id.asc())
        .limit(event_limit)
    ).all()
    return {
        "run_id": run.id,
        "trace_id": run.trace_id,
        "thread_id": run.thread_id,
        "operation": run.operation,
        "mode": run.mode,
        "status": run.status,
        "pending_action_id": run.pending_action_id,
        "usage": dict(run.usage_json or {}),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "client_event_count": client_event_count,
        "events": [
            {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "agent_name": event.agent_name,
                "visibility": event.visibility,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "event_limit": event_limit,
        "events_truncated": client_event_count > len(events),
    }


def save_idempotency_record(
    session: Session,
    *,
    user_id: str | None,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    status: str,
    thread_id: str | None = None,
    run_id: str | None = None,
    response_fingerprint: str | None = None,
    record_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or _now()
    normalized_user_id = _clean_optional(user_id)
    normalized_key = idempotency_key.strip()
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == normalized_user_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == normalized_key,
        )
    )

    if record is None:
        record = IdempotencyRecord(
            id=record_id or str(uuid4()),
            user_id=normalized_user_id,
            thread_id=thread_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            status=status,
            response_fingerprint=response_fingerprint,
            metadata_json=metadata or {},
            expires_at=expires_at,
            created_at=current_time,
            updated_at=current_time,
        )
        session.add(record)
    else:
        record.thread_id = thread_id
        record.run_id = run_id
        record.request_hash = request_hash
        record.status = status
        record.response_fingerprint = response_fingerprint
        record.metadata_json = _merge_metadata(record.metadata_json, metadata)
        record.expires_at = expires_at
        record.updated_at = current_time

    session.flush()
    return _idempotency_to_dict(record)


def get_idempotency_record(
    session: Session,
    *,
    user_id: str | None,
    operation: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == _clean_optional(user_id),
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == idempotency_key.strip(),
        )
    )
    return None if record is None else _idempotency_to_dict(record)


def claim_idempotency_record(
    session: Session,
    *,
    user_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    run_id: str,
    thread_id: str | None = None,
    now: datetime | None = None,
    expires_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> IdempotencyClaim:
    """Atomically claim one runtime execution identity.

    The nested transaction is essential for PostgreSQL: a concurrent unique
    insert conflict must be rolled back to a savepoint before the winner can
    be read from the outer transaction.
    """

    normalized_user_id = user_id.strip()
    normalized_key = idempotency_key.strip()
    existing = session.scalar(
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.user_id == normalized_user_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == normalized_key,
        )
        .with_for_update()
    )
    if existing is not None:
        return IdempotencyClaim(claimed=False, record=_idempotency_to_dict(existing))

    current_time = now or _now()
    record = IdempotencyRecord(
        id=str(uuid4()),
        user_id=normalized_user_id,
        thread_id=thread_id,
        # IdempotencyRecord.run_id has an FK to AgentRun.  The claim must be
        # committed atomically with creation of that run, so leave this
        # nullable during the claim and bind the authoritative run below in
        # the same outer transaction.
        run_id=None,
        operation=operation,
        idempotency_key=normalized_key,
        request_hash=request_hash,
        status="started",
        metadata_json=metadata or {},
        expires_at=expires_at,
        created_at=current_time,
        updated_at=current_time,
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError as exc:
        winner = session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == normalized_user_id,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == normalized_key,
            )
            .with_for_update()
        )
        if winner is None:
            raise RuntimeIdempotencyPersistenceError(
                "Runtime idempotency claim could not be resolved after a unique conflict."
            ) from exc
        return IdempotencyClaim(claimed=False, record=_idempotency_to_dict(winner))
    return IdempotencyClaim(claimed=True, record=_idempotency_to_dict(record))
