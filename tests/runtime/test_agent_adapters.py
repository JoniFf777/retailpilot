from datetime import datetime, timedelta, timezone

import pytest

from app.runtime import (
    AgentAdapterError,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentTransportError,
    AgentTransportFailureCode,
    DelegationBudgetError,
    DelegationBudgetGuard,
    DelegationTimeBudgetError,
    DelegationUsageBudgetError,
    InProcessAgentAdapter,
    PolicyEnforcedAgentAdapter,
    RunBudget,
    RunUsage,
)


def make_task(*, recipient: str = "product_agent") -> AgentTask:
    return AgentTask(
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
        sender="supervisor",
        recipient=recipient,
        intent="product_search",
        input_data={"query": "keyboard"},
        trace_id="trace-1",
    )


def make_policy_adapter(*, guard, handler) -> PolicyEnforcedAgentAdapter:
    return PolicyEnforcedAgentAdapter(
        adapter=InProcessAgentAdapter(
            agent_name="product_agent",
            handler=handler,
        ),
        delegation_guard=guard,
    )


def test_in_process_adapter_returns_typed_matching_result() -> None:
    task = make_task()
    adapter = InProcessAgentAdapter(
        agent_name="product_agent",
        handler=lambda received_task: AgentResult(
            task_id=received_task.task_id,
            status=AgentTaskStatus.COMPLETED,
            output_data={"products": ["TECH-KEY-001"]},
            child_trace_ids=["trace-product-1"],
        ),
    )

    result = adapter.invoke(task)

    assert result.task_id == task.task_id
    assert result.output_data["products"] == ["TECH-KEY-001"]
    assert result.child_trace_ids == ["trace-product-1"]


def test_in_process_adapter_rejects_wrong_recipient_and_result_task_id() -> None:
    adapter = InProcessAgentAdapter(
        agent_name="product_agent",
        handler=lambda task: AgentResult(
            task_id="wrong-task",
            status=AgentTaskStatus.COMPLETED,
        ),
    )

    with pytest.raises(AgentAdapterError, match="recipient"):
        adapter.invoke(make_task(recipient="rag_agent"))
    with pytest.raises(AgentAdapterError, match="task_id"):
        adapter.invoke(make_task())


def test_failed_agent_result_requires_structured_error() -> None:
    with pytest.raises(ValueError, match="structured error"):
        AgentResult(task_id="task-1", status=AgentTaskStatus.FAILED)


def test_agent_tasks_require_consistent_parent_and_delegation_depth() -> None:
    with pytest.raises(ValueError, match="Root Agent tasks"):
        AgentTask(
            run_id="run-1",
            sender="supervisor",
            recipient="product_agent",
            intent="product_search",
            trace_id="trace-1",
            delegation_depth=1,
        )


def test_delegation_guard_enforces_depth_and_child_task_limits() -> None:
    guard = DelegationBudgetGuard()
    adapter = make_policy_adapter(
        guard=guard,
        handler=lambda task: AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
        ),
    )
    child_budget = RunBudget(max_delegation_depth=1, max_child_tasks=1)
    first_child = AgentTask(
        task_id="child-1",
        parent_task_id="parent-1",
        delegation_depth=1,
        run_id="run-1",
        sender="supervisor",
        recipient="product_agent",
        intent="product_search",
        trace_id="trace-1",
        budget=child_budget,
    )
    adapter.invoke(first_child)

    with pytest.raises(DelegationBudgetError, match="child task limit"):
        adapter.invoke(first_child.model_copy(update={"task_id": "child-2"}))
    with pytest.raises(DelegationBudgetError, match="delegation depth"):
        adapter.invoke(
            first_child.model_copy(
                update={"task_id": "child-3", "delegation_depth": 2}
            )
        )


