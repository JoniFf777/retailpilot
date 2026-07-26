"""Typed in-process Agent adapter for the first V5 collaboration slice."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from types import MappingProxyType
from typing import Callable, Protocol, runtime_checkable

from .contracts import (
    AgentResult,
    AgentTask,
    AgentTransportFailureCode,
    ErrorSource,
    RunBudget,
    RunUsage,
    utc_now,
)


class AgentAdapterError(ValueError):
    """Raised when a task cannot safely use the configured Agent adapter."""


_TRANSPORT_FAILURE_MESSAGES = {
    AgentTransportFailureCode.UNAVAILABLE: "Agent transport is unavailable.",
    AgentTransportFailureCode.TIMEOUT: "Agent transport timed out.",
    AgentTransportFailureCode.PROTOCOL_ERROR: "Agent transport protocol failed.",
}


class AgentTransportError(AgentAdapterError):
    """Sanitized typed failure raised by an Agent transport implementation."""

    def __init__(
        self,
        failure_code: AgentTransportFailureCode | str,
        *,
        retriable: bool,
        usage: RunUsage,
    ) -> None:
        try:
            normalized_code = AgentTransportFailureCode(failure_code)
        except ValueError as exc:
            raise AgentAdapterError(
                "Agent transport failures require a supported failure code."
            ) from exc
        if type(retriable) is not bool:
            raise AgentAdapterError(
                "Agent transport failures require an explicit boolean retriable flag."
            )
        if not isinstance(usage, RunUsage) or usage.step_count < 1:
            raise AgentAdapterError(
                "Agent transport failures require typed usage for one or more attempts."
            )
        self.failure_code = normalized_code
        self.error_code = normalized_code.value
        self.retriable = retriable
        self.usage = usage.model_copy(deep=True)
        self.source = (
            ErrorSource.TIMEOUT
            if normalized_code == AgentTransportFailureCode.TIMEOUT
            else ErrorSource.AGENT
        )
        self.safe_message = _TRANSPORT_FAILURE_MESSAGES[normalized_code]
        super().__init__(self.safe_message)


@runtime_checkable
class AgentAdapter(Protocol):
    """Transport-neutral boundary for typed Agent task execution."""

    agent_name: str

    def invoke(self, task: AgentTask) -> AgentResult:
        """Execute one task and return its typed result."""
        ...


def _validate_adapter_task(agent_name: str, task: AgentTask) -> None:
    if task.recipient != agent_name:
        raise AgentAdapterError(
            f"Task recipient '{task.recipient}' does not match adapter "
            f"'{agent_name}'."
        )


def _validate_adapter_result(task: AgentTask, result: object) -> AgentResult:
    if not isinstance(result, AgentResult):
        raise AgentAdapterError("Agent adapters must return AgentResult.")
    if result.task_id != task.task_id:
        raise AgentAdapterError("Agent result task_id does not match the request.")
    return result


def invoke_agent_adapter(adapter: AgentAdapter, task: AgentTask) -> AgentResult:
    """Invoke any adapter under the shared transport-neutral identity contract."""

    _validate_adapter_task(adapter.agent_name, task)
    return _validate_adapter_result(task, adapter.invoke(task))


class AgentAdapterRegistry:
    """Immutable server-owned adapter lookup keyed by exact recipient name."""

    def __init__(
        self,
        adapters: Iterable[AgentAdapter] = (),
        *,
        require_policy: bool = False,
    ) -> None:
        registered: dict[str, AgentAdapter] = {}
        for adapter in adapters:
            if not isinstance(adapter, AgentAdapter):
                raise AgentAdapterError(
                    "Registered Agent adapters must satisfy AgentAdapter."
                )
            if require_policy and not isinstance(
                adapter, PolicyEnforcedAgentAdapter
            ):
                raise AgentAdapterError(
                    "Policy-required registries only accept "
                    "PolicyEnforcedAgentAdapter entries."
                )
            agent_name = adapter.agent_name
            if (
                not isinstance(agent_name, str)
                or not agent_name
                or agent_name != agent_name.strip()
            ):
                raise AgentAdapterError(
                    "Registered Agent adapters require a normalized agent_name."
                )
            if agent_name in registered:
                raise AgentAdapterError(
                    f"Agent adapter '{agent_name}' is already registered."
                )
            registered[agent_name] = adapter
        self._adapters = MappingProxyType(registered)
        self._policy_required = require_policy

    @property
    def policy_required(self) -> bool:
        return self._policy_required

    @property
    def registered_agents(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def resolve(self, recipient: str) -> AgentAdapter:
        adapter = self._adapters.get(recipient)
        if adapter is None:
            raise AgentAdapterError(
                f"No Agent adapter is registered for recipient '{recipient}'."
            )
        return adapter

    def invoke(self, task: AgentTask) -> AgentResult:
        return invoke_agent_adapter(self.resolve(task.recipient), task)


class DelegationBudgetError(AgentAdapterError):
    """Raised when an Agent task exceeds its trusted delegation budget."""


class DelegationUsageBudgetError(DelegationBudgetError):
    """Raised when measured Agent usage cannot satisfy a trusted ceiling."""

    def __init__(self, *, budget_field: str, reason: str) -> None:
        if reason not in {"exceeded", "missing"}:
            raise ValueError("Delegation usage budget reason is invalid.")
        self.budget_field = budget_field
        self.reason = reason
        self.error_code = (
            "plan.usage_budget_exceeded"
            if reason == "exceeded"
            else "plan.usage_budget_unavailable"
        )
        message = (
            "Agent usage exceeded a configured budget."
            if reason == "exceeded"
            else "Agent usage was unavailable for a configured budget."
        )
        super().__init__(message)


class DelegationTimeBudgetError(DelegationBudgetError):
    """Raised when a local Agent task crosses a trusted time boundary."""

    def __init__(self, *, budget_field: str, phase: str) -> None:
        if budget_field not in {"deadline_at", "max_duration_ms"}:
            raise ValueError("Delegation time budget field is invalid.")
        if phase not in {"admission", "reconciliation"}:
            raise ValueError("Delegation time budget phase is invalid.")
        self.budget_field = budget_field
        self.phase = phase
        self.error_code = (
            "plan.deadline_exceeded"
            if budget_field == "deadline_at"
            else "plan.duration_budget_exceeded"
        )
        super().__init__("Agent task time budget was exceeded.")


AgentTaskHandler = Callable[[AgentTask], AgentResult]


@dataclass
class DelegationBudgetGuard:
    """Atomically admit local tasks under trusted run and delegation limits."""

    trusted_budget: RunBudget | None = None
    trusted_deadline_at: datetime | None = None
    run_started_at: datetime | None = None
    clock: Callable[[], datetime] = field(default=utc_now, repr=False)
    _run_step_counts: dict[str, int] = field(default_factory=dict, init=False)
    _child_counts: dict[tuple[str, str], int] = field(
        default_factory=dict,
        init=False,
    )
    _admitted_task_ids: set[tuple[str, str]] = field(
        default_factory=set,
        init=False,
    )
    _run_usage: dict[str, RunUsage] = field(default_factory=dict, init=False)
    _run_usage_samples: dict[str, int] = field(default_factory=dict, init=False)
    _blocked_usage_runs: dict[str, tuple[str, str]] = field(
        default_factory=dict,
        init=False,
    )
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.trusted_budget is not None:
            self.trusted_budget = self.trusted_budget.model_copy(deep=True)
        now = self._as_utc(self.clock())
        self.trusted_deadline_at = self._optional_utc(self.trusted_deadline_at)
        self.run_started_at = self._optional_utc(self.run_started_at) or now

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _optional_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else cls._as_utc(value)

    def _limit(self, task: AgentTask, field_name: str) -> int | float | None:
        values = [getattr(task.budget, field_name)]
        if self.trusted_budget is not None:
            values.append(getattr(self.trusted_budget, field_name))
        configured = [value for value in values if value is not None]
        return min(configured) if configured else None

    def _deadline(self, task: AgentTask) -> datetime | None:
        values = [task.deadline_at, task.budget.deadline_at]
        if self.trusted_budget is not None:
            values.append(self.trusted_budget.deadline_at)
        values.append(self.trusted_deadline_at)
        configured = [self._as_utc(value) for value in values if value is not None]
        return min(configured) if configured else None

    def enforce_time(self, task: AgentTask, *, phase: str) -> None:
        """Check absolute and run-duration limits at an execution boundary."""

        now = self._as_utc(self.clock())
        deadline = self._deadline(task)
        if deadline is not None and now >= deadline:
            raise DelegationTimeBudgetError(
                budget_field="deadline_at",
                phase=phase,
            )

        max_duration_ms = self._limit(task, "max_duration_ms")
        if max_duration_ms is None:
            return
        started_at = self.run_started_at or now
        elapsed_ms = max(0.0, (now - started_at).total_seconds() * 1000)
        if elapsed_ms >= max_duration_ms:
            raise DelegationTimeBudgetError(
                budget_field="max_duration_ms",
                phase=phase,
            )

    def admit(self, task: AgentTask) -> None:
        """Reject an over-budget task before its Agent handler can run."""

        self.enforce_time(task, phase="admission")
        max_depth = self._limit(task, "max_delegation_depth")
        if max_depth is not None and task.delegation_depth > max_depth:
            raise DelegationBudgetError(
                f"Task delegation depth {task.delegation_depth} exceeds "
                f"the configured maximum {max_depth}."
            )

        with self._lock:
            task_identity = (task.run_id, task.task_id)
            if task_identity in self._admitted_task_ids:
                return

            run_step_count = self._run_step_counts.get(task.run_id, 0)
            max_steps = self._limit(task, "max_steps")
            if max_steps is not None and run_step_count >= max_steps:
                raise DelegationBudgetError(
                    f"Run '{task.run_id}' reached its Agent task step limit "
                    f"of {max_steps}."
                )

            child_identity: tuple[str, str] | None = None
            child_count = 0
            if task.parent_task_id is not None:
                child_identity = (task.run_id, task.parent_task_id)
                child_count = self._child_counts.get(child_identity, 0)
                max_children = self._limit(task, "max_child_tasks")
                if max_children is not None and child_count >= max_children:
                    raise DelegationBudgetError(
                        f"Parent task '{task.parent_task_id}' reached its child task "
                        f"limit of {max_children}."
                    )

            self._run_step_counts[task.run_id] = run_step_count + 1
            if child_identity is not None:
                self._child_counts[child_identity] = child_count + 1
            self._admitted_task_ids.add(task_identity)

    @staticmethod
    def _usage_value(usage: RunUsage, budget_field: str) -> int | float | None:
        usage_field = {
            "max_prompt_tokens": "input_tokens",
            "max_completion_tokens": "output_tokens",
            "max_total_tokens": "total_tokens",
            "max_cost_usd": "cost_usd",
        }[budget_field]
        value = getattr(usage, usage_field)
        if (
            budget_field == "max_total_tokens"
            and value is None
            and usage.input_tokens is not None
            and usage.output_tokens is not None
        ):
            return usage.input_tokens + usage.output_tokens
        return value

    @classmethod
    def _combine_usage(
        cls,
        current: RunUsage,
        incoming: RunUsage,
        *,
        has_current_sample: bool,
    ) -> RunUsage:
        def complete_sum(field_name: str) -> int | float | None:
            current_value = getattr(current, field_name)
            incoming_value = getattr(incoming, field_name)
            if not has_current_sample:
                return incoming_value
            if current_value is None or incoming_value is None:
                return None
            return current_value + incoming_value

        incoming_total = cls._usage_value(incoming, "max_total_tokens")
        current_total = cls._usage_value(current, "max_total_tokens")
        if not has_current_sample:
            combined_total = incoming_total
        elif current_total is None or incoming_total is None:
            combined_total = None
        else:
            combined_total = current_total + incoming_total

        return RunUsage(
            input_tokens=complete_sum("input_tokens"),
            output_tokens=complete_sum("output_tokens"),
            total_tokens=combined_total,
            cost_usd=complete_sum("cost_usd"),
            tool_call_count=current.tool_call_count + incoming.tool_call_count,
            step_count=current.step_count + incoming.step_count,
        )

    def reconcile_usage(self, task: AgentTask, usage: RunUsage) -> None:
        """Record one measured attempt and enforce cumulative usage/time limits."""

        usage_error: DelegationUsageBudgetError | None = None
        with self._lock:
            blocked = self._blocked_usage_runs.get(task.run_id)
            if blocked is not None:
                usage_error = DelegationUsageBudgetError(
                    budget_field=blocked[0],
                    reason=blocked[1],
                )
            else:
                current = self._run_usage.get(task.run_id, RunUsage())
                sample_count = self._run_usage_samples.get(task.run_id, 0)
                proposed = self._combine_usage(
                    current,
                    usage,
                    has_current_sample=sample_count > 0,
                )
                self._run_usage[task.run_id] = proposed
                self._run_usage_samples[task.run_id] = sample_count + 1

                for budget_field in (
                    "max_prompt_tokens",
                    "max_completion_tokens",
                    "max_total_tokens",
                    "max_cost_usd",
                ):
                    limit = self._limit(task, budget_field)
                    if limit is None:
                        continue
                    proposed_value = self._usage_value(proposed, budget_field)
                    if proposed_value is None:
                        self._blocked_usage_runs[task.run_id] = (
                            budget_field,
                            "missing",
                        )
                        usage_error = DelegationUsageBudgetError(
                            budget_field=budget_field,
                            reason="missing",
                        )
                        break
                    if proposed_value > limit:
                        self._blocked_usage_runs[task.run_id] = (
                            budget_field,
                            "exceeded",
                        )
                        usage_error = DelegationUsageBudgetError(
                            budget_field=budget_field,
                            reason="exceeded",
                        )
                        break

        self.enforce_time(task, phase="reconciliation")
        if usage_error is not None:
            raise usage_error

    def reconcile(self, task: AgentTask, result: AgentResult) -> None:
        """Record a typed Agent result under the shared usage/time limits."""

        self.reconcile_usage(task, result.usage)

    def usage_snapshot(self, run_id: str) -> RunUsage:
        """Return a detached aggregate for diagnostics and tests."""

        with self._lock:
            return self._run_usage.get(run_id, RunUsage()).model_copy(deep=True)


@dataclass(frozen=True)
class InProcessAgentAdapter:
    """Runs one typed task locally without owning runtime policy lifecycle."""

    agent_name: str
    handler: AgentTaskHandler

    def invoke(self, task: AgentTask) -> AgentResult:
        _validate_adapter_task(self.agent_name, task)
        return _validate_adapter_result(task, self.handler(task))


@dataclass(frozen=True)
class PolicyEnforcedAgentAdapter:
    """Applies trusted delegation policy around any typed Agent transport."""

    adapter: AgentAdapter
    delegation_guard: DelegationBudgetGuard

    def __post_init__(self) -> None:
        if not isinstance(self.adapter, AgentAdapter):
            raise AgentAdapterError(
                "Policy-enforced adapters must wrap an AgentAdapter."
            )

    @property
    def agent_name(self) -> str:
        return self.adapter.agent_name

    def invoke(self, task: AgentTask) -> AgentResult:
        _validate_adapter_task(self.agent_name, task)
        self.delegation_guard.admit(task)
        try:
            result = self.adapter.invoke(task)
        except AgentTransportError as exc:
            self.delegation_guard.reconcile_usage(task, exc.usage)
            raise
        except Exception:
            self.delegation_guard.enforce_time(task, phase="reconciliation")
            raise
        result = _validate_adapter_result(task, result)
        self.delegation_guard.reconcile(task, result)
        return result


__all__ = [
    "AgentAdapter",
    "AgentAdapterError",
    "AgentAdapterRegistry",
    "AgentTransportError",
    "AgentTransportFailureCode",
    "AgentTaskHandler",
    "DelegationBudgetError",
    "DelegationBudgetGuard",
    "DelegationTimeBudgetError",
    "DelegationUsageBudgetError",
    "InProcessAgentAdapter",
    "PolicyEnforcedAgentAdapter",
    "invoke_agent_adapter",
]
