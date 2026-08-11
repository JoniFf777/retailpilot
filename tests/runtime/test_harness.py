from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    AgentRun,
    AgentRunEvent,
    ConversationMessage,
    ConversationThread,
    GovernanceAuditRecord as GovernanceAuditRecordModel,
    IdempotencyRecord,
)
from app.governance import (
    GovernanceAuditEmissionMonitor,
    GovernanceAuditEmitter,
)
from app.runtime import (
    AgentAdapterError,
    AgentPlanAttemptEvent,
    AgentPlanAttemptLifecycle,
    AgentPlanRetryReason,
    AgentTransportError,
    AgentTransportFailureCode,
    DelegationBudgetError,
    DelegationTimeBudgetError,
    DelegationUsageBudgetError,
    ContextSlice,
    EventVisibility,
    MemoryItem,
    MemoryKind,
    MemoryScope,
    RunMode,
    RunOperation,
    RunRequest,
    RunStatus,
    RunUsage,
    ToolCallRecord,
    ToolCallStatus,
    ToolGatewayExecutionError,
    ToolSideEffectClass,
)
from app.runtime.harness import RuntimeExecutionError, ShopMindRuntimeHarness


def make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session


def test_harness_persists_legacy_chat_run():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
        input_text="recommend a keyboard",
        mode=RunMode.MULTI,
        idempotency_key="idem-1",
    )

    def fake_executor(context):
        return {
            "answer": "Try MX Keys.",
            "status": "completed",
            "tool_calls": ["search_products"],
            "debug": {
                "agent_steps": [
                    {"index": 1, "node": "supervisor", "event": "classified"}
                ]
            },
            "raw_result": {"final_response": "Try MX Keys."},
        }

    result = harness.run(request, fake_executor)

    assert result.status == RunStatus.COMPLETED
    assert result.answer == "Try MX Keys."
    assert result.tool_calls == ["search_products"]
    assert [event.event_type for event in result.events][-2:] == [
        "tool.call.completed",
        "run.completed",
    ]

    session = session_factory()
    try:
        runs = session.query(AgentRun).all()
        messages = (
            session.query(ConversationMessage)
            .order_by(ConversationMessage.sequence.asc())
            .all()
        )
    finally:
        session.close()

    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert runs[0].expires_at is not None
    assert [message.role for message in messages] == ["user", "assistant"]
    session = session_factory()
    try:
        thread = session.query(ConversationThread).one()
        idempotency = session.query(IdempotencyRecord).one()
    finally:
        session.close()
    assert thread.expires_at is not None
    assert all(message.expires_at is not None for message in messages)
    assert idempotency.expires_at is not None


def test_harness_persists_only_canonical_recommendation_and_fingerprints_it():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    recommendation = {
        "outcome": "no_match", "ranking_policy_version": "v1", "request_summary": "x",
        "structured_constraints": {}, "no_match_reason": "none",
    }
    result = harness.run(
        RunRequest(operation=RunOperation.CHAT, user_id="user-1", idempotency_key="rec-idem"),
        lambda context: {
            "answer": "none", "status": "completed", "recommendation": recommendation,
            "raw_result": {"secret": "raw"}, "recommendation_diagnostics": {"secret": "diagnostic"},
        },
    )
    assert result.output_data == {"recommendation": recommendation}
    session = session_factory()
    try:
        run = session.query(AgentRun).one()
        record = session.query(IdempotencyRecord).one()
    finally:
        session.close()
    assert run.result_json == {"recommendation": recommendation}
    assert record.response_fingerprint == harness._response_fingerprint(result)


def test_harness_fails_before_persistence_when_recommendation_contract_is_invalid():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    result = harness.run(
        RunRequest(operation=RunOperation.CHAT, user_id="user-1"),
        lambda context: {"answer": "bad", "status": "completed", "recommendation": {"outcome": "recommended"}},
        raise_on_error=False,
    )
    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "recommendation.validation_failed"


