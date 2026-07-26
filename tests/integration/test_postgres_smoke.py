import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip(
        "set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL integration smoke tests",
        allow_module_level=True,
    )

from scripts.smoke_postgres import EXPECTED_ALEMBIC_VERSION, run_smoke

from app.core.settings import Settings, get_settings
from app.db.models import (
    AgentRun,
    AgentRunEvent,
    ConversationMessage,
    ConversationThread,
    GovernanceAuditRecord as GovernanceAuditRecordModel,
    IdempotencyRecord,
    MemoryRecord,
    PendingAction,
    UserPreference,
)
from app.db.session import SessionLocal
from app.governance import GovernanceAuditEmitter, OwnerDataService
from app.repositories.cart import (
    confirm_save_preference,
    prepare_save_preference,
    resolve_pending_action,
)
from app.repositories.governance_audit import (
    append_governance_audit_record,
    list_owner_governance_audit_records,
)
from app.repositories.runtime_memory import create_memory_record
from app.runtime import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentResult,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTaskStatus,
    AgentTransportError,
    AgentTransportFailureCode,
    BoundedPlanExecutor,
    EventVisibility,
    PersistedRunTrajectory,
    RunOperation,
    RunRequest,
    RunUsage,
    RuntimeTrajectoryRecorder,
    RuntimeTrajectoryReplayer,
    ShopMindRuntimeHarness,
    ToolCallRecord,
    ToolCallStatus,
    ToolSideEffectClass,
)
from app.security import (
    AuditDecision,
    AuditFingerprintNamespace,
    AuditOperation,
    AuditReason,
    GovernanceAuditFactory,
    build_identity_boundary,
    governance_fingerprint,
)


def test_postgres_smoke_against_configured_database():
    report = run_smoke()

    assert report.alembic_version == EXPECTED_ALEMBIC_VERSION
    assert report.table_counts["customers"] > 0
    assert report.table_counts["products"] > 0
    assert report.document_counts["product"] > 0
    assert report.document_counts["policy"] > 0


def test_postgres_governance_audit_is_owner_scoped_and_pii_safe():
    now = datetime.now(timezone.utc)
    owner_id = f"integration-audit-owner-{uuid4()}"
    action_id = f"integration-audit-action-{uuid4()}"
    record = GovernanceAuditFactory(clock=lambda: now).action_decision(
        operation=AuditOperation.ACTION_CONFIRM,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.COMPLETED,
        action_type="add_to_cart",
        action_id=action_id,
        principal=None,
        owner_id=owner_id,
    )
    session = SessionLocal()
    try:
        append_governance_audit_record(session, record=record, now=now)
        session.commit()
    finally:
        session.close()

    fresh_session = SessionLocal()
    try:
        loaded = list_owner_governance_audit_records(
            fresh_session,
            owner_fingerprint=record.owner_fingerprint,
            now=now,
        )
        row = fresh_session.get(GovernanceAuditRecordModel, str(record.audit_id))

        assert [item.record.audit_id for item in loaded] == [record.audit_id]
        assert row.owner_fingerprint != owner_id
        assert owner_id not in str(row.metadata_json)
        assert action_id not in str(row.metadata_json)
    finally:
        fresh_session.execute(
            delete(GovernanceAuditRecordModel).where(
                GovernanceAuditRecordModel.audit_id == str(record.audit_id)
            )
        )
        fresh_session.commit()
        fresh_session.close()


def _fresh_postgres_store():
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return engine, sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def _clear_runtime_user(session_factory, user_id: str) -> None:
    session = session_factory()
    try:
        session.execute(
            delete(GovernanceAuditRecordModel).where(
                GovernanceAuditRecordModel.owner_fingerprint
                == governance_fingerprint(
                    AuditFingerprintNamespace.OWNER,
                    user_id,
                )
            )
        )
        session.execute(delete(AgentRunEvent).where(AgentRunEvent.user_id == user_id))
        session.execute(
            delete(ConversationMessage).where(ConversationMessage.user_id == user_id)
        )
        session.execute(
            delete(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id)
        )
        session.execute(delete(MemoryRecord).where(MemoryRecord.user_id == user_id))
        session.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
        session.execute(
            delete(ConversationThread).where(ConversationThread.user_id == user_id)
        )
        session.execute(delete(PendingAction).where(PendingAction.user_id == user_id))
        session.execute(delete(UserPreference).where(UserPreference.user_id == user_id))
        session.commit()
    finally:
        session.close()


