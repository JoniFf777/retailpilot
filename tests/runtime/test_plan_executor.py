from contextvars import ContextVar
from threading import Barrier, Event, Lock

import pytest

from app.runtime import (
    AgentExecutionPlan,
    AgentPlanAttemptEvent,
    AgentPlanExecutionMode,
    AgentPlanStep,
    AgentResult,
    AgentTaskStatus,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTransportError,
    AgentTransportFailureCode,
    BoundedPlanExecutor,
    DelegationTimeBudgetError,
    DelegationUsageBudgetError,
    MemoryReference,
    PlanExecutionError,
    RunUsage,
)


def _parallel_plan() -> AgentExecutionPlan:
    return AgentExecutionPlan(
        plan_id="plan-1",
        execution_mode=AgentPlanExecutionMode.BOUNDED_PARALLEL,
        max_parallelism=2,
        steps=[
            AgentPlanStep(
                step_id=f"step-{index}",
                recipient=recipient,
                intent="read",
                parallel_eligible=True,
            )
            for index, recipient in enumerate(
                ["product_agent", "rag_agent", "preference_agent"],
                start=1,
            )
        ],
    )


def test_parallel_executor_is_disabled_by_default() -> None:
    called = False

    def handler(step: AgentPlanStep) -> AgentResult:
        nonlocal called
        called = True
        return AgentResult(task_id=step.step_id, status=AgentTaskStatus.COMPLETED)

    with pytest.raises(PlanExecutionError, match="disabled"):
        BoundedPlanExecutor().execute(_parallel_plan(), handler)

    assert called is False


def test_enabled_executor_bounds_workers_and_fans_in_deterministically() -> None:
    barrier = Barrier(2)
    lock = Lock()
    active = 0
    max_active = 0

    def handler(step: AgentPlanStep) -> AgentResult:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            if step.step_id in {"step-1", "step-2"}:
                barrier.wait(timeout=2)
            return AgentResult(
                task_id=step.step_id,
                status=AgentTaskStatus.COMPLETED,
                output_data={"recipient": step.recipient},
                evidence_references=[
                    MemoryReference(
                        ref_id="shared-doc",
                        ref_type="document",
                        scope="operational",
                    )
                ],
                usage=RunUsage(total_tokens=10, cost_usd=0.02, step_count=1),
            )
        finally:
            with lock:
                active -= 1

    result = BoundedPlanExecutor(parallel_enabled=True).execute(
        _parallel_plan(),
        handler,
    )

    assert result.status == "completed"
    assert max_active == 2
    assert [step.step_id for step in result.step_results] == [
        "step-1",
        "step-2",
        "step-3",
    ]
    assert list(result.output_data) == ["step-1", "step-2", "step-3"]
    assert [reference.ref_id for reference in result.evidence_references] == [
        "shared-doc"
    ]
    assert result.usage.total_tokens == 30
    assert result.usage.cost_usd == pytest.approx(0.06)
    assert result.usage.step_count == 3


def test_executor_maps_usage_budget_failure_to_stable_error() -> None:
    plan = AgentExecutionPlan(
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="product_agent",
                intent="product_read",
            )
        ]
    )

    def handler(step: AgentPlanStep) -> AgentResult:
        raise DelegationUsageBudgetError(
            budget_field="max_total_tokens",
            reason="exceeded",
        )

    result = BoundedPlanExecutor().execute(plan, handler)

    assert result.status == "failed"
    assert result.errors[0].code == "plan.usage_budget_exceeded"
    assert result.errors[0].details == {
        "budget_field": "max_total_tokens",
        "reason": "exceeded",
        "exception_type": "DelegationUsageBudgetError",
    }


def test_executor_maps_time_budget_failure_to_timeout_error() -> None:
    plan = AgentExecutionPlan(
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="product_agent",
                intent="product_read",
            )
        ]
    )

    def handler(step: AgentPlanStep) -> AgentResult:
        raise DelegationTimeBudgetError(
            budget_field="deadline_at",
            phase="admission",
        )

    result = BoundedPlanExecutor().execute(plan, handler)

    assert result.status == "failed"
    assert result.errors[0].code == "plan.deadline_exceeded"
    assert result.errors[0].source == "timeout"
    assert result.errors[0].details == {
        "budget_field": "deadline_at",
        "phase": "admission",
        "exception_type": "DelegationTimeBudgetError",
    }