def test_harness_streams_and_persists_structured_attempt_event() -> None:
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    streamed = []
    payload = AgentPlanAttemptEvent(
        lifecycle=AgentPlanAttemptLifecycle.RETRY_SCHEDULED,
        step_id="read-rag-1",
        recipient="rag_agent",
        attempt=1,
        max_attempts=2,
        next_attempt=2,
        failure_code=AgentTransportFailureCode.UNAVAILABLE,
        error_code="agent.transport_unavailable",
        retriable=True,
        reason=AgentPlanRetryReason.TRANSPORT_RETRIABLE,
        usage=RunUsage(total_tokens=4, step_count=1),
    )

    def executor(context):
        context.emit_event(
            "plan.step.retry.scheduled",
            visibility=EventVisibility.INTERNAL,
            agent_name="rag_agent",
            payload={
                "plan_id": "plan-1",
                **payload.model_dump(mode="json", exclude_none=True),
            },
        )
        return {"answer": "ok", "status": "completed"}

    result = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="user-1",
            thread_id="thread-1",
        ),
        executor,
        event_sink=streamed.append,
    )
    attempt_event = next(
        event
        for event in result.events
        if event.event_type == "plan.step.retry.scheduled"
    )

    session = session_factory()
    try:
        persisted = (
            session.query(AgentRunEvent)
            .filter(AgentRunEvent.event_type == "plan.step.retry.scheduled")
            .one()
        )
    finally:
        session.close()

    assert attempt_event.sequence == streamed[attempt_event.sequence - 1].sequence
    assert attempt_event.payload["next_attempt"] == 2
    assert persisted.sequence == attempt_event.sequence
    assert persisted.payload_json == attempt_event.payload


def test_harness_persists_failed_executor_result_without_swallowing():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
        input_text="recommend a keyboard",
        mode=RunMode.MULTI,
    )

    def failing_executor(context):
        raise RuntimeError("boom")

    try:
        harness.run(request, failing_executor)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    session = session_factory()
    try:
        run = session.query(AgentRun).one()
    finally:
        session.close()

    assert run.status == "failed"
    assert run.error_json["message"] == "Runtime execution failed."
    assert "boom" not in str(run.error_json)


@pytest.mark.parametrize(
    ("exception", "expected_code", "expected_message", "expected_details"),
    [
        (
            RuntimeError("private provider endpoint: api.internal"),
            "runtime.executor_exception",
            "Runtime execution failed.",
            {"exception_type": "RuntimeError"},
        ),
        (
            AgentAdapterError("private malformed payload"),
            "agent.adapter_contract_failed",
            "Agent adapter contract validation failed.",
            {"exception_type": "AgentAdapterError"},
        ),
        (
            DelegationTimeBudgetError(
                budget_field="deadline_at",
                phase="reconciliation",
            ),
            "plan.deadline_exceeded",
            "Agent delegation time budget was exceeded.",
            {
                "budget_field": "deadline_at",
                "phase": "reconciliation",
                "exception_type": "DelegationTimeBudgetError",
            },
        ),
        (
            DelegationUsageBudgetError(
                budget_field="max_total_tokens",
                reason="missing",
            ),
            "plan.usage_budget_unavailable",
            "Agent delegation usage budget could not be satisfied.",
            {
                "budget_field": "max_total_tokens",
                "reason": "missing",
                "exception_type": "DelegationUsageBudgetError",
            },
        ),
        (
            DelegationBudgetError("private budget detail"),
            "plan.step_budget_exceeded",
            "Agent delegation budget was exceeded.",
            {"exception_type": "DelegationBudgetError"},
        ),
    ],
)
def test_harness_sanitizes_executor_and_adapter_failures(
    exception,
    expected_code,
    expected_message,
    expected_details,
):
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(operation=RunOperation.CHAT, user_id="user-1")

    result = harness.run(
        request,
        lambda context: (_ for _ in ()).throw(exception),
        raise_on_error=False,
    )

    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == expected_code
    assert result.error.message == expected_message
    assert result.error.details == expected_details
    serialized = str(result.model_dump(mode="json"))
    assert "api.internal" not in serialized
    assert "private malformed payload" not in serialized
    assert "private budget detail" not in serialized


