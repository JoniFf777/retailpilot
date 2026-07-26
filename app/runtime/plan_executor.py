"""Disabled-by-default bounded execution and deterministic fan-in."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context, copy_context
from dataclasses import dataclass
from time import perf_counter

from .adapters import (
    AgentTransportError,
    DelegationBudgetError,
    DelegationTimeBudgetError,
    DelegationUsageBudgetError,
)
from .contracts import (
    AgentExecutionPlan,
    AgentPlanAttemptEvent,
    AgentPlanAttemptLifecycle,
    AgentPlanExecutionMode,
    AgentPlanResult,
    AgentPlanStatus,
    AgentPlanStep,
    AgentPlanStepResult,
    AgentPlanStepStatus,
    AgentResult,
    AgentTaskStatus,
    AgentTaskRetryOwner,
    AgentPlanRetryReason,
    ErrorSource,
    MemoryReference,
    RunError,
    RunUsage,
    aggregate_run_usage,
    utc_now,
)


class PlanExecutionError(ValueError):
    """Raised when a plan cannot use the configured local executor."""


PlanStepHandler = Callable[[AgentPlanStep], AgentResult]
PlanCancellationCheck = Callable[[], bool]
PlanStepObserver = Callable[
    [str, AgentPlanStep, AgentPlanStepResult | None],
    None,
]
PlanAttemptObserver = Callable[[AgentPlanAttemptEvent], None]


def _notify_step(
    observer: PlanStepObserver | None,
    event: str,
    step: AgentPlanStep,
    result: AgentPlanStepResult | None,
) -> None:
    if observer is None:
        return
    try:
        observer(event, step, result)
    except Exception:
        # Observability must not change the plan result.
        pass


def _notify_attempt(
    observer: PlanAttemptObserver | None,
    event: AgentPlanAttemptEvent,
) -> None:
    if observer is None:
        return
    try:
        observer(event)
    except Exception:
        # Observability must not change retry or plan execution.
        pass


def _attempt_event(
    lifecycle: AgentPlanAttemptLifecycle,
    step: AgentPlanStep,
    attempt: int,
    **updates: object,
) -> AgentPlanAttemptEvent:
    return AgentPlanAttemptEvent(
        lifecycle=lifecycle,
        step_id=step.step_id,
        recipient=step.recipient,
        attempt=attempt,
        max_attempts=step.retry_policy.max_attempts,
        **updates,
    )


def _run_step(
    step: AgentPlanStep,
    handler: PlanStepHandler,
    cancellation_check: PlanCancellationCheck | None = None,
    attempt_observer: PlanAttemptObserver | None = None,
) -> AgentPlanStepResult:
    started_at = utc_now()
    started = perf_counter()
    usage: RunUsage | None = None
    attempt_count = 0
    attempt_usages: list[RunUsage] = []
    while True:
        attempt_count += 1
        if attempt_count > 1:
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    AgentPlanAttemptLifecycle.RETRY_STARTED,
                    step,
                    attempt_count,
                    reason=AgentPlanRetryReason.TRANSPORT_RETRIABLE,
                ),
            )
        _notify_attempt(
            attempt_observer,
            _attempt_event(
                AgentPlanAttemptLifecycle.ATTEMPT_STARTED,
                step,
                attempt_count,
            ),
        )
        try:
            result = handler(step)
            if not isinstance(result, AgentResult):
                raise TypeError("Plan step handlers must return AgentResult.")
            if result.status == AgentTaskStatus.COMPLETED:
                status = AgentPlanStepStatus.COMPLETED
                error = None
            elif result.status == AgentTaskStatus.CANCELLED:
                status = AgentPlanStepStatus.CANCELLED
                error = result.error or RunError(
                    code="plan.step_cancelled",
                    message="Agent plan step was cancelled.",
                    source=ErrorSource.CANCELLATION,
                )
            else:
                status = AgentPlanStepStatus.FAILED
                error = result.error
            attempt_usages.append(result.usage)
            terminal_lifecycle = {
                AgentPlanStepStatus.COMPLETED: (
                    AgentPlanAttemptLifecycle.ATTEMPT_COMPLETED
                ),
                AgentPlanStepStatus.CANCELLED: (
                    AgentPlanAttemptLifecycle.ATTEMPT_CANCELLED
                ),
                AgentPlanStepStatus.FAILED: AgentPlanAttemptLifecycle.ATTEMPT_FAILED,
            }[status]
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    terminal_lifecycle,
                    step,
                    attempt_count,
                    error_code=None if error is None else error.code,
                    usage=result.usage,
                ),
            )
            if status == AgentPlanStepStatus.COMPLETED and attempt_count > 1:
                _notify_attempt(
                    attempt_observer,
                    _attempt_event(
                        AgentPlanAttemptLifecycle.RETRY_SUCCEEDED,
                        step,
                        attempt_count,
                        reason=AgentPlanRetryReason.SUCCESS_AFTER_RETRY,
                        usage=result.usage,
                    ),
                )
            break
        except AgentTransportError as exc:
            result = None
            attempt_usages.append(exc.usage)
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    AgentPlanAttemptLifecycle.ATTEMPT_FAILED,
                    step,
                    attempt_count,
                    failure_code=exc.failure_code,
                    error_code=exc.error_code,
                    retriable=exc.retriable,
                    usage=exc.usage,
                ),
            )
            retry_policy = step.retry_policy
            retry_allowed = (
                retry_policy.owner == AgentTaskRetryOwner.PLAN_EXECUTOR
                and exc.retriable
                and exc.failure_code.value in retry_policy.retryable_failure_codes
                and attempt_count < retry_policy.max_attempts
            )
            if retry_allowed:
                _notify_attempt(
                    attempt_observer,
                    _attempt_event(
                        AgentPlanAttemptLifecycle.RETRY_SCHEDULED,
                        step,
                        attempt_count,
                        next_attempt=attempt_count + 1,
                        failure_code=exc.failure_code,
                        error_code=exc.error_code,
                        retriable=True,
                        reason=AgentPlanRetryReason.TRANSPORT_RETRIABLE,
                        usage=exc.usage,
                    ),
                )
                if cancellation_check is not None and cancellation_check():
                    _notify_attempt(
                        attempt_observer,
                        _attempt_event(
                            AgentPlanAttemptLifecycle.RETRY_CANCELLED,
                            step,
                            attempt_count,
                            next_attempt=attempt_count + 1,
                            failure_code=exc.failure_code,
                            error_code=exc.error_code,
                            retriable=True,
                            reason=(
                                AgentPlanRetryReason.CANCELLATION_BEFORE_RETRY
                            ),
                            usage=exc.usage,
                        ),
                    )
                    status = AgentPlanStepStatus.CANCELLED
                    error = RunError(
                        code="plan.step_cancelled",
                        message="Agent plan step was cancelled before retry.",
                        source=ErrorSource.CANCELLATION,
                    )
                    break
                continue
            if (
                retry_policy.owner == AgentTaskRetryOwner.PLAN_EXECUTOR
                and exc.retriable
                and exc.failure_code.value in retry_policy.retryable_failure_codes
                and attempt_count >= retry_policy.max_attempts
            ):
                decision_lifecycle = (
                    AgentPlanAttemptLifecycle.ATTEMPTS_EXHAUSTED
                )
                decision_reason = AgentPlanRetryReason.ATTEMPTS_EXHAUSTED
            else:
                decision_lifecycle = (
                    AgentPlanAttemptLifecycle.RETRY_NON_RETRIABLE
                )
                if retry_policy.owner != AgentTaskRetryOwner.PLAN_EXECUTOR:
                    decision_reason = AgentPlanRetryReason.RETRY_POLICY_DISABLED
                elif not exc.retriable:
                    decision_reason = (
                        AgentPlanRetryReason.TRANSPORT_NON_RETRIABLE
                    )
                else:
                    decision_reason = (
                        AgentPlanRetryReason.FAILURE_CODE_NOT_ALLOWLISTED
                    )
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    decision_lifecycle,
                    step,
                    attempt_count,
                    failure_code=exc.failure_code,
                    error_code=exc.error_code,
                    retriable=exc.retriable,
                    reason=decision_reason,
                    usage=exc.usage,
                ),
            )
            status = AgentPlanStepStatus.FAILED
            error = RunError(
                code=exc.error_code,
                message=exc.safe_message,
                source=exc.source,
                retriable=exc.retriable,
                details={"exception_type": exc.__class__.__name__},
            )
            break
        except DelegationTimeBudgetError as exc:
            result = None
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    AgentPlanAttemptLifecycle.ATTEMPT_FAILED,
                    step,
                    attempt_count,
                    error_code=exc.error_code,
                ),
            )
            if step.retry_policy.owner == AgentTaskRetryOwner.PLAN_EXECUTOR:
                _notify_attempt(
                    attempt_observer,
                    _attempt_event(
                        AgentPlanAttemptLifecycle.RETRY_BUDGET_BLOCKED,
                        step,
                        attempt_count,
                        error_code=exc.error_code,
                        retriable=False,
                        reason=AgentPlanRetryReason.TIME_BUDGET,
                        budget_field=exc.budget_field,
                    ),
                )
            status = AgentPlanStepStatus.FAILED
            error = RunError(
                code=exc.error_code,
                message="Agent plan step time budget was exceeded.",
                source=ErrorSource.TIMEOUT,
                retriable=False,
                details={
                    "budget_field": exc.budget_field,
                    "phase": exc.phase,
                    "exception_type": exc.__class__.__name__,
                },
            )
            break
        except DelegationUsageBudgetError as exc:
            result = None
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    AgentPlanAttemptLifecycle.ATTEMPT_FAILED,
                    step,
                    attempt_count,
                    error_code=exc.error_code,
                ),
            )
            if step.retry_policy.owner == AgentTaskRetryOwner.PLAN_EXECUTOR:
                _notify_attempt(
                    attempt_observer,
                    _attempt_event(
                        AgentPlanAttemptLifecycle.RETRY_BUDGET_BLOCKED,
                        step,
                        attempt_count,
                        error_code=exc.error_code,
                        retriable=False,
                        reason=AgentPlanRetryReason.USAGE_BUDGET,
                        budget_field=exc.budget_field,
                        budget_reason=exc.reason,
                    ),
                )
            status = AgentPlanStepStatus.FAILED
            error = RunError(
                code=exc.error_code,
                message="Agent plan step usage budget could not be satisfied.",
                source=ErrorSource.AGENT,
                retriable=False,
                details={
                    "budget_field": exc.budget_field,
                    "reason": exc.reason,
                    "exception_type": exc.__class__.__name__,
                },
            )
            break
        except DelegationBudgetError as exc:
            result = None
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    AgentPlanAttemptLifecycle.ATTEMPT_FAILED,
                    step,
                    attempt_count,
                    error_code="plan.step_budget_exceeded",
                ),
            )
            if step.retry_policy.owner == AgentTaskRetryOwner.PLAN_EXECUTOR:
                _notify_attempt(
                    attempt_observer,
                    _attempt_event(
                        AgentPlanAttemptLifecycle.RETRY_BUDGET_BLOCKED,
                        step,
                        attempt_count,
                        error_code="plan.step_budget_exceeded",
                        retriable=False,
                        reason=AgentPlanRetryReason.DELEGATION_BUDGET,
                    ),
                )
            status = AgentPlanStepStatus.FAILED
            error = RunError(
                code="plan.step_budget_exceeded",
                message="Agent plan step budget was exceeded.",
                source=ErrorSource.AGENT,
                retriable=False,
                details={"exception_type": exc.__class__.__name__},
            )
            break
        except Exception as exc:
            result = None
            _notify_attempt(
                attempt_observer,
                _attempt_event(
                    AgentPlanAttemptLifecycle.ATTEMPT_FAILED,
                    step,
                    attempt_count,
                    error_code="plan.step_failed",
                    retriable=False,
                ),
            )
            status = AgentPlanStepStatus.FAILED
            error = RunError(
                code="plan.step_failed",
                message="Agent plan step execution failed.",
                source=ErrorSource.AGENT,
                retriable=False,
                details={"exception_type": exc.__class__.__name__},
            )
            break

    if attempt_usages:
        usage = aggregate_run_usage(attempt_usages)

    return AgentPlanStepResult(
        step_id=step.step_id,
        recipient=step.recipient,
        status=status,
        result=result,
        error=error,
        usage=usage,
        attempt_count=attempt_count,
        started_at=started_at,
        completed_at=utc_now(),
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
    )


def _topological_steps(plan: AgentExecutionPlan) -> list[AgentPlanStep]:
    remaining = list(plan.steps)
    ordered: list[AgentPlanStep] = []
    completed_ids: set[str] = set()
    while remaining:
        ready = [
            step for step in remaining if set(step.depends_on).issubset(completed_ids)
        ]
        if not ready:
            raise PlanExecutionError("Agent plan has no executable dependency frontier.")
        for step in ready:
            ordered.append(step)
            completed_ids.add(step.step_id)
            remaining.remove(step)
    return ordered


def _skipped_step(step: AgentPlanStep) -> AgentPlanStepResult:
    now = utc_now()
    return AgentPlanStepResult(
        step_id=step.step_id,
        recipient=step.recipient,
        status=AgentPlanStepStatus.SKIPPED,
        error=RunError(
            code="plan.dependency_failed",
            message="Agent plan step was skipped because a dependency did not complete.",
            source=ErrorSource.AGENT,
        ),
        started_at=now,
        completed_at=now,
    )


def _cancelled_step(step: AgentPlanStep) -> AgentPlanStepResult:
    now = utc_now()
    return AgentPlanStepResult(
        step_id=step.step_id,
        recipient=step.recipient,
        status=AgentPlanStepStatus.CANCELLED,
        error=RunError(
            code="plan.step_cancelled",
            message="Agent plan step was cancelled before execution.",
            source=ErrorSource.CANCELLATION,
        ),
        started_at=now,
        completed_at=now,
    )


def _execute_step(
    step: AgentPlanStep,
    handler: PlanStepHandler,
    cancellation_check: PlanCancellationCheck | None,
    observer: PlanStepObserver | None,
    attempt_observer: PlanAttemptObserver | None,
) -> AgentPlanStepResult:
    if cancellation_check is not None and cancellation_check():
        result = _cancelled_step(step)
        _notify_step(observer, "cancelled", step, result)
        return result

    _notify_step(observer, "started", step, None)
    result = _run_step(
        step,
        handler,
        cancellation_check,
        attempt_observer,
    )
    _notify_step(observer, str(result.status), step, result)
    return result


def _aggregate_usage(step_results: list[AgentPlanStepResult]) -> RunUsage:
    return aggregate_run_usage(
        step.usage for step in step_results if step.usage is not None
    )


def _aggregate_plan_result(
    plan: AgentExecutionPlan,
    step_results: list[AgentPlanStepResult],
) -> AgentPlanResult:
    completed = [
        step for step in step_results if step.status == AgentPlanStepStatus.COMPLETED
    ]
    if len(completed) == len(step_results):
        status = AgentPlanStatus.COMPLETED
    elif completed:
        status = AgentPlanStatus.PARTIAL
    else:
        status = AgentPlanStatus.FAILED

    references: list[MemoryReference] = []
    seen_references: set[tuple[str, str, str]] = set()
    for step in step_results:
        if step.result is None:
            continue
        for reference in step.result.evidence_references:
            identity = (reference.ref_type, reference.ref_id, reference.scope)
            if identity not in seen_references:
                references.append(reference)
                seen_references.add(identity)

    return AgentPlanResult(
        plan_id=plan.plan_id,
        status=status,
        step_results=step_results,
        output_data={
            step.step_id: step.result.output_data
            for step in completed
            if step.result is not None
        },
        evidence_references=references,
        usage=_aggregate_usage(step_results),
        errors=[step.error for step in step_results if step.error is not None],
        metadata={
            "execution_mode": plan.execution_mode,
            "max_parallelism": plan.max_parallelism,
        },
    )


@dataclass(frozen=True)
class BoundedPlanExecutor:
    """Execute validated plans locally; parallel mode requires explicit opt-in."""

    parallel_enabled: bool = False

    def execute(
        self,
        plan: AgentExecutionPlan,
        handler: PlanStepHandler,
        *,
        cancellation_check: PlanCancellationCheck | None = None,
        step_observer: PlanStepObserver | None = None,
        attempt_observer: PlanAttemptObserver | None = None,
    ) -> AgentPlanResult:
        if plan.execution_mode == AgentPlanExecutionMode.BOUNDED_PARALLEL:
            return self._execute_parallel(
                plan,
                handler,
                cancellation_check,
                step_observer,
                attempt_observer,
            )
        return self._execute_sequential(
            plan,
            handler,
            cancellation_check,
            step_observer,
            attempt_observer,
        )

    def _execute_sequential(
        self,
        plan: AgentExecutionPlan,
        handler: PlanStepHandler,
        cancellation_check: PlanCancellationCheck | None,
        step_observer: PlanStepObserver | None,
        attempt_observer: PlanAttemptObserver | None,
    ) -> AgentPlanResult:
        results_by_id: dict[str, AgentPlanStepResult] = {}
        for step in _topological_steps(plan):
            dependency_results = [results_by_id[item] for item in step.depends_on]
            if any(
                result.status != AgentPlanStepStatus.COMPLETED
                for result in dependency_results
            ):
                results_by_id[step.step_id] = _skipped_step(step)
            else:
                results_by_id[step.step_id] = _execute_step(
                    step,
                    handler,
                    cancellation_check,
                    step_observer,
                    attempt_observer,
                )
        return _aggregate_plan_result(
            plan,
            [results_by_id[step.step_id] for step in plan.steps],
        )

    def _execute_parallel(
        self,
        plan: AgentExecutionPlan,
        handler: PlanStepHandler,
        cancellation_check: PlanCancellationCheck | None,
        step_observer: PlanStepObserver | None,
        attempt_observer: PlanAttemptObserver | None,
    ) -> AgentPlanResult:
        if not self.parallel_enabled:
            raise PlanExecutionError("Bounded parallel plan execution is disabled.")
        if any(step.depends_on for step in plan.steps):
            raise PlanExecutionError(
                "Bounded parallel execution currently requires independent steps."
            )
        if not plan.steps:
            return _aggregate_plan_result(plan, [])

        worker_count = min(plan.max_parallelism, len(plan.steps))

        def execute_in_context(item: tuple[Context, AgentPlanStep]):
            context, step = item
            return context.run(
                _execute_step,
                step,
                handler,
                cancellation_check,
                step_observer,
                attempt_observer,
            )

        contextual_steps = [(copy_context(), step) for step in plan.steps]
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            step_results = list(executor.map(execute_in_context, contextual_steps))
        return _aggregate_plan_result(plan, step_results)


__all__ = [
    "BoundedPlanExecutor",
    "PlanCancellationCheck",
    "PlanAttemptObserver",
    "PlanExecutionError",
    "PlanStepHandler",
    "PlanStepObserver",
]