def test_delegation_guard_enforces_trusted_run_steps_with_scoped_idempotency() -> None:
    handled: list[tuple[str, str]] = []
    guard = DelegationBudgetGuard(trusted_budget=RunBudget(max_steps=1))
    adapter = make_policy_adapter(
        guard=guard,
        handler=lambda task: (
            handled.append((task.run_id, task.task_id))
            or AgentResult(
                task_id=task.task_id,
                status=AgentTaskStatus.COMPLETED,
            )
        ),
    )
    first = make_task().model_copy(
        update={
            "task_id": "plan-step-1",
            "budget": RunBudget(max_steps=100),
        }
    )

    adapter.invoke(first)
    adapter.invoke(first)

    with pytest.raises(DelegationBudgetError, match="task step limit"):
        adapter.invoke(first.model_copy(update={"task_id": "plan-step-2"}))

    adapter.invoke(first.model_copy(update={"run_id": "run-2"}))

    assert handled == [
        ("run-1", "plan-step-1"),
        ("run-1", "plan-step-1"),
        ("run-2", "plan-step-1"),
    ]


def test_delegation_guard_aggregates_usage_and_enforces_trusted_ceiling() -> None:
    guard = DelegationBudgetGuard(
        trusted_budget=RunBudget(max_total_tokens=50, max_cost_usd=0.25)
    )
    adapter = make_policy_adapter(
        guard=guard,
        handler=lambda task: AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
            usage=RunUsage(
                input_tokens=15,
                output_tokens=10,
                total_tokens=25,
                cost_usd=0.1,
                step_count=1,
            ),
        ),
    )
    first = make_task().model_copy(
        update={"task_id": "step-1", "budget": RunBudget(max_total_tokens=500)}
    )

    adapter.invoke(first)
    adapter.invoke(first)

    usage = guard.usage_snapshot("run-1")
    assert usage.input_tokens == 30
    assert usage.output_tokens == 20
    assert usage.total_tokens == 50
    assert usage.cost_usd == pytest.approx(0.2)
    assert usage.step_count == 2

    with pytest.raises(DelegationUsageBudgetError) as captured:
        adapter.invoke(first.model_copy(update={"task_id": "step-2"}))

    assert captured.value.error_code == "plan.usage_budget_exceeded"
    assert captured.value.budget_field == "max_total_tokens"
    assert captured.value.reason == "exceeded"
    adapter.invoke(
        first.model_copy(update={"run_id": "run-2", "task_id": "step-1"})
    )


def test_policy_adapter_accounts_failed_attempt_before_same_task_success() -> None:
    attempts = 0
    guard = DelegationBudgetGuard(trusted_budget=RunBudget(max_steps=1))

    def flaky_handler(task: AgentTask) -> AgentResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AgentTransportError(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=True,
                usage=RunUsage(total_tokens=5, cost_usd=0.01, step_count=1),
            )
        return AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
            usage=RunUsage(total_tokens=7, cost_usd=0.02, step_count=1),
        )

    adapter = make_policy_adapter(guard=guard, handler=flaky_handler)
    task = make_task().model_copy(update={"task_id": "retryable-step"})

    with pytest.raises(AgentTransportError):
        adapter.invoke(task)
    result = adapter.invoke(task)

    assert result.status == "completed"
    usage = guard.usage_snapshot("run-1")
    assert usage.total_tokens == 12
    assert usage.cost_usd == pytest.approx(0.03)
    assert usage.step_count == 2


@pytest.mark.parametrize(
    ("budget", "usage", "reason"),
    [
        (
            RunBudget(max_total_tokens=4),
            RunUsage(total_tokens=5, step_count=1),
            "exceeded",
        ),
        (
            RunBudget(max_prompt_tokens=100),
            RunUsage(step_count=1),
            "missing",
        ),
    ],
)
def test_failed_transport_attempt_usage_fails_closed_before_replay(
    budget,
    usage,
    reason,
) -> None:
    guard = DelegationBudgetGuard(trusted_budget=budget)
    adapter = make_policy_adapter(
        guard=guard,
        handler=lambda task: (_ for _ in ()).throw(
            AgentTransportError(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=True,
                usage=usage,
            )
        ),
    )

    with pytest.raises(DelegationUsageBudgetError) as captured:
        adapter.invoke(make_task())

    assert captured.value.reason == reason
    assert guard.usage_snapshot("run-1").step_count == 1


