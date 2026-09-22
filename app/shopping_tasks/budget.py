"""Persistent cumulative task budget ledger helpers."""

from __future__ import annotations

from typing import Any

from .contracts import (
    MAX_INTERACTION_ROUNDS,
    MAX_MODEL_ATTEMPTS,
    MAX_PLAN_REPAIRS,
    MAX_STEP_ATTEMPTS,
    MAX_STEP_RETRIES,
)


class BudgetExceeded(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _ledger(task) -> dict[str, Any]:
    return dict(task.budget_json or {})


def reserve_step_attempt(task) -> int:
    ledger = _ledger(task)
    used = int(ledger.get("step_attempts", 0))
    limit = int(ledger.get("max_step_attempts", MAX_STEP_ATTEMPTS))
    if used >= limit:
        raise BudgetExceeded("budget_exceeded")
    used += 1
    task.budget_json = {**ledger, "step_attempts": used}
    return used


def reserve_model_attempt(task) -> int:
    ledger = _ledger(task)
    used = int(ledger.get("model_attempts", 0))
    limit = int(ledger.get("max_model_attempts", MAX_MODEL_ATTEMPTS))
    if used >= limit:
        raise BudgetExceeded("model_budget_exceeded")
    used += 1
    task.budget_json = {**ledger, "model_attempts": used}
    return used


def reserve_plan_repair(task) -> int:
    ledger = _ledger(task)
    used = int(ledger.get("plan_repairs", 0))
    if used >= int(ledger.get("max_plan_repairs", MAX_PLAN_REPAIRS)):
        raise BudgetExceeded("plan_repair_budget_exceeded")
    task.budget_json = {**ledger, "plan_repairs": used + 1}
    return used + 1


def record_interaction(task) -> int:
    ledger = _ledger(task)
    used = int(ledger.get("interaction_rounds", 0))
    if used >= int(ledger.get("max_interaction_rounds", MAX_INTERACTION_ROUNDS)):
        raise BudgetExceeded("interaction_budget_exceeded")
    task.budget_json = {**ledger, "interaction_rounds": used + 1}
    return used + 1


def record_usage(task, usage: dict[str, Any] | None) -> None:
    ledger = _ledger(task)
    usage = usage or {}
    unknown = sum(
        1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd")
        if usage.get(key) is None
    )
    task.budget_json = {
        **ledger,
        "unknown_usage": int(ledger.get("unknown_usage", 0)) + unknown,
    }


__all__ = [
    "BudgetExceeded",
    "record_interaction",
    "record_usage",
    "reserve_model_attempt",
    "reserve_plan_repair",
    "reserve_step_attempt",
]
