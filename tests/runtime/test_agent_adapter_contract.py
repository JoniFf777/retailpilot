from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest

from app.runtime import (
    AgentAdapter,
    AgentAdapterError,
    AgentAdapterRegistry,
    AgentTransportError,
    AgentTransportFailureCode,
    AgentResult,
    AgentTask,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTaskStatus,
    ErrorSource,
    InProcessAgentAdapter,
    PolicyEnforcedAgentAdapter,
    DelegationBudgetError,
    DelegationBudgetGuard,
    DelegationTimeBudgetError,
    RunBudget,
    RunError,
    RunUsage,
    build_agent_task_idempotency_key,
    invoke_agent_adapter,
)


def make_task(*, recipient: str = "product_agent") -> AgentTask:
    return AgentTask(
        task_id="task-1",
        run_id="run-1",
        sender="supervisor",
        recipient=recipient,
        intent="product_read",
        trace_id="trace-1",
    )


@dataclass
class ProtocolOnlyAdapter:
    agent_name: str
    result_factory: Callable[[AgentTask], object]
    calls: list[str] = field(default_factory=list)

    def invoke(self, task: AgentTask):
        self.calls.append(task.task_id)
        return self.result_factory(task)


def completed_result(task: AgentTask) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        status=AgentTaskStatus.COMPLETED,
        output_data={"transport": "test"},
    )


def test_structural_adapter_conforms_without_inheritance() -> None:
    adapter = ProtocolOnlyAdapter("product_agent", completed_result)
    task = make_task()

    result = invoke_agent_adapter(adapter, task)

    assert isinstance(adapter, AgentAdapter)
    assert result.output_data == {"transport": "test"}
    assert adapter.calls == ["task-1"]


@pytest.mark.parametrize(
    ("failure_code", "message", "source"),
    [
        (
            AgentTransportFailureCode.UNAVAILABLE,
            "Agent transport is unavailable.",
            "agent",
        ),
        (
            AgentTransportFailureCode.TIMEOUT,
            "Agent transport timed out.",
            "timeout",
        ),
        (
            AgentTransportFailureCode.PROTOCOL_ERROR,
            "Agent transport protocol failed.",
            "agent",
        ),
    ],
)
def test_transport_failure_contract_uses_safe_server_defined_values(
    failure_code,
    message,
    source,
) -> None:
    usage = RunUsage(total_tokens=3, step_count=1)
    error = AgentTransportError(failure_code, retriable=True, usage=usage)

    assert error.error_code == failure_code.value
    assert str(error) == message
    assert error.source == source
    assert error.retriable is True
    assert error.usage == usage
    assert error.usage is not usage


def test_transport_failure_contract_rejects_arbitrary_code_and_retry_value() -> None:
    with pytest.raises(AgentAdapterError, match="supported failure code"):
        AgentTransportError(
            "private.endpoint_failure",
            retriable=True,
            usage=RunUsage(step_count=1),
        )
    with pytest.raises(AgentAdapterError, match="boolean retriable"):
        AgentTransportError(
            AgentTransportFailureCode.UNAVAILABLE,
            retriable=1,  # type: ignore[arg-type]
            usage=RunUsage(step_count=1),
        )
    with pytest.raises(AgentAdapterError, match="typed usage"):
        AgentTransportError(
            AgentTransportFailureCode.UNAVAILABLE,
            retriable=True,
            usage=RunUsage(),
        )


def test_task_retry_policy_requires_plan_ownership_and_trusted_identity() -> None:
    retry_policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )
    idempotency_key = build_agent_task_idempotency_key("run-1", "task-1")
    task = AgentTask(
        task_id="task-1",
        run_id="run-1",
        sender="supervisor",
        recipient="product_agent",
        intent="product_read",
        trace_id="trace-1",
        idempotency_key=idempotency_key,
        retry_policy=retry_policy,
    )

    assert task.retry_policy.owner == "plan_executor"
    assert task.retry_policy.max_attempts == 2
    assert task.retry_policy.retryable_failure_codes == {
        "agent.transport_unavailable"
    }
    assert task.idempotency_key == idempotency_key

    with pytest.raises(ValueError, match="trusted task idempotency key"):
        AgentTask(
            task_id="task-1",
            run_id="run-1",
            sender="supervisor",
            recipient="product_agent",
            intent="product_read",
            trace_id="trace-1",
            idempotency_key="caller-selected-key",
            retry_policy=retry_policy,
        )


@pytest.mark.parametrize(
    "policy_data",
    [
        {"max_attempts": 2},
        {
            "owner": "plan_executor",
            "max_attempts": 1,
            "retryable_failure_codes": {"agent.transport_unavailable"},
        },
        {
            "owner": "plan_executor",
            "max_attempts": 2,
            "retryable_failure_codes": {"agent.transport_unavailable"},
            "preserve_task_identity": False,
        },
        {
            "owner": "plan_executor",
            "max_attempts": 2,
            "retryable_failure_codes": {"agent.transport_unavailable"},
            "account_each_attempt": False,
        },
    ],
)
def test_task_retry_policy_fails_closed_for_unsafe_configuration(
    policy_data,
) -> None:
    with pytest.raises(ValueError):
        AgentTaskRetryPolicy.model_validate(policy_data)


