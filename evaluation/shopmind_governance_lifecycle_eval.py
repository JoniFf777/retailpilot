"""Deterministic evaluation for identity and owner-data governance lifecycle."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

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
    GovernanceAuditEmissionMonitor,
    GovernanceAuditEmissionReason,
    GovernanceAuditEmissionResult,
    GovernanceAuditEmissionStatus,
    GovernanceAuditEmitter,
    OwnerDataService,
)
from app.repositories.runtime_memory import create_memory_record
from app.runtime import LocalRuntimeCoordinationBackend
from app.security import (
    AuditDecision,
    AuditOperation,
    AuditReason,
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    GovernanceAuditFactory,
    IdentityAuthenticationFailure,
    IdentityProviderName,
    build_identity_boundary,
    signed_identity_signature,
)


NOW = datetime(2026, 7, 26, 13, 0, tzinfo=timezone.utc)
SIGNED_NOW = 1_800_000_000
SIGNED_SECRET = "governance-eval-signing-secret-32-bytes-minimum"
GOVERNANCE_LIFECYCLE_SCENARIOS: tuple[str, ...] = (
    "signed_identity_replay",
    "owner_memory_lifecycle",
    "owner_full_deletion",
    "audit_monitor_recovery",
    "audit_persistence_idempotency",
)


def _store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _principal(owner_id: str):
    binding = build_identity_boundary(
        Settings(shopmind_identity_provider="development_payload")
    ).bind_user(owner_id, require_user=True)
    assert binding.principal is not None
    return binding.principal


def _seed_memory(
    session_factory,
    *,
    owner_id: str,
    memory_id: str,
    content: str,
) -> None:
    session = session_factory()
    try:
        create_memory_record(
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
    finally:
        session.close()


def _case_result(
    name: str,
    checks: Mapping[str, bool],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    failures = [check_id for check_id, passed in checks.items() if not passed]
    return {
        "name": name,
        "passed": not failures,
        "checks_passed": sum(checks.values()),
        "total_checks": len(checks),
        "failures": failures,
        "outcome": dict(outcome),
    }


def _emission_result(
    *,
    status: GovernanceAuditEmissionStatus,
    reason: GovernanceAuditEmissionReason,
    requested: int,
    persisted: int = 0,
    duplicates: int = 0,
) -> GovernanceAuditEmissionResult:
    return GovernanceAuditEmissionResult(
        status=status,
        reason=reason,
        requested_records=requested,
        persisted_records=persisted,
        duplicate_records=duplicates,
    )


def _signed_identity_case() -> dict[str, Any]:
    owner_id = "private-signed-governance-owner"
    nonce = "governance-nonce-0123456789"
    settings = Settings(
        shopmind_identity_provider="signed_header",
        shopmind_identity_signing_secret=SIGNED_SECRET,
        shopmind_identity_signature_max_age_seconds=60,
        shopmind_identity_signature_clock_skew_seconds=5,
    )
    signature = signed_identity_signature(
        secret=SIGNED_SECRET,
        subject_id=owner_id,
        issued_at=SIGNED_NOW,
        nonce=nonce,
    )
    credentials = {
        "trusted_subject": owner_id,
        "signed_issued_at": str(SIGNED_NOW),
        "signed_nonce": nonce,
        "signed_signature": signature,
    }
    backend = LocalRuntimeCoordinationBackend()
    boundary = build_identity_boundary(
        settings,
        replay_backend=backend,
        clock=lambda: SIGNED_NOW,
        **credentials,
    )
    binding = boundary.bind_user(owner_id, require_user=True)

    owner_mismatch_denied = False
    try:
        boundary.bind_user("private-different-owner", require_user=True)
    except AuthorizationDeniedError:
        owner_mismatch_denied = True

    replayed = build_identity_boundary(
        settings,
        replay_backend=backend,
        clock=lambda: SIGNED_NOW,
        **credentials,
    )
    replay_denied = False
    try:
        replayed.bind_user(owner_id, require_user=True)
    except AuthenticationRequiredError as exc:
        replay_denied = (
            exc.failure == IdentityAuthenticationFailure.REPLAYED
        )

    outcome = {
        "provider": str(boundary.provider_name),
        "scheme": boundary.authentication_scheme,
        "fingerprint_length": len(binding.principal.subject_fingerprint),
        "owner_mismatch_denied": owner_mismatch_denied,
        "replay_failure": str(replayed.authentication_failure),
    }
    serialized = json.dumps(outcome, sort_keys=True)
    checks = {
        "provider_selected": (
            boundary.provider_name == IdentityProviderName.SIGNED_HEADER
        ),
        "scheme_closed": (
            boundary.authentication_scheme == "ShopMindSignedHeader"
        ),
        "owner_bound": binding.effective_user_id == owner_id,
        "principal_typed": binding.principal.provider == "signed_header",
        "fingerprint_only": len(binding.principal.subject_fingerprint) == 64,
        "owner_mismatch_denied": owner_mismatch_denied,
        "replay_denied": replay_denied,
        "output_private_free": not any(
            value in serialized for value in (owner_id, nonce, signature, SIGNED_SECRET)
        ),
    }
    return _case_result("signed_identity_replay", checks, outcome)


def _owner_memory_case() -> dict[str, Any]:
    engine, session_factory = _store()
    owner_id = "private-memory-lifecycle-owner"
    other_owner = "private-memory-lifecycle-other"
    owner_memory_id = "private-owner-memory-id"
    other_memory_id = "private-other-memory-id"
    original_content = "private outdated preference"
    corrected_content = "private explicit corrected preference"
    try:
        _seed_memory(
            session_factory,
            owner_id=owner_id,
            memory_id=owner_memory_id,
            content=original_content,
        )
        _seed_memory(
            session_factory,
            owner_id=other_owner,
            memory_id=other_memory_id,
            content="private retained other-owner content",
        )
        service = OwnerDataService(
            session_factory,
            audit_emitter=GovernanceAuditEmitter(session_factory),
            clock=lambda: NOW,
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
            memory_id=owner_memory_id,
            content=corrected_content,
            audit_enabled=True,
        )
        cross_owner = service.correct_memory(
            owner_id=owner_id,
            principal=principal,
            memory_id=other_memory_id,
            content="private forbidden overwrite",
            audit_enabled=True,
        )
        deletion = service.delete_memory(
            owner_id=owner_id,
            principal=principal,
            memory_id=owner_memory_id,
            audit_enabled=True,
        )

        session = session_factory()
        try:
            deleted = session.get(MemoryRecord, owner_memory_id)
            retained = session.get(MemoryRecord, other_memory_id)
            audit_rows = list(
                session.scalars(
                    select(GovernanceAuditRecordModel).order_by(
                        GovernanceAuditRecordModel.occurred_at.asc()
                    )
                )
            )
        finally:
            session.close()

        trajectory = [
            (row.operation, row.decision)
            for row in audit_rows
        ]
        audit_projection = json.dumps(
            [
                {
                    "owner_fingerprint": row.owner_fingerprint,
                    "resource_fingerprint": row.resource_fingerprint,
                    "metadata": row.metadata_json,
                }
                for row in audit_rows
            ],
            sort_keys=True,
        )
        outcome = {
            "inspected": len(snapshot.memories),
            "corrected": correction is not None,
            "cross_owner_found": cross_owner is not None,
            "deleted": deletion is not None,
            "audit_trajectory": trajectory,
        }
        checks = {
            "inspection_exact_owner": (
                [item.memory_id for item in snapshot.memories]
                == [owner_memory_id]
            ),
            "correction_explicit": (
                correction is not None
                and correction.memory.content == corrected_content
                and correction.memory.content_json == {}
                and correction.memory.confidence == 1.0
            ),
            "cross_owner_blocked": cross_owner is None,
            "deletion_exact": (
                deletion is not None
                and deletion.memory_id == owner_memory_id
            ),
            "owner_memory_removed": deleted is None,
            "other_owner_retained": (
                retained is not None
                and retained.content_text == "private retained other-owner content"
            ),
            "audit_trajectory": trajectory == [
                ("memory.inspect", "succeeded"),
                ("memory.correct", "succeeded"),
                ("memory.correct", "not_found"),
                ("memory.delete", "succeeded"),
            ],
            "audit_fingerprints_only": all(
                row.owner_fingerprint is not None
                and len(row.owner_fingerprint) == 64
                and row.resource_fingerprint is not None
                and len(row.resource_fingerprint) == 64
                for row in audit_rows
            ),
            "audit_private_free": not any(
                value in audit_projection
                for value in (
                    owner_id,
                    other_owner,
                    original_content,
                    corrected_content,
                )
            ),
        }
        return _case_result("owner_memory_lifecycle", checks, outcome)
    finally:
        engine.dispose()


def _owner_full_deletion_case() -> dict[str, Any]:
    engine, session_factory = _store()
    owner_id = "private-full-delete-owner"
    other_owner = "private-full-delete-other"
    deletion_request_id = UUID("00000000-0000-0000-0000-000000000401")
    try:
        _seed_memory(
            session_factory,
            owner_id=owner_id,
            memory_id="private-full-delete-memory",
            content="private owner deletion content",
        )
        _seed_memory(
            session_factory,
            owner_id=other_owner,
            memory_id="private-retained-memory",
            content="private retained deletion content",
        )
        session = session_factory()
        try:
            session.add_all(
                [
                    UserPreference(
                        user_id=owner_id,
                        preference_type="style",
                        preference_value="private owner preference",
                    ),
                    UserPreference(
                        user_id=other_owner,
                        preference_type="style",
                        preference_value="private retained preference",
                    ),
                    PendingAction(
                        id="private-full-delete-action",
                        user_id=owner_id,
                        action_type="save_preference",
                        payload_json={"private": "payload"},
                        risk_class="medium",
                        preview_text="private action preview",
                        status="pending",
                        expires_at=NOW + timedelta(hours=1),
                        metadata_json={},
                    ),
                    CandidateContext(
                        user_id=owner_id,
                        thread_id="private-full-delete-thread",
                        product_ids=["TECH-KEY-010"],
                        quantity=1,
                        expires_at=NOW + timedelta(minutes=10),
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        service = OwnerDataService(
            session_factory,
            audit_emitter=GovernanceAuditEmitter(session_factory),
            clock=lambda: NOW,
        )
        principal = _principal(owner_id)
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

        session = session_factory()
        try:
            target_remaining = sum(
                len(list(session.scalars(statement)))
                for statement in (
                    select(MemoryRecord).where(MemoryRecord.user_id == owner_id),
                    select(UserPreference).where(UserPreference.user_id == owner_id),
                    select(PendingAction).where(PendingAction.user_id == owner_id),
                    select(CandidateContext).where(
                        CandidateContext.user_id == owner_id
                    ),
                )
            )
            other_memories = list(
                session.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.user_id == other_owner
                    )
                )
            )
            other_preferences = list(
                session.scalars(
                    select(UserPreference).where(
                        UserPreference.user_id == other_owner
                    )
                )
            )
            audit_rows = list(
                session.scalars(
                    select(GovernanceAuditRecordModel).order_by(
                        GovernanceAuditRecordModel.operation.asc(),
                        GovernanceAuditRecordModel.decision.asc(),
                    )
                )
            )
        finally:
            session.close()

        trajectory = [
            (row.operation, row.decision, row.reason)
            for row in audit_rows
        ]
        audit_projection = json.dumps(
            [
                {
                    "owner_fingerprint": row.owner_fingerprint,
                    "resource_fingerprint": row.resource_fingerprint,
                    "metadata": row.metadata_json,
                }
                for row in audit_rows
            ],
            sort_keys=True,
        )
        outcome = {
            "first_status": first.status,
            "records_affected": first.records_affected,
            "second_status": second.status,
            "target_remaining": target_remaining,
            "audit_trajectory": trajectory,
        }
        checks = {
            "first_deleted": first.status == "deleted",
            "exact_affected_count": first.records_affected == 4,
            "exact_category_counts": (
                first.counts.memory_records == 1
                and first.counts.preferences == 1
                and first.counts.pending_actions == 1
                and first.counts.candidate_contexts == 1
            ),
            "second_idempotent_by_effect": (
                second.status == "already_deleted"
                and second.records_affected == 0
            ),
            "request_identity_stable": (
                first.deletion_request_id
                == second.deletion_request_id
                == deletion_request_id
            ),
            "target_owner_removed": target_remaining == 0,
            "other_owner_retained": (
                len(other_memories) == 1
                and len(other_preferences) == 1
            ),
            "audit_retained": trajectory == [
                ("deletion.execute", "skipped", "already_deleted"),
                ("deletion.execute", "succeeded", "completed"),
                ("deletion.request", "requested", "user_requested"),
            ],
            "audit_private_free": not any(
                value in audit_projection
                for value in (
                    owner_id,
                    other_owner,
                    "private owner deletion content",
                    "private owner preference",
                    "private action preview",
                )
            ),
        }
        return _case_result("owner_full_deletion", checks, outcome)
    finally:
        engine.dispose()


def _audit_monitor_case() -> dict[str, Any]:
    monitor = GovernanceAuditEmissionMonitor(
        alert_failure_threshold=2,
        clock=lambda: NOW,
    )
    first_failure = monitor.observe(
        _emission_result(
            status=GovernanceAuditEmissionStatus.FAILED,
            reason=GovernanceAuditEmissionReason.STORAGE_UNAVAILABLE,
            requested=1,
        )
    )
    second_failure = monitor.observe(
        _emission_result(
            status=GovernanceAuditEmissionStatus.FAILED,
            reason=GovernanceAuditEmissionReason.STORAGE_UNAVAILABLE,
            requested=2,
        )
    )
    skipped = monitor.observe(
        _emission_result(
            status=GovernanceAuditEmissionStatus.SKIPPED,
            reason=GovernanceAuditEmissionReason.NO_RECORDS,
            requested=0,
        )
    )
    alerting = monitor.snapshot()
    recovered = monitor.observe(
        _emission_result(
            status=GovernanceAuditEmissionStatus.DUPLICATE,
            reason=GovernanceAuditEmissionReason.ALREADY_EXISTS,
            requested=3,
            duplicates=3,
        )
    )
    final = monitor.snapshot()
    outcome = {
        "schema_version": final.schema_version,
        "status": final.status,
        "alert_transitions": final.alert_transitions_total,
        "recovery_transitions": final.recovery_transitions_total,
        "failed_calls": final.failed_calls_total,
        "skipped_calls": final.skipped_calls_total,
    }
    serialized = json.dumps(outcome, sort_keys=True)
    checks = {
        "first_failure_warns": (
            not first_failure.alert_activated
            and first_failure.consecutive_failures == 1
        ),
        "threshold_activates_once": (
            second_failure.alert_activated
            and second_failure.consecutive_failures == 2
        ),
        "skip_does_not_recover": (
            not skipped.alert_recovered
            and alerting.alert_active
            and alerting.status == "alerting"
        ),
        "duplicate_recovers": recovered.alert_recovered,
        "final_state_healthy": (
            final.status == "healthy"
            and not final.alert_active
            and final.consecutive_failures == 0
        ),
        "closed_counters": (
            final.emission_calls_total == 4
            and final.storage_attempts_total == 3
            and final.requested_records_total == 6
            and final.duplicate_records_total == 3
            and final.failed_calls_total == 2
            and final.skipped_calls_total == 1
        ),
        "transition_counts": (
            final.alert_transitions_total == 1
            and final.recovery_transitions_total == 1
        ),
        "output_private_free": (
            "private" not in serialized
            and final.schema_version == "shopmind.governance-audit-monitor.v1"
        ),
    }
    return _case_result("audit_monitor_recovery", checks, outcome)


def _audit_persistence_case() -> dict[str, Any]:
    engine, session_factory = _store()
    owner_id = "private-audit-persistence-owner"
    action_id = "private-audit-persistence-action"
    try:
        monitor = GovernanceAuditEmissionMonitor(
            alert_failure_threshold=2,
            clock=lambda: NOW,
        )
        emitter = GovernanceAuditEmitter(session_factory, monitor=monitor)
        record = GovernanceAuditFactory(
            clock=lambda: NOW,
            audit_id_factory=lambda: UUID(
                "00000000-0000-0000-0000-000000000402"
            ),
        ).action_decision(
            operation=AuditOperation.ACTION_CONFIRM,
            decision=AuditDecision.SUCCEEDED,
            reason=AuditReason.COMPLETED,
            action_type="add_to_cart",
            action_id=action_id,
            principal=None,
            owner_id=owner_id,
        )
        first = emitter.emit(record)
        second = emitter.emit(record)

        session = session_factory()
        try:
            rows = list(session.scalars(select(GovernanceAuditRecordModel)))
        finally:
            session.close()
        snapshot = monitor.snapshot()
        row = rows[0] if rows else None
        projection = (
            json.dumps(
                {
                    "owner_fingerprint": row.owner_fingerprint,
                    "resource_fingerprint": row.resource_fingerprint,
                    "metadata": row.metadata_json,
                },
                sort_keys=True,
            )
            if row is not None
            else ""
        )
        outcome = {
            "first_status": str(first.status),
            "second_status": str(second.status),
            "stored_records": len(rows),
            "monitor_status": snapshot.status,
        }
        checks = {
            "first_persisted": (
                first.status == GovernanceAuditEmissionStatus.PERSISTED
                and first.persisted_records == 1
            ),
            "duplicate_classified": (
                second.status == GovernanceAuditEmissionStatus.DUPLICATE
                and second.duplicate_records == 1
            ),
            "immutable_single_row": len(rows) == 1,
            "owner_fingerprint": (
                row is not None
                and row.owner_fingerprint is not None
                and len(row.owner_fingerprint) == 64
            ),
            "resource_fingerprint": (
                row is not None
                and row.resource_fingerprint is not None
                and len(row.resource_fingerprint) == 64
            ),
            "metadata_allowlisted": (
                row is not None
                and row.metadata_json == {"action_type": "add_to_cart"}
            ),
            "monitor_counts_commits": (
                snapshot.emission_calls_total == 2
                and snapshot.storage_attempts_total == 2
                and snapshot.persisted_records_total == 1
                and snapshot.duplicate_records_total == 1
                and snapshot.status == "healthy"
            ),
            "projection_private_free": (
                owner_id not in projection
                and action_id not in projection
                and "private" not in json.dumps(outcome, sort_keys=True)
            ),
        }
        return _case_result(
            "audit_persistence_idempotency",
            checks,
            outcome,
        )
    finally:
        engine.dispose()


_SCENARIO_RUNNERS: Mapping[str, Callable[[], dict[str, Any]]] = {
    "signed_identity_replay": _signed_identity_case,
    "owner_memory_lifecycle": _owner_memory_case,
    "owner_full_deletion": _owner_full_deletion_case,
    "audit_monitor_recovery": _audit_monitor_case,
    "audit_persistence_idempotency": _audit_persistence_case,
}


def replay_governance_lifecycle_case(scenario: str) -> dict[str, Any]:
    try:
        runner = _SCENARIO_RUNNERS[scenario]
    except KeyError as exc:
        raise ValueError("Unknown governance lifecycle scenario.") from exc
    return runner()


def evaluate_governance_lifecycle(
    scenarios: Sequence[str] = GOVERNANCE_LIFECYCLE_SCENARIOS,
) -> dict[str, Any]:
    results = [
        replay_governance_lifecycle_case(scenario)
        for scenario in scenarios
    ]
    total_checks = sum(result["total_checks"] for result in results)
    passed_checks = sum(result["checks_passed"] for result in results)
    passed_cases = sum(result["passed"] for result in results)
    return {
        "schema_version": "shopmind.governance-lifecycle-eval.v1",
        "evaluation": "shopmind_governance_lifecycle",
        "total_cases": len(results),
        "passed_cases": passed_cases,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "failures": [
            result for result in results if not result["passed"]
        ],
        "results": results,
    }


def format_governance_lifecycle_summary(summary: Mapping[str, Any]) -> str:
    failures = ", ".join(
        result["name"] for result in summary["failures"]
    ) or "none"
    return "\n".join(
        (
            "# ShopMind Governance Lifecycle Evaluation",
            "",
            f"- cases: {summary['passed_cases']}/{summary['total_cases']}",
            f"- checks: {summary['passed_checks']}/{summary['total_checks']}",
            f"- failures: {failures}",
        )
    )


__all__ = [
    "GOVERNANCE_LIFECYCLE_SCENARIOS",
    "evaluate_governance_lifecycle",
    "format_governance_lifecycle_summary",
    "replay_governance_lifecycle_case",
]