def test_harness_persists_failed_tool_call_and_emits_audit_event():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
    )
    record = ToolCallRecord(
        tool_name="search_products",
        caller="product_agent",
        capability="search_products",
        status=ToolCallStatus.FAILED,
        requires_confirmation=True,
        result_metadata={"error_code": "tool.execution_failed"},
    )

    result = harness.run(
        request,
        lambda context: (_ for _ in ()).throw(ToolGatewayExecutionError(record)),
        raise_on_error=False,
    )

    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "tool.execution_failed"
    assert result.error.source == "tool"
    assert result.tool_calls == ["search_products"]
    assert result.tool_call_records == [record]
    assert [event.event_type for event in result.events][-2:] == [
        "tool.call.failed",
        "run.failed",
    ]
    assert result.events[-2].payload["requires_confirmation"] is True

    session = session_factory()
    try:
        run = session.query(AgentRun).one()
    finally:
        session.close()

    assert run.tool_call_records_json[0]["tool_call_id"] == record.tool_call_id


def test_harness_projects_tool_and_action_governance_audits_when_enabled():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    action_id = "private-governance-action"
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

    result = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="private-governance-owner",
            thread_id="private-governance-thread",
            metadata={"governance_audit_enabled": True},
        ),
        executor,
    )
    session = session_factory()
    try:
        rows = (
            session.query(GovernanceAuditRecordModel)
            .order_by(GovernanceAuditRecordModel.category.asc())
            .all()
        )
    finally:
        session.close()

    assert result.status == RunStatus.CONFIRMATION_REQUIRED
    assert [(row.category, row.operation) for row in rows] == [
        ("action", "action.prepare"),
        ("tool", "tool.invoke"),
    ]
    assert all(row.owner_fingerprint != "private-governance-owner" for row in rows)
    assert all(row.thread_fingerprint != "private-governance-thread" for row in rows)
    assert all(row.run_fingerprint != result.run_id for row in rows)
    assert all(row.resource_fingerprint != action_id for row in rows)
    assert action_id not in str([row.metadata_json for row in rows])


def test_harness_governance_storage_failure_does_not_change_business_result():
    session_factory = make_session_factory()
    monitor = GovernanceAuditEmissionMonitor(alert_failure_threshold=1)

    def unavailable_audit_session():
        raise RuntimeError("private governance storage failure")

    harness = ShopMindRuntimeHarness(
        session_factory=session_factory,
        governance_audit_emitter=GovernanceAuditEmitter(
            unavailable_audit_session,
            monitor=monitor,
        ),
    )
    result = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="user-1",
            metadata={"governance_audit_enabled": True},
        ),
        lambda context: {
            "answer": "business result remains valid",
            "status": "completed",
            "tool_calls": ["search_products"],
        },
    )
    session = session_factory()
    try:
        run = session.query(AgentRun).one()
        audit_count = session.query(GovernanceAuditRecordModel).count()
    finally:
        session.close()

    assert result.status == RunStatus.COMPLETED
    assert result.answer == "business result remains valid"
    assert run.status == "completed"
    assert audit_count == 0
    assert monitor.snapshot().failed_calls_total == 1
    assert monitor.snapshot().alert_active is True