def test_contract_rejects_wrong_recipient_before_transport_invocation() -> None:
    adapter = ProtocolOnlyAdapter("product_agent", completed_result)

    with pytest.raises(AgentAdapterError, match="recipient"):
        invoke_agent_adapter(adapter, make_task(recipient="rag_agent"))

    assert adapter.calls == []


@pytest.mark.parametrize(
    ("result_factory", "message"),
    [
        (lambda task: {"task_id": task.task_id}, "AgentResult"),
        (
            lambda task: AgentResult(
                task_id="different-task",
                status=AgentTaskStatus.COMPLETED,
            ),
            "task_id",
        ),
    ],
)
def test_contract_rejects_invalid_transport_results(
    result_factory: Callable[[AgentTask], object],
    message: str,
) -> None:
    adapter = ProtocolOnlyAdapter("product_agent", result_factory)

    with pytest.raises(AgentAdapterError, match=message):
        invoke_agent_adapter(adapter, make_task())


def test_contract_preserves_typed_failed_result() -> None:
    def failed_result(task: AgentTask) -> AgentResult:
        return AgentResult(
            task_id=task.task_id,
            status=AgentTaskStatus.FAILED,
            error=RunError(
                code="agent.unavailable",
                message="Agent is unavailable.",
                source=ErrorSource.AGENT,
                retriable=True,
            ),
        )

    result = invoke_agent_adapter(
        ProtocolOnlyAdapter("product_agent", failed_result),
        make_task(),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "agent.unavailable"


def test_in_process_adapter_satisfies_transport_neutral_protocol() -> None:
    adapter = InProcessAgentAdapter(
        agent_name="product_agent",
        handler=completed_result,
    )

    assert isinstance(adapter, AgentAdapter)
    assert invoke_agent_adapter(adapter, make_task()).status == "completed"


def test_registry_resolves_and_invokes_exact_recipient() -> None:
    product = ProtocolOnlyAdapter("product_agent", completed_result)
    rag = ProtocolOnlyAdapter("rag_agent", completed_result)
    registry = AgentAdapterRegistry([product, rag])

    result = registry.invoke(make_task(recipient="rag_agent"))

    assert registry.registered_agents == ("product_agent", "rag_agent")
    assert registry.resolve("product_agent") is product
    assert result.task_id == "task-1"
    assert product.calls == []
    assert rag.calls == ["task-1"]


def test_registry_rejects_duplicate_and_invalid_adapters() -> None:
    product = ProtocolOnlyAdapter("product_agent", completed_result)

    with pytest.raises(AgentAdapterError, match="already registered"):
        AgentAdapterRegistry([product, product])
    with pytest.raises(AgentAdapterError, match="normalized"):
        AgentAdapterRegistry(
            [ProtocolOnlyAdapter(" product_agent", completed_result)]
        )
    with pytest.raises(AgentAdapterError, match="satisfy AgentAdapter"):
        AgentAdapterRegistry([object()])  # type: ignore[list-item]


def test_registry_fails_closed_for_unknown_recipient() -> None:
    registry = AgentAdapterRegistry(
        [ProtocolOnlyAdapter("product_agent", completed_result)]
    )

    with pytest.raises(AgentAdapterError, match="No Agent adapter"):
        registry.resolve("rag_agent")


def test_registry_policy_required_mode_rejects_unwrapped_transport() -> None:
    transport = ProtocolOnlyAdapter("product_agent", completed_result)

    with pytest.raises(AgentAdapterError, match="PolicyEnforcedAgentAdapter"):
        AgentAdapterRegistry([transport], require_policy=True)


def test_registry_preserves_policy_reconciliation_after_transport_failure() -> None:
    started_at = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    current_time = [started_at]

    def fail_after_deadline(task: AgentTask) -> AgentResult:
        current_time[0] += timedelta(milliseconds=11)
        raise RuntimeError("private transport endpoint")

    adapter = PolicyEnforcedAgentAdapter(
        adapter=ProtocolOnlyAdapter("product_agent", fail_after_deadline),
        delegation_guard=DelegationBudgetGuard(
            trusted_budget=RunBudget(max_duration_ms=10),
            run_started_at=started_at,
            clock=lambda: current_time[0],
        ),
    )
    registry = AgentAdapterRegistry([adapter], require_policy=True)

    with pytest.raises(DelegationTimeBudgetError) as captured:
        registry.invoke(make_task())

    assert captured.value.phase == "reconciliation"
    assert "private transport endpoint" not in str(captured.value)


def test_policy_wrapper_enforces_budget_for_protocol_only_transport() -> None:
    transport = ProtocolOnlyAdapter("product_agent", completed_result)
    adapter = PolicyEnforcedAgentAdapter(
        adapter=transport,
        delegation_guard=DelegationBudgetGuard(
            trusted_budget=RunBudget(max_steps=1)
        ),
    )
    first = make_task()

    invoke_agent_adapter(adapter, first)
    with pytest.raises(DelegationBudgetError, match="task step limit"):
        invoke_agent_adapter(
            adapter,
            first.model_copy(update={"task_id": "task-2"}),
        )

    assert transport.calls == ["task-1"]