def test_postgres_harness_emits_tool_and_action_governance_batch() -> None:
    user_id = f"integration-governance-runtime-{uuid4()}"
    action_id = f"integration-governance-action-{uuid4()}"
    tool_record = ToolCallRecord(
        tool_name="prepare_add_to_cart",
        caller="write_handoff",
        capability="prepare_add_to_cart",
        status=ToolCallStatus.COMPLETED,
        side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
        requires_confirmation=True,
    )

    def executor(context):
        context.emit_event(
            "action.prepared",
            visibility=EventVisibility.CLIENT,
            agent_name="write_handoff",
            payload={
                "action_id": action_id,
                "action_type": "add_to_cart",
                "status": "pending",
                "risk_class": "high",
            },
        )
        return {
            "answer": "confirmation required",
            "status": "confirmation_required",
            "tool_calls": ["prepare_add_to_cart"],
            "tool_call_records": [tool_record.model_dump(mode="json")],
            "pending_action_id": action_id,
        }

    try:
        result = ShopMindRuntimeHarness(SessionLocal).run(
            RunRequest(
                operation=RunOperation.CHAT,
                user_id=user_id,
                thread_id=f"thread-{user_id}",
                metadata={"governance_audit_enabled": True},
            ),
            executor,
        )
        session = SessionLocal()
        try:
            audits = list_owner_governance_audit_records(
                session,
                owner_fingerprint=governance_fingerprint(
                    AuditFingerprintNamespace.OWNER,
                    user_id,
                ),
            )
        finally:
            session.close()

        assert result.status == "confirmation_required"
        assert {(item.record.category, item.record.operation) for item in audits} == {
            ("action", "action.prepare"),
            ("tool", "tool.invoke"),
        }
        serialized = "".join(item.record.model_dump_json() for item in audits)
        assert user_id not in serialized
        assert action_id not in serialized
    finally:
        _clear_runtime_user(SessionLocal, user_id)


def test_postgres_owner_data_lifecycle_deletes_raw_rows_but_retains_audit() -> None:
    user_id = f"integration-owner-data-{uuid4()}"
    memory_id = f"integration-owner-memory-{uuid4()}"
    request_id = uuid4()
    session = SessionLocal()
    try:
        create_memory_record(
            session,
            memory_id=memory_id,
            memory_kind="long_term",
            scope="user",
            user_id=user_id,
            content_text="private integration memory",
            content_json={"private": "derived"},
        )
        session.add(
            UserPreference(
                user_id=user_id,
                preference_type="style",
                preference_value="private integration preference",
            )
        )
        session.commit()
    finally:
        session.close()

    binding = build_identity_boundary(
        Settings(shopmind_identity_provider="development_payload")
    ).bind_user(
        user_id,
        require_user=True,
    )
    assert binding.principal is not None
    service = OwnerDataService(
        SessionLocal,
        audit_emitter=GovernanceAuditEmitter(SessionLocal),
    )
    try:
        inspected = service.inspect(
            owner_id=user_id,
            principal=binding.principal,
            memory_limit=10,
            audit_enabled=True,
        )
        corrected = service.correct_memory(
            owner_id=user_id,
            principal=binding.principal,
            memory_id=memory_id,
            content="private explicit correction",
            audit_enabled=True,
        )
        deleted = service.delete_all(
            owner_id=user_id,
            principal=binding.principal,
            deletion_request_id=request_id,
            audit_enabled=True,
        )

        fresh_session = SessionLocal()
        try:
            persisted_memory = fresh_session.get(MemoryRecord, memory_id)
            preferences = list(
                fresh_session.scalars(
                    select(UserPreference).where(
                        UserPreference.user_id == user_id
                    )
                )
            )
            audits = list_owner_governance_audit_records(
                fresh_session,
                owner_fingerprint=governance_fingerprint(
                    AuditFingerprintNamespace.OWNER,
                    user_id,
                ),
            )
        finally:
            fresh_session.close()

        assert inspected.counts.memory_records == 1
        assert corrected is not None
        assert corrected.memory.content == "private explicit correction"
        assert deleted.status == "deleted"
        assert deleted.records_affected == 2
        assert persisted_memory is None
        assert preferences == []
        assert {
            (item.record.category, item.record.operation)
            for item in audits
        } == {
            ("memory", "memory.inspect"),
            ("memory", "memory.correct"),
            ("deletion", "deletion.request"),
            ("deletion", "deletion.execute"),
        }
        serialized = "".join(
            item.record.model_dump_json() for item in audits
        )
        assert user_id not in serialized
        assert "private integration memory" not in serialized
        assert "private explicit correction" not in serialized
    finally:
        _clear_runtime_user(SessionLocal, user_id)