def test_harness_projects_selected_memory_without_content_or_raw_identity():
    session_factory = make_session_factory()
    private_memory_content = "private memory content must not enter audit"

    class FixedContextManager:
        def build(self, context):
            return ContextSlice(
                items=[
                    MemoryItem(
                        memory_id="private-memory-id",
                        kind=MemoryKind.LONG_TERM,
                        scope=MemoryScope.USER,
                        content=private_memory_content,
                        user_id="private-memory-owner",
                        priority=10,
                        token_estimate=8,
                        provenance={"source": "runtime_memory_record"},
                    )
                ],
                rendered_text=private_memory_content,
                estimated_tokens=8,
            )

    harness = ShopMindRuntimeHarness(
        session_factory=session_factory,
        context_manager=FixedContextManager(),
    )
    result = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="private-memory-owner",
            metadata={"governance_audit_enabled": True},
        ),
        lambda context: {"answer": "ok", "status": "completed"},
    )
    session = session_factory()
    try:
        row = session.query(GovernanceAuditRecordModel).one()
    finally:
        session.close()

    assert result.status == RunStatus.COMPLETED
    assert row.category == "memory"
    assert row.operation == "memory.inspect"
    assert row.metadata_json == {
        "memory_kind": "long_term",
        "memory_scope": "user",
        "records_affected": 1,
    }
    serialized = str(row.metadata_json)
    assert private_memory_content not in serialized
    assert "private-memory-id" not in serialized
    assert "private-memory-owner" not in serialized


def test_harness_maps_tool_gateway_deadline_to_timeout_result():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
    )
    record = ToolCallRecord(
        tool_name="search_products",
        caller="product_agent",
        capability="search_products",
        status=ToolCallStatus.SKIPPED,
        result_metadata={"error_code": "tool.deadline_exceeded"},
    )

    result = harness.run(
        request,
        lambda context: (_ for _ in ()).throw(ToolGatewayExecutionError(record)),
        raise_on_error=False,
    )

    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "tool.deadline_exceeded"
    assert result.error.source == "timeout"
    assert result.events[-1].event_type == "run.timed_out"


def test_harness_retries_retriable_executor_and_records_attempt():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
        policy={"max_retries": 1},
    )
    attempts = 0

    def flaky_executor(context):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeExecutionError(
                "provider.unavailable",
                "temporary provider failure",
                retriable=True,
            )
        return {"answer": "ok", "status": "completed"}

    result = harness.run(request, flaky_executor)

    assert attempts == 2
    assert result.status == RunStatus.COMPLETED
    assert result.metadata["attempts"] == 2
    assert [event.event_type for event in result.events] == [
        "run.started",
        "memory.loaded",
        "context.built",
        "run.retrying",
        "run.completed",
    ]


def test_harness_retries_typed_transport_failure_without_private_fields():
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        policy={"max_retries": 1},
    )
    attempts = 0

    def flaky_transport_executor(context):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AgentTransportError(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=True,
                usage=RunUsage(total_tokens=5, cost_usd=0.01, step_count=1),
            )
        return {
            "answer": "ok",
            "status": "completed",
            "delegated_usage": [
                RunUsage(
                    total_tokens=7,
                    cost_usd=0.02,
                    step_count=1,
                ).model_dump(mode="python")
            ],
        }

    result = harness.run(request, flaky_transport_executor)

    assert attempts == 2
    assert result.status == RunStatus.COMPLETED
    assert result.metadata["attempts"] == 2
    assert result.usage.total_tokens == 12
    assert result.usage.cost_usd == pytest.approx(0.03)
    assert result.usage.step_count == 2
    retry_event = next(
        event for event in result.events if event.event_type == "run.retrying"
    )
    assert retry_event.payload["error_code"] == "agent.transport_unavailable"


def test_harness_applies_run_budget_to_failed_and_successful_attempt_usage():
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        policy={"max_retries": 1},
        budget={"max_total_tokens": 10},
    )
    attempts = 0

    def over_budget_retry(context):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AgentTransportError(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=True,
                usage=RunUsage(total_tokens=5, step_count=1),
            )
        return {
            "answer": "must not be accepted",
            "status": "completed",
            "delegated_usage": [
                RunUsage(total_tokens=7, step_count=1).model_dump(mode="python")
            ],
        }

    result = harness.run(request, over_budget_retry)

    assert attempts == 2
    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "runtime.usage_budget_exceeded"
    assert result.usage.total_tokens == 12
    assert result.usage.step_count == 2