@pytest.mark.parametrize(
    ("failure_code", "expected_source"),
    [
        (AgentTransportFailureCode.UNAVAILABLE, "agent"),
        (AgentTransportFailureCode.TIMEOUT, "timeout"),
    ],
)
def test_executor_preserves_typed_transport_failure_classification(
    failure_code,
    expected_source,
) -> None:
    plan = AgentExecutionPlan(
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="product_agent",
                intent="product_read",
            )
        ]
    )

    def handler(step: AgentPlanStep) -> AgentResult:
        raise AgentTransportError(
            failure_code,
            retriable=True,
            usage=RunUsage(total_tokens=4, cost_usd=0.01, step_count=1),
        )

    result = BoundedPlanExecutor().execute(plan, handler)

    assert result.status == "failed"
    assert result.errors[0].code == failure_code.value
    assert result.errors[0].source == expected_source
    assert result.errors[0].retriable is True
    assert result.errors[0].details == {
        "exception_type": "AgentTransportError"
    }
    assert result.step_results[0].usage is not None
    assert result.usage.total_tokens == 4
    assert result.usage.cost_usd == pytest.approx(0.01)
    assert result.usage.step_count == 1


def test_executor_replays_allowlisted_transport_failure_with_same_step_identity() -> None:
    retry_policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )
    step = AgentPlanStep(
        step_id="step-1",
        recipient="product_agent",
        intent="product_read",
        retry_policy=retry_policy,
    )
    attempts: list[AgentPlanStep] = []

    def handler(current_step: AgentPlanStep) -> AgentResult:
        attempts.append(current_step)
        if len(attempts) == 1:
            raise AgentTransportError(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=True,
                usage=RunUsage(total_tokens=5, cost_usd=0.01, step_count=1),
            )
        return AgentResult(
            task_id=current_step.step_id,
            status=AgentTaskStatus.COMPLETED,
            usage=RunUsage(total_tokens=7, cost_usd=0.02, step_count=1),
        )

    result = BoundedPlanExecutor().execute(
        AgentExecutionPlan(steps=[step]),
        handler,
    )

    assert result.status == "completed"
    assert attempts == [step, step]
    assert result.step_results[0].attempt_count == 2
    assert result.usage.total_tokens == 12
    assert result.usage.cost_usd == pytest.approx(0.03)
    assert result.usage.step_count == 2


def test_executor_emits_ordered_retry_success_attempt_lifecycle() -> None:
    policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )
    step = AgentPlanStep(
        step_id="step-1",
        recipient="rag_agent",
        intent="document_retrieval",
        retry_policy=policy,
    )
    events: list[AgentPlanAttemptEvent] = []
    calls = 0

    def handler(current_step: AgentPlanStep) -> AgentResult:
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

    result = BoundedPlanExecutor().execute(
        AgentExecutionPlan(steps=[step]),
        handler,
        attempt_observer=events.append,
    )

    assert result.status == "completed"
    assert [event.lifecycle for event in events] == [
        "attempt.started",
        "attempt.failed",
        "retry.scheduled",
        "retry.started",
        "attempt.started",
        "attempt.completed",
        "retry.succeeded",
    ]
    assert [event.attempt for event in events] == [1, 1, 1, 2, 2, 2, 2]
    assert events[2].next_attempt == 2
    assert events[-1].reason == "success_after_retry"


def test_executor_emits_exhausted_and_non_retriable_decisions() -> None:
    policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )

    def run_failure(*, retriable: bool) -> list[AgentPlanAttemptEvent]:
        events: list[AgentPlanAttemptEvent] = []

        def handler(step: AgentPlanStep) -> AgentResult:
            raise AgentTransportError(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=retriable,
                usage=RunUsage(total_tokens=1, step_count=1),
            )

        BoundedPlanExecutor().execute(
            AgentExecutionPlan(
                steps=[
                    AgentPlanStep(
                        step_id="step-1",
                        recipient="rag_agent",
                        intent="document_retrieval",
                        retry_policy=policy,
                    )
                ]
            ),
            handler,
            attempt_observer=events.append,
        )
        return events

    exhausted = run_failure(retriable=True)
    non_retriable = run_failure(retriable=False)

    assert exhausted[-1].lifecycle == "attempt.exhausted"
    assert exhausted[-1].attempt == 2
    assert exhausted[-1].reason == "attempts_exhausted"
    assert non_retriable[-1].lifecycle == "retry.non_retriable"
    assert non_retriable[-1].attempt == 1
    assert non_retriable[-1].reason == "transport_non_retriable"


