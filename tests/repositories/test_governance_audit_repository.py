import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import GovernanceAuditRecord as GovernanceAuditRecordModel
from app.repositories.governance_audit import (
    DEFAULT_GOVERNANCE_AUDIT_RETENTION_DAYS,
    GovernanceAuditConflictError,
    append_governance_audit_record,
    get_owner_governance_audit_record,
    list_owner_governance_audit_records,
    prune_expired_governance_audit_records,
)
from app.security import (
    AuditDecision,
    AuditFingerprintNamespace,
    AuditOperation,
    AuditReason,
    GovernanceAuditFactory,
    governance_fingerprint,
)


BASE_TIME = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


def make_action_record(
    *,
    audit_id: str,
    occurred_at: datetime = BASE_TIME,
    owner_id: str = "private-owner-001",
    action_id: str = "private-action-001",
    operation: AuditOperation = AuditOperation.ACTION_CONFIRM,
):
    return GovernanceAuditFactory(
        clock=lambda: occurred_at,
        audit_id_factory=lambda: UUID(audit_id),
    ).action_decision(
        operation=operation,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.COMPLETED,
        action_type="add_to_cart",
        action_id=action_id,
        principal=None,
        owner_id=owner_id,
        thread_id="private-thread-001",
        run_id="private-run-001",
    )


def test_append_and_reload_preserves_typed_contract_and_default_retention():
    session = make_session()
    record = make_action_record(
        audit_id="00000000-0000-0000-0000-000000000101"
    )

    appended = append_governance_audit_record(
        session,
        record=record,
        now=BASE_TIME,
    )
    session.commit()
    loaded = get_owner_governance_audit_record(
        session,
        audit_id=str(record.audit_id),
        owner_fingerprint=record.owner_fingerprint,
        now=BASE_TIME,
    )

    assert loaded is not None
    assert loaded.record == record
    assert loaded.expires_at == BASE_TIME + timedelta(
        days=DEFAULT_GOVERNANCE_AUDIT_RETENTION_DAYS
    )
    assert appended.created_at == BASE_TIME


def test_owner_inspection_is_exact_bounded_filtered_and_newest_first():
    session = make_session()
    owner_id = "private-owner-001"
    records = [
        make_action_record(
            audit_id=f"00000000-0000-0000-0000-{suffix:012d}",
            occurred_at=BASE_TIME + timedelta(minutes=offset),
            owner_id=owner_id,
            action_id=f"private-action-{suffix}",
            operation=operation,
        )
        for suffix, offset, operation in (
            (102, 1, AuditOperation.ACTION_PREPARE),
            (103, 2, AuditOperation.ACTION_CONFIRM),
            (104, 3, AuditOperation.ACTION_CONFIRM),
        )
    ]
    for record in records:
        append_governance_audit_record(session, record=record, now=BASE_TIME)
    session.commit()

    result = list_owner_governance_audit_records(
        session,
        owner_fingerprint=records[0].owner_fingerprint,
        operation=AuditOperation.ACTION_CONFIRM,
        since=BASE_TIME + timedelta(minutes=1),
        before=BASE_TIME + timedelta(minutes=4),
        limit=1,
        now=BASE_TIME,
    )

    assert [item.record.audit_id for item in result] == [records[2].audit_id]
    with pytest.raises(ValueError, match="limit"):
        list_owner_governance_audit_records(
            session,
            owner_fingerprint=records[0].owner_fingerprint,
            limit=201,
        )


def test_cross_owner_lookup_never_returns_a_record():
    session = make_session()
    record = make_action_record(
        audit_id="00000000-0000-0000-0000-000000000105"
    )
    append_governance_audit_record(session, record=record, now=BASE_TIME)
    session.commit()
    other_owner = governance_fingerprint(
        AuditFingerprintNamespace.OWNER,
        "private-owner-002",
    )

    assert (
        get_owner_governance_audit_record(
            session,
            audit_id=str(record.audit_id),
            owner_fingerprint=other_owner,
            now=BASE_TIME,
        )
        is None
    )
    assert (
        list_owner_governance_audit_records(
            session,
            owner_fingerprint=other_owner,
            now=BASE_TIME,
        )
        == []
    )


def test_expired_records_are_hidden_then_pruned():
    session = make_session()
    expired = make_action_record(
        audit_id="00000000-0000-0000-0000-000000000106",
        occurred_at=BASE_TIME - timedelta(days=2),
    )
    active = make_action_record(
        audit_id="00000000-0000-0000-0000-000000000107",
    )
    append_governance_audit_record(
        session,
        record=expired,
        expires_at=BASE_TIME - timedelta(days=1),
        now=BASE_TIME - timedelta(days=2),
    )
    append_governance_audit_record(session, record=active, now=BASE_TIME)
    session.commit()

    visible = list_owner_governance_audit_records(
        session,
        owner_fingerprint=active.owner_fingerprint,
        now=BASE_TIME,
    )
    deleted = prune_expired_governance_audit_records(session, now=BASE_TIME)
    session.commit()

    assert [item.record.audit_id for item in visible] == [active.audit_id]
    assert deleted == 1
    assert session.get(GovernanceAuditRecordModel, str(expired.audit_id)) is None
    assert session.get(GovernanceAuditRecordModel, str(active.audit_id)) is not None


def test_append_is_immutable_and_rejects_duplicate_audit_id():
    session = make_session()
    record = make_action_record(
        audit_id="00000000-0000-0000-0000-000000000108"
    )
    append_governance_audit_record(session, record=record, now=BASE_TIME)

    with pytest.raises(GovernanceAuditConflictError, match="already exists"):
        append_governance_audit_record(session, record=record, now=BASE_TIME)


def test_persisted_row_never_contains_raw_identity_or_resource_values():
    session = make_session()
    record = make_action_record(
        audit_id="00000000-0000-0000-0000-000000000109",
        owner_id="private-owner-sensitive",
        action_id="private-action-sensitive",
    )
    append_governance_audit_record(session, record=record, now=BASE_TIME)
    session.commit()
    row = session.scalar(select(GovernanceAuditRecordModel))
    serialized = json.dumps(
        {
            column.name: getattr(row, column.name)
            for column in GovernanceAuditRecordModel.__table__.columns
            if column.name not in {"occurred_at", "expires_at", "created_at"}
        },
        sort_keys=True,
    )

    assert "private-owner-sensitive" not in serialized
    assert "private-action-sensitive" not in serialized
    assert "private-thread-001" not in serialized
    assert "private-run-001" not in serialized