def test_harness_maps_non_retriable_transport_timeout_to_timed_out_result():
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(operation=RunOperation.CHAT, user_id="user-1")

    result = harness.run(
        request,
        lambda context: (_ for _ in ()).throw(
            AgentTransportError(
                AgentTransportFailureCode.TIMEOUT,
                retriable=False,
                usage=RunUsage(total_tokens=2, step_count=1),
            )
        ),
        raise_on_error=False,
    )

    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "agent.transport_timeout"
    assert result.error.message == "Agent transport timed out."
    assert result.error.source == "timeout"
    assert result.error.retriable is False
    assert result.usage.total_tokens == 2
    assert result.usage.step_count == 1
    assert result.events[-1].event_type == "run.timed_out"


def test_harness_returns_timeout_without_invoking_executor():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
        deadline_at="2000-01-01T00:00:00Z",
    )
    invoked = False

    def executor(context):
        nonlocal invoked
        invoked = True
        return {"answer": "unexpected", "status": "completed"}

    result = harness.run(request, executor)

    assert invoked is False
    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "runtime.deadline_exceeded"
    assert result.error.source == "timeout"
    assert result.events[-1].event_type == "run.timed_out"


def test_harness_returns_cancelled_without_invoking_executor():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
    )
    invoked = False

    def executor(context):
        nonlocal invoked
        invoked = True
        return {"answer": "unexpected", "status": "completed"}

    result = harness.run(request, executor, cancellation_check=lambda: True)

    assert invoked is False
    assert result.status == RunStatus.CANCELLED
    assert result.error is not None
    assert result.error.code == "runtime.cancelled"
    assert result.events[-1].event_type == "run.cancelled"


def test_harness_enforces_tool_call_budget_as_failed_run():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
        budget={"max_tool_calls": 0},
    )

    result = harness.run(
        request,
        lambda context: {
            "answer": "blocked",
            "status": "completed",
            "tool_calls": ["search_products"],
        },
    )

    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "runtime.tool_call_budget_exceeded"
    assert result.events[-1].event_type == "run.failed"


def test_harness_aggregates_delegated_token_and_cost_usage():
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(operation=RunOperation.CHAT, user_id="user-1")

    result = harness.run(
        request,
        lambda context: {
            "answer": "ok",
            "status": "completed",
            "delegated_usage": [
                {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "cost_usd": 0.01,
                },
                {
                    "input_tokens": 20,
                    "output_tokens": 8,
                    "total_tokens": 28,
                    "cost_usd": 0.02,
                },
            ],
        },
    )

    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 13
    assert result.usage.total_tokens == 43
    assert result.usage.cost_usd == pytest.approx(0.03)
    assert "delegated_usage" not in result.output_data


def test_harness_fails_closed_when_configured_usage_is_unavailable():
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        budget={"max_total_tokens": 100},
    )

    result = harness.run(
        request,
        lambda context: {"answer": "unmetered", "status": "completed"},
    )

    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "runtime.usage_budget_unavailable"
    assert result.error.details == {"budget_field": "max_total_tokens"}


def test_harness_replays_completed_idempotency_key_without_reexecuting():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    calls = 0

    def executor(context):
        nonlocal calls
        calls += 1
        return {
            "answer": "Try MX Keys.",
            "status": "completed",
            "tool_calls": ["search_products"],
        }

    first = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="user-1",
            thread_id="thread-1",
            input_text="recommend a keyboard",
            idempotency_key="idem-replay",
        ),
        executor,
    )
    replay = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="user-1",
            thread_id="thread-1",
            input_text="recommend a keyboard",
            idempotency_key="idem-replay",
        ),
        executor,
    )

    assert calls == 1
    assert replay.run_id == first.run_id
    assert replay.answer == first.answer
    assert replay.tool_calls == ["search_products"]
    assert replay.metadata["idempotency_replayed"] is True
    assert [event.event_type for event in replay.events] == ["run.replayed"]

    session = session_factory()
    try:
        assert session.query(AgentRun).count() == 1
        assert session.query(ConversationMessage).count() == 2
    finally:
        session.close()