def test_executor_emits_retry_budget_blocked_decision() -> None:
    events: list[AgentPlanAttemptEvent] = []
    plan = AgentExecutionPlan(
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="rag_agent",
                intent="document_retrieval",
                retry_policy=AgentTaskRetryPolicy(
                    owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
                    max_attempts=2,
                    retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
                ),
            )
        ]
    )

    def blocked_handler(_step: AgentPlanStep) -> AgentResult:
        raise DelegationUsageBudgetError(
            budget_field="max_total_tokens",
            reason="exceeded",
        )

    result = BoundedPlanExecutor().execute(
        plan,
        blocked_handler,
        attempt_observer=events.append,
    )

    assert result.status == "failed"
    assert [event.lifecycle for event in events] == [
        "attempt.started",
        "attempt.failed",
        "retry.budget_blocked",
    ]
    assert events[-1].budget_field == "max_total_tokens"
    assert events[-1].budget_reason == "exceeded"
    assert events[-1].reason == "usage_budget"


@pytest.mark.parametrize(
    ("failure_code", "retriable"),
    [
        (AgentTransportFailureCode.PROTOCOL_ERROR, True),
        (AgentTransportFailureCode.UNAVAILABLE, False),
    ],
)
def test_executor_does_not_replay_unapproved_transport_failure(
    failure_code,
    retriable: bool,
) -> None:
    attempts = 0
    plan = AgentExecutionPlan(
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="product_agent",
                intent="product_read",
                retry_policy=AgentTaskRetryPolicy(
                    owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
                    max_attempts=3,
                    retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
                ),
            )
        ]
    )

    def handler(step: AgentPlanStep) -> AgentResult:
        nonlocal attempts
        attempts += 1
        raise AgentTransportError(
            failure_code,
            retriable=retriable,
            usage=RunUsage(total_tokens=3, step_count=1),
        )

    result = BoundedPlanExecutor().execute(plan, handler)

    assert attempts == 1
    assert result.status == "failed"
    assert result.step_results[0].attempt_count == 1
    assert result.usage.total_tokens == 3


def test_executor_bounds_replay_and_aggregates_all_failed_attempts() -> None:
    attempts = 0
    plan = AgentExecutionPlan(
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="rag_agent",
                intent="document_retrieval",
                retry_policy=AgentTaskRetryPolicy(
                    owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
                    max_attempts=3,
                    retryable_failure_codes={AgentTransportFailureCode.TIMEOUT},
                ),
            )
        ]
    )

    def handler(step: AgentPlanStep) -> AgentResult:
        nonlocal attempts
        attempts += 1
        raise AgentTransportError(
            AgentTransportFailureCode.TIMEOUT,
            retriable=True,
            usage=RunUsage(total_tokens=2, cost_usd=0.01, step_count=1),
        )

    result = BoundedPlanExecutor().execute(plan, handler)

    assert attempts == 3
    assert result.status == "failed"
    assert result.step_results[0].attempt_count == 3
    assert result.usage.total_tokens == 6
    assert result.usage.cost_usd == pytest.approx(0.03)
    assert result.usage.step_count == 3


def test_executor_checks_cancellation_before_replaying_transport_failure() -> None:
    cancellation = Event()
    attempts = 0
    plan = AgentExecutionPlan(
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="product_agent",
                intent="product_read",
                retry_policy=AgentTaskRetryPolicy(
                    owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
                    max_attempts=2,
                    retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
                ),
            )
        ]
    )

    def handler(step: AgentPlanStep) -> AgentResult:
        nonlocal attempts
        attempts += 1
        cancellation.set()
        raise AgentTransportError(
            AgentTransportFailureCode.UNAVAILABLE,
            retriable=True,
            usage=RunUsage(total_tokens=4, step_count=1),
        )

    events: list[AgentPlanAttemptEvent] = []
    result = BoundedPlanExecutor().execute(
        plan,
        handler,
        cancellation_check=cancellation.is_set,
        attempt_observer=events.append,
    )

    assert attempts == 1
    assert result.status == "failed"
    assert result.step_results[0].status == "cancelled"
    assert result.step_results[0].attempt_count == 1
    assert result.usage.total_tokens == 4
    assert [event.lifecycle for event in events][-2:] == [
        "retry.scheduled",
        "retry.cancelled",
    ]
    assert events[-1].reason == "cancellation_before_retry"