def test_delegation_guard_fails_closed_when_configured_usage_is_missing() -> None:
    guard = DelegationBudgetGuard(
        trusted_budget=RunBudget(max_prompt_tokens=100)
    )
    adapter = make_policy_adapter(
        guard=guard,
        handler=lambda task: AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
        ),
    )

    with pytest.raises(DelegationUsageBudgetError) as captured:
        adapter.invoke(make_task())

    assert captured.value.error_code == "plan.usage_budget_unavailable"
    assert captured.value.budget_field == "max_prompt_tokens"
    assert captured.value.reason == "missing"


def test_delegation_guard_does_not_hide_prior_unmetered_usage() -> None:
    guard = DelegationBudgetGuard()
    adapter = make_policy_adapter(
        guard=guard,
        handler=lambda task: AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
            usage=(
                RunUsage()
                if task.task_id == "unmetered"
                else RunUsage(input_tokens=5)
            ),
        ),
    )
    first = make_task().model_copy(update={"task_id": "unmetered"})
    adapter.invoke(first)

    with pytest.raises(DelegationUsageBudgetError) as captured:
        adapter.invoke(
            first.model_copy(
                update={
                    "task_id": "metered",
                    "budget": RunBudget(max_prompt_tokens=100),
                }
            )
        )

    assert captured.value.error_code == "plan.usage_budget_unavailable"


def test_delegation_guard_rejects_expired_trusted_deadline_before_handler() -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    handled = False
    guard = DelegationBudgetGuard(
        trusted_deadline_at=now - timedelta(milliseconds=1),
        clock=lambda: now,
    )

    def handler(task: AgentTask) -> AgentResult:
        nonlocal handled
        handled = True
        return AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
        )

    adapter = make_policy_adapter(
        guard=guard,
        handler=handler,
    )
    task = make_task().model_copy(
        update={"deadline_at": now + timedelta(hours=1)}
    )

    with pytest.raises(DelegationTimeBudgetError) as captured:
        adapter.invoke(task)

    assert handled is False
    assert captured.value.error_code == "plan.deadline_exceeded"
    assert captured.value.budget_field == "deadline_at"
    assert captured.value.phase == "admission"


def test_delegation_guard_reconciles_stricter_task_duration_after_handler() -> None:
    started_at = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    current_time = [started_at]
    guard = DelegationBudgetGuard(
        trusted_budget=RunBudget(max_duration_ms=1_000),
        run_started_at=started_at,
        clock=lambda: current_time[0],
    )

    def handler(task: AgentTask) -> AgentResult:
        current_time[0] += timedelta(milliseconds=60)
        return AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.COMPLETED,
            usage=RunUsage(total_tokens=5),
        )

    adapter = make_policy_adapter(
        guard=guard,
        handler=handler,
    )
    task = make_task().model_copy(
        update={"budget": RunBudget(max_duration_ms=50)}
    )

    with pytest.raises(DelegationTimeBudgetError) as captured:
        adapter.invoke(task)

    assert captured.value.error_code == "plan.duration_budget_exceeded"
    assert captured.value.budget_field == "max_duration_ms"
    assert captured.value.phase == "reconciliation"
    assert guard.usage_snapshot("run-1").total_tokens == 5


def test_adapter_prefers_reconciled_timeout_over_private_handler_error() -> None:
    started_at = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    current_time = [started_at]
    guard = DelegationBudgetGuard(
        trusted_budget=RunBudget(max_duration_ms=10),
        run_started_at=started_at,
        clock=lambda: current_time[0],
    )

    def handler(task: AgentTask) -> AgentResult:
        current_time[0] += timedelta(milliseconds=11)
        raise RuntimeError("private provider detail")

    adapter = make_policy_adapter(
        guard=guard,
        handler=handler,
    )

    with pytest.raises(DelegationTimeBudgetError) as captured:
        adapter.invoke(make_task())

    assert captured.value.phase == "reconciliation"
    assert "private provider detail" not in str(captured.value)
