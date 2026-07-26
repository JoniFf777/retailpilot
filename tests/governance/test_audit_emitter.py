from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import GovernanceAuditRecord as GovernanceAuditRecordModel
from app.governance import (
    GovernanceAuditEmissionReason,
    GovernanceAuditEmissionStatus,
    GovernanceAuditEmitter,
    project_runtime_governance_records,
)
from app.runtime import (
    AgentEvent,
    EventVisibility,
    RunContext,
    RunOperation,
    RunRequest,
    RunResult,
    RunStatus,
)
from app.security import (
    AuditDecision,
    AuditOperation,
    AuditReason,
    GovernanceAuditFactory,
)


NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def make_record():
    return GovernanceAuditFactory(
        clock=lambda: NOW,
        audit_id_factory=lambda: UUID(
            "00000000-0000-0000-0000-000000000201"
        ),
    ).action_decision(
        operation=AuditOperation.ACTION_CONFIRM,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.COMPLETED,
        action_type="add_to_cart",
        action_id="private-action-emitter",
        principal=None,
        owner_id="private-owner-emitter",
    )


def test_emitter_commits_independent_batch_and_replay_is_duplicate():
    Session = make_session_factory()
    emitter = GovernanceAuditEmitter(Session)
    record = make_record()

    first = emitter.emit(record)
    duplicate = emitter.emit(record)
    session = Session()
    try:
        rows = session.query(GovernanceAuditRecordModel).all()
    finally:
        session.close()

    assert first.status == "persisted"
    assert first.reason == "completed"
    assert first.persisted_records == 1
    assert duplicate.status == "duplicate"
    assert duplicate.reason == "already_exists"
    assert duplicate.duplicate_records == 1
    assert len(rows) == 1


def test_emitter_disabled_and_empty_batches_are_closed_skips():
    disabled = GovernanceAuditEmitter(None).emit(make_record())
    empty = GovernanceAuditEmitter(None).emit_many([])

    assert disabled.status == GovernanceAuditEmissionStatus.SKIPPED
    assert disabled.reason == GovernanceAuditEmissionReason.DISABLED
    assert disabled.requested_records == 1
    assert empty.status == GovernanceAuditEmissionStatus.SKIPPED
    assert empty.reason == GovernanceAuditEmissionReason.NO_RECORDS


def test_emitter_storage_failure_is_sanitized_and_never_raises(caplog):
    def unavailable_session():
        raise RuntimeError(
            "private database host and password must never escape"
        )

    result = GovernanceAuditEmitter(unavailable_session).emit(make_record())
    serialized = result.model_dump_json()

    assert result.status == "failed"
    assert result.reason == "storage_unavailable"
    assert result.persisted_records == 0
    assert "private database" not in serialized
    assert "password" not in serialized
    assert "storage_unavailable" in caplog.text
    assert "private database" not in caplog.text


@pytest.mark.parametrize(
    (
        "event_type",
        "event_reason",
        "confirmed",
        "expected_operation",
        "expected_decision",
        "expected_reason",
    ),
    (
        (
            "action.resumed",
            None,
            True,
            "action.resume",
            "succeeded",
            "owner_matched",
        ),
        (
            "action.confirmed",
            None,
            True,
            "action.confirm",
            "succeeded",
            "completed",
        ),
        (
            "action.cancelled",
            None,
            False,
            "action.cancel",
            "succeeded",
            "cancelled",
        ),
        (
            "action.expired",
            None,
            True,
            "action.expire",
            "succeeded",
            "expired",
        ),
        (
            "action.failed",
            "invalid_edit",
            True,
            "action.confirm",
            "denied",
            "validation_failed",
        ),
        (
            "action.failed",
            "handler_failed",
            True,
            "action.confirm",
            "failed",
            "provider_failed",
        ),
    ),
)
def test_runtime_projector_closes_action_lifecycle_and_uses_stable_ids(
    event_type,
    event_reason,
    confirmed,
    expected_operation,
    expected_decision,
    expected_reason,
):
    request = RunRequest(
        operation=RunOperation.CONFIRM_PENDING_ACTION,
        user_id="private-action-owner",
        input_data={
            "pending_action_id": "private-action-id",
            "confirmed": confirmed,
            "thread_id": "private-action-thread",
        },
    )
    context = RunContext(
        run_id="private-action-run",
        runtime_thread_id="runtime-thread",
        trace_id="private-action-trace",
        request=request,
    )
    payload = {
        "action_id": "private-action-id",
        "action_type": "add_to_cart",
        "status": event_type.rsplit(".", maxsplit=1)[-1],
    }
    if event_reason is not None:
        payload["reason"] = event_reason
    result = RunResult(
        run_id=context.run_id,
        runtime_thread_id=context.runtime_thread_id,
        trace_id=context.trace_id,
        request_id=request.request_id,
        user_id=request.user_id,
        status=RunStatus.COMPLETED,
        completed_at=NOW,
        events=[
            AgentEvent(
                sequence=1,
                event_type=event_type,
                visibility=EventVisibility.CLIENT,
                trace_id=context.trace_id,
                timestamp=NOW,
                payload=payload,
            )
        ],
    )

    first = project_runtime_governance_records(context, result)
    replay = project_runtime_governance_records(context, result)

    assert len(first) == 1
    assert first[0].operation == expected_operation
    assert first[0].decision == expected_decision
    assert first[0].reason == expected_reason
    assert replay[0].audit_id == first[0].audit_id
    serialized = first[0].model_dump_json()
    assert "private-action-owner" not in serialized
    assert "private-action-id" not in serialized
    assert "private-action-thread" not in serialized
    assert "private-action-run" not in serialized
