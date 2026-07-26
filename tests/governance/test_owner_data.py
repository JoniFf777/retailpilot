from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.settings import Settings
from app.db.base import Base
from app.db.models import (
    CandidateContext,
    GovernanceAuditRecord as GovernanceAuditRecordModel,
    MemoryRecord,
    PendingAction,
    UserPreference,
)
from app.governance import (
    GovernanceAuditEmitter,
    OwnerDataService,
    OwnerDataStorageError,
)
from app.repositories.runtime_memory import create_memory_record
from app.security import build_identity_boundary


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _principal(owner_id: str):
    binding = build_identity_boundary(Settings()).bind_user(
        owner_id,
        require_user=True,
    )
    assert binding.principal is not None
    return binding.principal


def _seed_memory(Session, *, owner_id: str, content: str, memory_id: str):
    session = Session()
    try:
        record = create_memory_record(
            session,
            memory_id=memory_id,
            memory_kind="long_term",
            scope="user",
            user_id=owner_id,
            content_text=content,
            content_json={"derived": True},
            provenance={"source": "model_inference"},
            priority=20,
            token_count=5,
            confidence=0.5,
        )
        session.commit()
        return record
    finally:
        session.close()


def test_owner_memory_inspection_correction_and_deletion_are_exact_scoped():
    Session = _session_factory()
    owner_id = "private-owner-lifecycle"
    other_owner = "private-other-owner"
    memory_id = "owner-memory"
    _seed_memory(
        Session,
        owner_id=owner_id,
        content="private outdated preference",
        memory_id=memory_id,
    )
    _seed_memory(
        Session,
        owner_id=other_owner,
        content="private other owner content",
        memory_id="other-memory",
    )
    service = OwnerDataService(
        Session,
        audit_emitter=GovernanceAuditEmitter(Session),
    )
    principal = _principal(owner_id)

    snapshot = service.inspect(
        owner_id=owner_id,
        principal=principal,
        memory_limit=10,
        audit_enabled=True,
    )
    correction = service.correct_memory(
        owner_id=owner_id,
        principal=principal,
        memory_id=memory_id,
        content="explicit corrected preference",
        audit_enabled=True,
    )
    denied_cross_owner = service.correct_memory(
        owner_id=owner_id,
        principal=principal,
        memory_id="other-memory",
        content="must not overwrite",
        audit_enabled=True,
    )
    deletion = service.delete_memory(
        owner_id=owner_id,
        principal=principal,
        memory_id=memory_id,
        audit_enabled=True,
    )

    assert [item.memory_id for item in snapshot.memories] == [memory_id]
    assert correction is not None
    assert correction.memory.content == "explicit corrected preference"
    assert correction.memory.content_json == {}
    assert correction.memory.confidence == 1.0
    assert denied_cross_owner is None
    assert deletion is not None
    assert deletion.memory_id == memory_id

    session = Session()
    try:
        deleted = session.get(MemoryRecord, memory_id)
        other = session.get(MemoryRecord, "other-memory")
        rows = list(
            session.scalars(
                select(GovernanceAuditRecordModel).order_by(
                    GovernanceAuditRecordModel.occurred_at.asc()
                )
            )
        )
    finally:
        session.close()

    assert deleted is None
    assert other is not None
    assert other.content_text == "private other owner content"
    assert [(row.operation, row.decision) for row in rows] == [
        ("memory.inspect", "succeeded"),
        ("memory.correct", "succeeded"),
        ("memory.correct", "not_found"),
        ("memory.delete", "succeeded"),
    ]
    serialized = "".join(
        str(
            {
                "owner": row.owner_fingerprint,
                "resource": row.resource_fingerprint,
                "metadata": row.metadata_json,
            }
        )
        for row in rows
    )
    assert owner_id not in serialized
    assert "private outdated preference" not in serialized
    assert "explicit corrected preference" not in serialized
