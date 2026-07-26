from types import SimpleNamespace

from app.runtime import RunOperation, build_runtime_budget, build_runtime_policy


def test_runtime_policy_is_deny_first_for_sensitive_tools() -> None:
    settings = SimpleNamespace(
        shopmind_runtime_max_retries=2,
        shopmind_parallel_read_enabled=True,
        shopmind_parallel_read_max_workers=2,
    )

    chat_policy = build_runtime_policy(settings, RunOperation.CHAT)
    confirmation_policy = build_runtime_policy(
        settings, RunOperation.CONFIRM_PENDING_ACTION
    )

    assert chat_policy.allow_sensitive_tools is False
    assert confirmation_policy.allow_sensitive_tools is True
    assert chat_policy.max_retries == 2
    assert chat_policy.metadata["policy_source"] == "server_defaults"
    assert chat_policy.metadata["parallel_read_enabled"] is True
    assert chat_policy.metadata["parallel_read_max_workers"] == 2
    assert chat_policy.agent_task_retry_policy.owner == "disabled"


def test_runtime_policy_builds_server_owned_bounded_task_retry() -> None:
    policy = build_runtime_policy(
        SimpleNamespace(shopmind_agent_task_max_attempts=3),
        RunOperation.CHAT,
    )

    assert policy.agent_task_retry_policy.owner == "plan_executor"
    assert policy.agent_task_retry_policy.max_attempts == 3
    assert policy.agent_task_retry_policy.retryable_failure_codes == {
        "agent.transport_unavailable",
        "agent.transport_timeout",
    }


def test_runtime_budget_uses_only_positive_server_settings() -> None:
    settings = SimpleNamespace(
        shopmind_runtime_max_duration_ms=1_500,
        shopmind_runtime_max_steps=6,
        shopmind_runtime_max_tool_calls=4,
        shopmind_runtime_max_prompt_tokens=512,
        shopmind_runtime_max_completion_tokens=256,
        shopmind_runtime_max_total_tokens=768,
        shopmind_runtime_max_cost_usd=0.25,
    )

    budget = build_runtime_budget(settings)

    assert budget.max_duration_ms == 1_500
    assert budget.max_steps == 6
    assert budget.max_tool_calls == 4
    assert budget.max_prompt_tokens == 512
    assert budget.max_completion_tokens == 256
    assert budget.max_total_tokens == 768
    assert budget.max_cost_usd == 0.25

    empty_budget = build_runtime_budget(SimpleNamespace(shopmind_runtime_max_steps=0))
    assert empty_budget.max_steps is None
