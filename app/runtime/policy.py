"""Server-owned defaults for runtime policy and execution budgets."""

from __future__ import annotations

from typing import Any

from .contracts import (
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTransportFailureCode,
    RunBudget,
    RunOperation,
    RuntimePolicy,
)


def _optional_setting(settings: Any, name: str) -> int | None:
    value = getattr(settings, name, None)
    return value if isinstance(value, int) and value > 0 else None


def _optional_float_setting(settings: Any, name: str) -> float | None:
    value = getattr(settings, name, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def build_runtime_policy(settings: Any, operation: RunOperation) -> RuntimePolicy:
    """Build a deny-first policy without accepting client policy overrides."""

    task_max_attempts = max(
        1,
        min(3, int(getattr(settings, "shopmind_agent_task_max_attempts", 1))),
    )
    task_retry_policy = (
        AgentTaskRetryPolicy()
        if task_max_attempts == 1
        else AgentTaskRetryPolicy(
            owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
            max_attempts=task_max_attempts,
            retryable_failure_codes={
                AgentTransportFailureCode.UNAVAILABLE,
                AgentTransportFailureCode.TIMEOUT,
            },
        )
    )
    return RuntimePolicy(
        allow_sensitive_tools=operation == RunOperation.CONFIRM_PENDING_ACTION,
        max_retries=max(0, int(getattr(settings, "shopmind_runtime_max_retries", 0))),
        agent_task_retry_policy=task_retry_policy,
        metadata={
            "policy_source": "server_defaults",
            "operation": operation.value,
            "parallel_read_enabled": bool(
                getattr(settings, "shopmind_parallel_read_enabled", False)
            ),
            "parallel_read_max_workers": max(
                1,
                int(getattr(settings, "shopmind_parallel_read_max_workers", 1)),
            ),
        },
    )


def build_runtime_budget(settings: Any) -> RunBudget:
    """Translate optional server limits into the shared execution contract."""

    return RunBudget(
        max_duration_ms=_optional_setting(settings, "shopmind_runtime_max_duration_ms"),
        max_steps=_optional_setting(settings, "shopmind_runtime_max_steps"),
        max_tool_calls=_optional_setting(settings, "shopmind_runtime_max_tool_calls"),
        max_prompt_tokens=_optional_setting(
            settings, "shopmind_runtime_max_prompt_tokens"
        ),
        max_completion_tokens=_optional_setting(
            settings, "shopmind_runtime_max_completion_tokens"
        ),
        max_total_tokens=_optional_setting(
            settings, "shopmind_runtime_max_total_tokens"
        ),
        max_cost_usd=_optional_float_setting(
            settings, "shopmind_runtime_max_cost_usd"
        ),
    )