def test_full_owner_deletion_retains_audit_and_is_idempotent_by_effect():
    Session = _session_factory()
    owner_id = "private-delete-owner"
    other_owner = "private-delete-other"
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    _seed_memory(
        Session,
        owner_id=owner_id,
        content="private owner memory",
        memory_id="delete-owner-memory",
    )
    _seed_memory(
        Session,
        owner_id=other_owner,
        content="private retained memory",
        memory_id="retained-memory",
    )
    session = Session()
    try:
        session.add_all(
            [
                UserPreference(
                    user_id=owner_id,
                    preference_type="style",
                    preference_value="private quiet preference",
                ),
                UserPreference(
                    user_id=other_owner,
                    preference_type="style",
                    preference_value="private retained preference",
                ),
                PendingAction(
                    id="private-delete-action",
                    user_id=owner_id,
                    action_type="save_preference",
                    payload_json={"private": "payload"},
                    risk_class="medium",
                    preview_text="private preview",
                    status="pending",
                    expires_at=now + timedelta(hours=1),
                    metadata_json={},
                ),
                CandidateContext(
                    user_id=owner_id,
                    thread_id="private-delete-thread",
                    product_ids=["TECH-KEY-010"],
                    quantity=1,
                    expires_at=now + timedelta(minutes=10),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    service = OwnerDataService(
        Session,
        audit_emitter=GovernanceAuditEmitter(Session),
        clock=lambda: now,
    )
    principal = _principal(owner_id)
    deletion_request_id = uuid4()
    first = service.delete_all(
        owner_id=owner_id,
        principal=principal,
        deletion_request_id=deletion_request_id,
        audit_enabled=True,
    )
    second = service.delete_all(
        owner_id=owner_id,
        principal=principal,
        deletion_request_id=deletion_request_id,
        audit_enabled=True,
    )

    assert first.status == "deleted"
    assert first.records_affected == 4
    assert first.counts.memory_records == 1
    assert first.counts.preferences == 1
    assert first.counts.pending_actions == 1
    assert first.counts.candidate_contexts == 1
    assert second.status == "already_deleted"
    assert second.records_affected == 0

    session = Session()
    try:
        retained_preferences = list(
            session.scalars(
                select(UserPreference).where(
                    UserPreference.user_id == other_owner
                )
            )
        )
        rows = list(
            session.scalars(
                select(GovernanceAuditRecordModel).order_by(
                    GovernanceAuditRecordModel.operation.asc(),
                    GovernanceAuditRecordModel.decision.asc(),
                )
            )
        )
    finally:
        session.close()

    assert len(retained_preferences) == 1
    assert [(row.operation, row.decision, row.reason) for row in rows] == [
        ("deletion.execute", "skipped", "already_deleted"),
        ("deletion.execute", "succeeded", "completed"),
        ("deletion.request", "requested", "user_requested"),
    ]
    serialized = "".join(str(row.metadata_json) for row in rows)
    assert owner_id not in serialized
    assert "private owner memory" not in serialized


def test_owner_deletion_storage_open_failure_emits_sanitized_failed_result():
    AuditSession = _session_factory()
    owner_id = "private-storage-owner"

    def unavailable_session():
        raise RuntimeError("private database URL and owner details")

    service = OwnerDataService(
        unavailable_session,
        audit_emitter=GovernanceAuditEmitter(AuditSession),
    )
    request_id = uuid4()

    with pytest.raises(
        OwnerDataStorageError,
        match="Owner data storage unavailable.",
    ):
        service.delete_all(
            owner_id=owner_id,
            principal=_principal(owner_id),
            deletion_request_id=request_id,
            audit_enabled=True,
        )

    session = AuditSession()
    try:
        rows = list(
            session.scalars(
                select(GovernanceAuditRecordModel).order_by(
                    GovernanceAuditRecordModel.occurred_at.asc()
                )
            )
        )
    finally:
        session.close()

    assert [(row.operation, row.decision) for row in rows] == [
        ("deletion.request", "requested"),
        ("deletion.execute", "failed"),
    ]
    assert owner_id not in "".join(str(row.metadata_json) for row in rows)


def test_owner_deletion_commit_failure_rolls_back_raw_rows_and_audits_failure():
    Session = _session_factory()
    owner_id = "private-rollback-owner"
    memory_id = "rollback-owner-memory"
    _seed_memory(
        Session,
        owner_id=owner_id,
        content="private rollback memory",
        memory_id=memory_id,
    )
    operation_session = Session()

    def fail_commit():
        raise RuntimeError("private commit failure")

    operation_session.commit = fail_commit
    service = OwnerDataService(
        lambda: operation_session,
        audit_emitter=GovernanceAuditEmitter(Session),
    )

    with pytest.raises(
        OwnerDataStorageError,
        match="Owner data storage unavailable.",
    ):
        service.delete_all(
            owner_id=owner_id,
            principal=_principal(owner_id),
            deletion_request_id=uuid4(),
            audit_enabled=True,
        )

    session = Session()
    try:
        retained = session.get(MemoryRecord, memory_id)
        rows = list(
            session.scalars(
                select(GovernanceAuditRecordModel).order_by(
                    GovernanceAuditRecordModel.occurred_at.asc()
                )
            )
        )
    finally:
        session.close()

    assert retained is not None
    assert retained.content_text == "private rollback memory"
    assert [(row.operation, row.decision) for row in rows] == [
        ("deletion.request", "requested"),
        ("deletion.execute", "failed"),
    ]
