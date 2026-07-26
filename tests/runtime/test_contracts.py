from threading import Event

import pytest

from app.runtime import (
    AgentEvent,
    AgentExecutionPlan,
    AgentPlanAttemptEvent,
    AgentPlanAttemptLifecycle,
    AgentPlanExecutionMode,
    AgentPlanStep,
    AgentPlanRetryReason,
    ErrorSource,
    EvidenceConflict,
    EvidenceConflictType,
    EvidenceResolution,
    EvidenceResolutionAction,
    EventVisibility,
    RunUsage,
    RunContext,
    RunError,
    RunOperation,
    RunRequest,
    RunResult,
    RunStatus,
    ToolCallRecord,
    ToolCallStatus,
    ToolSideEffectClass,
)


def test_run_request_and_context_generate_runtime_ids():
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="user-1",
        thread_id="thread-1",
        input_text="recommend a keyboard",
    )

    context = RunContext(request=request)

    assert context.run_id
    assert context.runtime_thread_id
    assert context.trace_id
    assert context.user_id == "user-1"
    assert context.client_thread_id == "thread-1"


def test_run_context_local_controls_are_not_serialized() -> None:
    cancellation = Event()
    emitted: list[dict] = []
    context = RunContext(request=RunRequest(operation=RunOperation.CHAT))
    context.bind_cancellation_check(cancellation.is_set)
    context.bind_event_emitter(lambda **event: emitted.append(event))

    cancellation.set()
    assert context.refresh_cancellation() is True
    context.emit_event("plan.step.cancelled", payload={"step_id": "read-2"})

    payload = context.model_dump(mode="json")
    assert payload["cancellation_requested"] is True
    assert "_cancellation_check" not in payload
    assert "_event_emitter" not in payload
    assert emitted[0]["event_type"] == "plan.step.cancelled"


def test_plan_attempt_event_payload_is_frozen_and_json_persistable() -> None:
    payload = AgentPlanAttemptEvent(
        lifecycle=AgentPlanAttemptLifecycle.RETRY_SCHEDULED,
        step_id="read-rag-1",
        recipient="rag_agent",
        attempt=1,
        max_attempts=2,
        next_attempt=2,
        failure_code="agent.transport_unavailable",
        error_code="agent.transport_unavailable",
        retriable=True,
        reason=AgentPlanRetryReason.TRANSPORT_RETRIABLE,
        usage=RunUsage(total_tokens=4, step_count=1),
    )

    serialized = payload.model_dump(mode="json", exclude_none=True)

    assert serialized["lifecycle"] == "retry.scheduled"
    assert serialized["failure_code"] == "agent.transport_unavailable"
    assert serialized["next_attempt"] == 2
    assert serialized["usage"]["step_count"] == 1
    with pytest.raises(Exception):
        payload.attempt = 2


def test_run_result_keeps_structured_events_tool_records_and_error():
    tool_record = ToolCallRecord(
        tool_name="prepare_add_to_cart",
        caller="write_handoff",
        status=ToolCallStatus.COMPLETED,
        side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
    )
    event = AgentEvent(
        sequence=1,
        event_type="run.started",
        agent_name="runtime_harness",
        visibility=EventVisibility.CLIENT,
        payload={"operation": "chat"},
        tool_call_id=tool_record.tool_call_id,
    )
    error = RunError(
        code="runtime.timeout",
        message="deadline exceeded",
        source=ErrorSource.TIMEOUT,
        retriable=True,
        event_sequence=3,
    )

    result = RunResult(
        run_id="run-1",
        runtime_thread_id="runtime-thread-1",
        trace_id="trace-1",
        request_id="request-1",
        user_id="user-1",
        client_thread_id="thread-1",
        status=RunStatus.FAILED,
        answer="",
        tool_calls=["prepare_add_to_cart"],
        tool_call_records=[tool_record],
        events=[event],
        error=error,
    )

    assert result.status == "failed"
    assert result.tool_call_records[0].side_effect_class == "sensitive_write"
    assert result.events[0].event_type == "run.started"
    assert result.error is not None
    assert result.error.source == "timeout"


def test_evidence_conflict_and_resolution_are_typed() -> None:
    conflict = EvidenceConflict(
        conflict_type=EvidenceConflictType.PRODUCT_SCOPE_MISMATCH,
        product_ids=["TECH-KEY-001"],
        evidence_product_ids=["TECH-MON-001"],
        evidence_reference_ids=["42"],
    )
    resolution = EvidenceResolution(
        action=EvidenceResolutionAction.EXCLUDE_EVIDENCE_AND_REQUEST_CLARIFICATION,
        excluded_summaries=["rag_summary"],
        followup_reason=EvidenceConflictType.PRODUCT_SCOPE_MISMATCH,
    )

    assert conflict.conflict_type == "product_evidence_scope_mismatch"
    assert resolution.action == "exclude_evidence_and_request_clarification"
    assert resolution.requires_followup is True


def test_agent_execution_plan_rejects_invalid_parallelism_and_dependencies() -> None:
    with pytest.raises(ValueError, match="max_parallelism 1"):
        AgentExecutionPlan(
            execution_mode=AgentPlanExecutionMode.SEQUENTIAL,
            max_parallelism=2,
        )

    with pytest.raises(ValueError, match="known steps"):
        AgentExecutionPlan(
            steps=[
                AgentPlanStep(
                    step_id="read-1",
                    recipient="rag_agent",
                    intent="document_retrieval",
                    depends_on=["missing-step"],
                )
            ]
        )

    with pytest.raises(ValueError, match="acyclic"):
        AgentExecutionPlan(
            steps=[
                AgentPlanStep(
                    step_id="read-1",
                    recipient="product_agent",
                    intent="product_read",
                    depends_on=["read-2"],
                ),
                AgentPlanStep(
                    step_id="read-2",
                    recipient="rag_agent",
                    intent="document_retrieval",
                    depends_on=["read-1"],
                ),
            ]
        )