def test_parallel_executor_propagates_independent_execution_contexts() -> None:
    request_scope = ContextVar("request_scope", default="missing")
    token = request_scope.set("parent-run")

    def handler(step: AgentPlanStep) -> AgentResult:
        return AgentResult(
            task_id=step.step_id,
            status=AgentTaskStatus.COMPLETED,
            output_data={"request_scope": request_scope.get()},
        )

    try:
        result = BoundedPlanExecutor(parallel_enabled=True).execute(
            _parallel_plan(),
            handler,
        )
    finally:
        request_scope.reset(token)

    assert [
        output["request_scope"] for output in result.output_data.values()
    ] == ["parent-run", "parent-run", "parent-run"]


def test_parallel_executor_returns_partial_result_for_step_failure() -> None:
    def handler(step: AgentPlanStep) -> AgentResult:
        if step.recipient == "rag_agent":
            raise RuntimeError("rag unavailable")
        return AgentResult(
            task_id=step.step_id,
            status=AgentTaskStatus.COMPLETED,
            output_data={"recipient": step.recipient},
        )

    result = BoundedPlanExecutor(parallel_enabled=True).execute(
        _parallel_plan(),
        handler,
    )

    assert result.status == "partial"
    assert [step.status for step in result.step_results] == [
        "completed",
        "failed",
        "completed",
    ]
    assert result.errors[0].code == "plan.step_failed"
    assert result.errors[0].details["exception_type"] == "RuntimeError"


def test_sequential_executor_skips_failed_dependencies() -> None:
    plan = AgentExecutionPlan(
        plan_id="sequential-plan",
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="product_agent",
                intent="product_read",
            ),
            AgentPlanStep(
                step_id="step-2",
                recipient="rag_agent",
                intent="document_retrieval",
                depends_on=["step-1"],
            ),
        ],
    )

    def failing_handler(step: AgentPlanStep) -> AgentResult:
        raise RuntimeError("private detail")

    result = BoundedPlanExecutor().execute(plan, failing_handler)

    assert result.status == "failed"
    assert [step.status for step in result.step_results] == ["failed", "skipped"]
    assert result.errors[0].message == "Agent plan step execution failed."
    assert "private detail" not in result.errors[0].message
    assert result.errors[1].code == "plan.dependency_failed"


def test_parallel_executor_rejects_dependent_steps() -> None:
    plan = AgentExecutionPlan(
        execution_mode=AgentPlanExecutionMode.BOUNDED_PARALLEL,
        max_parallelism=2,
        steps=[
            AgentPlanStep(
                step_id="step-1",
                recipient="product_agent",
                intent="product_read",
            ),
            AgentPlanStep(
                step_id="step-2",
                recipient="rag_agent",
                intent="document_retrieval",
                depends_on=["step-1"],
            ),
        ],
    )

    with pytest.raises(PlanExecutionError, match="independent steps"):
        BoundedPlanExecutor(parallel_enabled=True).execute(
            plan,
            lambda step: AgentResult(
                task_id=step.step_id,
                status=AgentTaskStatus.COMPLETED,
            ),
        )


def test_parallel_executor_cancels_queued_steps_at_execution_checkpoint() -> None:
    cancellation = Event()
    handled: list[str] = []
    lifecycle: list[tuple[str, str]] = []

    def handler(step: AgentPlanStep) -> AgentResult:
        handled.append(step.step_id)
        cancellation.set()
        return AgentResult(
            task_id=step.step_id,
            status=AgentTaskStatus.COMPLETED,
        )

    result = BoundedPlanExecutor(parallel_enabled=True).execute(
        _parallel_plan().model_copy(update={"max_parallelism": 1}),
        handler,
        cancellation_check=cancellation.is_set,
        step_observer=lambda event, step, _result: lifecycle.append(
            (event, step.step_id)
        ),
    )

    assert result.status == "partial"
    assert handled == ["step-1"]
    assert [step.status for step in result.step_results] == [
        "completed",
        "cancelled",
        "cancelled",
    ]
    assert [error.code for error in result.errors] == [
        "plan.step_cancelled",
        "plan.step_cancelled",
    ]
    assert lifecycle == [
        ("started", "step-1"),
        ("completed", "step-1"),
        ("cancelled", "step-2"),
        ("cancelled", "step-3"),
    ]