def test_postgres_runtime_retry_trajectory_replays_after_fresh_store() -> None:
    user_id = f"integration-retry-{uuid4()}"
    fresh_engine, fresh_factory = _fresh_postgres_store()
    calls = 0
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id=user_id,
        thread_id=f"thread-{user_id}",
        input_text="private integration fault payload",
        idempotency_key=f"key-{user_id}",
    )
    retry_policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )

    def executor(context):
        nonlocal calls
        step = AgentPlanStep(
            step_id="rag-step",
            recipient="rag_agent",
            intent="document_retrieval",
            retry_policy=retry_policy,
        )

        def handler(current_step):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise AgentTransportError(
                    AgentTransportFailureCode.UNAVAILABLE,
                    retriable=True,
                    usage=RunUsage(total_tokens=2, step_count=1),
                )
            return AgentResult(
                task_id=current_step.step_id,
                status=AgentTaskStatus.COMPLETED,
                usage=RunUsage(total_tokens=3, step_count=1),
            )

        def observe(event):
            context.emit_event(
                f"plan.step.{event.lifecycle}",
                agent_name=event.recipient,
                payload=event.model_dump(mode="json"),
            )

        plan_result = BoundedPlanExecutor().execute(
            AgentExecutionPlan(run_id=context.run_id, steps=[step]),
            handler,
            attempt_observer=observe,
        )
        return {
            "answer": "completed",
            "status": "completed",
            "delegated_usage": [plan_result.usage.model_dump(mode="json")],
        }

    try:
        first = ShopMindRuntimeHarness(SessionLocal).run(request, executor)
        recorded = RuntimeTrajectoryRecorder(SessionLocal).record(
            run_id=first.run_id,
            user_id=user_id,
            runtime_thread_id=first.runtime_thread_id,
        )
        wire_snapshot = PersistedRunTrajectory.model_validate_json(
            recorded.model_dump_json()
        )
        replay = RuntimeTrajectoryReplayer(fresh_factory).replay(wire_snapshot)
        second = ShopMindRuntimeHarness(fresh_factory).run(request, executor)

        assert replay.matches is True
        assert replay.recorded_fingerprint == replay.observed_fingerprint
        assert second.metadata["idempotency_replayed"] is True
        assert second.run_id == first.run_id
        assert calls == 2
        event_types = [event.event_type for event in recorded.events]
        assert "plan.step.retry.scheduled" in event_types
        assert "plan.step.retry.succeeded" in event_types
        assert "private integration fault payload" not in recorded.model_dump_json()
    finally:
        _clear_runtime_user(fresh_factory, user_id)
        fresh_engine.dispose()


def test_postgres_action_resume_trajectory_replays_after_fresh_store() -> None:
    user_id = f"integration-action-{uuid4()}"
    client_thread_id = f"thread-{user_id}"
    fresh_engine, fresh_factory = _fresh_postgres_store()
    session = SessionLocal()
    try:
        prepared = prepare_save_preference(
            session,
            user_id=user_id,
            preference_type="style",
            preference_value="quiet keyboard",
            thread_id=client_thread_id,
        )
        action_id = prepared["pending_action_id"]
        session.commit()
    finally:
        session.close()

    def executor(context):
        operation_session = fresh_factory()
        try:
            resolved = resolve_pending_action(
                operation_session, action_id, user_id, client_thread_id
            )
            assert resolved["status"] == "resolved"
            context.emit_event(
                "action.resumed",
                payload={"action_id": action_id, "action_type": "save_preference"},
            )
            confirmed = confirm_save_preference(
                operation_session, action_id, user_id, client_thread_id
            )
            operation_session.commit()
        finally:
            operation_session.close()
        context.emit_event(
            "action.confirmed",
            payload={"action_id": action_id, "action_type": "save_preference"},
        )
        return {
            "answer": confirmed["message"],
            "status": "completed",
            "pending_action_id": action_id,
        }

    try:
        result = ShopMindRuntimeHarness(fresh_factory).run(
            RunRequest(
                operation=RunOperation.CONFIRM_PENDING_ACTION,
                user_id=user_id,
                thread_id=client_thread_id,
                input_data={"pending_action_id": action_id, "confirmed": True},
            ),
            executor,
        )
        recorded = RuntimeTrajectoryRecorder(fresh_factory).record(
            run_id=result.run_id,
            user_id=user_id,
            runtime_thread_id=result.runtime_thread_id,
        )
        replay = RuntimeTrajectoryReplayer(SessionLocal).replay(recorded)
        session = fresh_factory()
        try:
            action_status = session.get(PendingAction, action_id).status
            preferences = session.scalars(
                select(UserPreference).where(UserPreference.user_id == user_id)
            ).all()
        finally:
            session.close()

        assert replay.matches is True
        assert result.pending_action_id == action_id
        assert action_status == "confirmed"
        assert len(preferences) == 1
        assert [
            event.event_type
            for event in recorded.events
            if event.event_type.startswith("action.")
        ] == ["action.resumed", "action.confirmed"]
    finally:
        _clear_runtime_user(fresh_factory, user_id)
        fresh_engine.dispose()