def test_harness_rejects_reused_idempotency_key_with_different_request():
    session_factory = make_session_factory()
    harness = ShopMindRuntimeHarness(session_factory=session_factory)
    calls = 0

    def executor(context):
        nonlocal calls
        calls += 1
        return {"answer": "ok", "status": "completed"}

    harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="user-1",
            thread_id="thread-1",
            input_text="first question",
            idempotency_key="idem-conflict",
        ),
        executor,
    )
    conflict = harness.run(
        RunRequest(
            operation=RunOperation.CHAT,
            user_id="user-1",
            thread_id="thread-1",
            input_text="different question",
            idempotency_key="idem-conflict",
        ),
        executor,
    )

    assert calls == 1
    assert conflict.status == RunStatus.FAILED
    assert conflict.error is not None
    assert conflict.error.code == "runtime.idempotency_key_conflict"
    assert [event.event_type for event in conflict.events] == ["run.rejected"]


def test_harness_binds_mid_execution_cancellation_probe() -> None:
    cancellation = Event()
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
    )

    def executor(context):
        assert context.refresh_cancellation() is False
        record = ToolCallRecord(
            tool_name="search_products",
            caller="product_agent",
            capability="search_products",
            status=ToolCallStatus.COMPLETED,
        )
        with context.locked_metadata() as metadata:
            metadata["tool_call_records"] = [record.model_dump(mode="json")]
        cancellation.set()
        assert context.refresh_cancellation() is True
        context.emit_event(
            "plan.execution.completed",
            payload={"status": "partial"},
        )
        return {"answer": "partial result", "status": "completed"}

    result = harness.run(
        request,
        executor,
        cancellation_check=cancellation.is_set,
    )

    assert result.status == RunStatus.CANCELLED
    assert result.answer == ""
    assert result.error is not None
    assert result.error.code == "runtime.cancelled"
    assert result.tool_calls == ["search_products"]
    assert result.tool_call_records[0].caller == "product_agent"
    assert result.usage.tool_call_count == 1
    assert [event.event_type for event in result.events][-3:] == [
        "plan.execution.completed",
        "tool.call.completed",
        "run.cancelled",
    ]


def test_harness_preserves_failed_record_for_partial_plan_result() -> None:
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(operation=RunOperation.CHAT, user_id="user-1")
    completed = ToolCallRecord(
        tool_name="search_products",
        caller="product_agent",
        status=ToolCallStatus.COMPLETED,
    )
    failed = ToolCallRecord(
        tool_name="search_policy_docs",
        caller="rag_agent",
        status=ToolCallStatus.FAILED,
        result_metadata={"error_code": "tool.execution_failed"},
    )

    result = harness.run(
        request,
        lambda context: {
            "answer": "partial answer",
            "status": "completed",
            "tool_calls": ["search_products"],
            "tool_call_records": [
                completed.model_dump(mode="json"),
                failed.model_dump(mode="json"),
            ],
        },
    )

    assert result.status == RunStatus.COMPLETED
    assert result.tool_calls == ["search_products"]
    assert result.tool_call_records == [completed, failed]
    assert result.usage.tool_call_count == 2
    assert [event.event_type for event in result.events][-3:] == [
        "tool.call.completed",
        "tool.call.failed",
        "run.completed",
    ]


def test_harness_allocates_concurrent_runtime_event_sequences_atomically() -> None:
    harness = ShopMindRuntimeHarness(session_factory=None)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
    )

    def executor(context):
        def emit(index: int) -> None:
            context.emit_event(
                "plan.step.started",
                payload={"step_index": index},
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(emit, range(12)))
        return {"answer": "ok", "status": "completed"}

    result = harness.run(request, executor)

    assert [event.sequence for event in result.events] == list(
        range(1, len(result.events) + 1)
    )
    plan_events = [
        event for event in result.events if event.event_type == "plan.step.started"
    ]
    assert len(plan_events) == 12
    assert {event.payload["step_index"] for event in plan_events} == set(range(12))
