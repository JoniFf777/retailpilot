from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.shopping_tasks.after_sales import OrderFactEnvelope, PolicyRule, assess_after_sales
from app.shopping_tasks.bundle import solve_bundle
from app.shopping_tasks.compatibility import CompatibilityRule, resolve_compatibility
from app.shopping_tasks.contracts import SourceRef, ShoppingTaskRequest
from app.shopping_tasks.planner import build_goal, offline_plan, validate_plan
from app.shopping_tasks.repair import targeted_bundle_repair
from app.shopping_tasks.budget import BudgetExceeded, record_usage, reserve_model_attempt, reserve_step_attempt
from app.shopping_tasks.state import InvalidTaskTransition, transition_task


def ref(source: str = "catalog") -> SourceRef:
    return SourceRef(source=source, source_id="fixture", source_version="v1", verified=source != "user_reported")


def candidate(slot: str, code: str, price: str) -> dict:
    return {"sku_id": str(uuid4()), "sku_code": code, "sku_name": slot, "money_amount": price, "currency": "CNY", "available_quantity": 2}


def test_three_task_plans_are_distinct_and_validated() -> None:
    plans = {}
    for kind in ("bundle_selection", "compatibility_diagnosis", "after_sales_assessment"):
        request = ShoppingTaskRequest(kind=kind, goal_text="test")
        goal = build_goal(request)
        plan = offline_plan(goal)
        plans[kind] = [step.capability for step in plan.steps]
        assert validate_plan(plan, goal=goal) == []
    assert plans["bundle_selection"] != plans["compatibility_diagnosis"]
    assert plans["compatibility_diagnosis"] != plans["after_sales_assessment"]


def test_plan_rejects_cycle_and_write_capability() -> None:
    request = ShoppingTaskRequest(kind="bundle_selection", goal_text="test")
    plan = offline_plan(build_goal(request))
    bad_steps = list(plan.steps)
    bad_steps[0] = bad_steps[0].model_copy(update={"depends_on": [bad_steps[1].key]})
    bad_steps[1] = bad_steps[1].model_copy(update={"depends_on": [bad_steps[0].key]})
    bad_steps[-1] = bad_steps[-1].model_copy(update={"capability": "pay_now"})
    bad = plan.model_copy(update={"steps": bad_steps})
    errors = validate_plan(bad)
    assert "dependency_cycle" in errors
    assert any(error.startswith("unknown_or_write_capability") for error in errors)


def test_bundle_solver_is_bounded_and_does_not_infer_usb_c() -> None:
    laptop = candidate("laptop", "LAP-1", "4000")
    monitor = candidate("monitor", "MON-1", "1000")
    dock = candidate("dock", "DOCK-USB-C", "300")
    proposal = solve_bundle({"laptop": [laptop], "monitor": [monitor], "dock": [dock]}, [], budget="6000")
    assert proposal.outcome == "no_solution"
    assert proposal.issues == ["no_compatible_combination_in_checked_candidates"]
    assert resolve_compatibility("LAP-1", "DOCK-USB-C", []).state == "unknown"


def test_bundle_solver_limits_each_slot_to_five_and_returns_three() -> None:
    values = {slot: [candidate(slot, f"{slot}-{index}", str(100 + index)) for index in range(6)] for slot in ("laptop", "monitor", "dock")}
    rules = [CompatibilityRule(source_ref=ref(), left_sku=f"{left}-0", right_sku=f"{right}-0", state="supported", reason="fixture") for left, right in (("laptop", "dock"), ("monitor", "dock"))]
    proposal = solve_bundle(values, rules, budget="1000")
    assert proposal.search_truncated is True
    assert len(proposal.options) <= 3
    assert proposal.searched_candidates == {"laptop": 5, "monitor": 5, "dock": 5}


def test_targeted_repair_excludes_only_unsupported_dock_and_keeps_locked_monitor() -> None:
    laptop = candidate("laptop", "LAP-1", "4000")
    monitor = candidate("monitor", "MON-LOCKED", "1000")
    bad_dock = candidate("dock", "DOCK-BAD", "300")
    good_dock = candidate("dock", "DOCK-GOOD", "500")
    rules = [
        CompatibilityRule(source_ref=ref(), left_sku="LAP-1", right_sku="DOCK-BAD", state="unsupported", reason="bad"),
        CompatibilityRule(source_ref=ref(), left_sku="MON-LOCKED", right_sku="DOCK-BAD", state="unsupported", reason="bad"),
        CompatibilityRule(source_ref=ref(), left_sku="LAP-1", right_sku="DOCK-GOOD", state="supported", reason="good"),
        CompatibilityRule(source_ref=ref(), left_sku="MON-LOCKED", right_sku="DOCK-GOOD", state="supported", reason="good"),
    ]
    previous = solve_bundle({"laptop": [laptop], "monitor": [monitor], "dock": [bad_dock, good_dock]}, rules, budget="6000", locked={"monitor": "MON-LOCKED"})
    repaired = targeted_bundle_repair({"laptop": [laptop], "monitor": [monitor], "dock": [bad_dock, good_dock]}, rules, previous.model_copy(update={"options": []}), budget="6000", currency="CNY", locked={"monitor": "MON-LOCKED"})
    assert repaired.outcome == "recommended"
    assert repaired.options[0].items[1].sku_code == "MON-LOCKED"
    assert repaired.options[0].items[2].sku_code == "DOCK-GOOD"


def test_after_sales_missing_delivery_and_invalid_policy_are_honest() -> None:
    order = OrderFactEnvelope(order_id="O-1", owner_id="u-1", order_status="Delivered", facts=[ref("order")])
    policy = PolicyRule(policy_type="return", region="CN", channel="online", valid_from=date.today() - timedelta(days=1), return_window_days=7, source_ref=ref("policy"))
    missing = assess_after_sales(order, policy, today=date.today())
    assert missing.outcome == "conditional"
    assert "delivered_at" in missing.missing_facts
    unavailable = assess_after_sales(order, None, today=date.today())
    assert unavailable.outcome == "unknown"
    assert "current_policy" in unavailable.missing_facts


def test_budget_is_cumulative_and_terminal_state_cannot_be_reanimated() -> None:
    task = type("Task", (), {"budget_json": {"step_attempts": 1, "max_step_attempts": 2, "model_attempts": 0, "max_model_attempts": 1}, "status": "queued", "version": 1})()
    assert reserve_step_attempt(task) == 2
    with pytest.raises(BudgetExceeded):
        reserve_step_attempt(task)
    transition_task(task, "running")
    transition_task(task, "succeeded")
    with pytest.raises(InvalidTaskTransition):
        transition_task(task, "queued")
    assert reserve_model_attempt(task) == 1
    record_usage(task, {"prompt_tokens": None, "completion_tokens": None})
    assert task.budget_json["unknown_usage"] == 4
