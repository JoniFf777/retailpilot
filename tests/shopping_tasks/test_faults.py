import pytest
from types import SimpleNamespace

from app.shopping_tasks.contracts import GoalSpec, ShoppingTaskRequest
from app.shopping_tasks import model_gateway
from app.shopping_tasks.model_gateway import (
    _chat_model,
    _coerce_plan_response,
    _coerce_review_response,
)
from app.shopping_tasks.planner import build_goal, offline_plan, validate_plan
from app.shopping_tasks.state import InvalidTaskTransition, transition_task
from app.shopping_tasks.verifier import verify_task_output
from app.shopping_tasks.reviewer import merge_reviewer_supplement
from app.shopping_tasks.repair import revise_plan_locally
from app.shopping_tasks.contracts import VerificationReport


def test_stub_fault_gate_rejects_unknown_capability_and_cycle() -> None:
    goal = build_goal(
        ShoppingTaskRequest(kind="bundle_selection", goal_text="预算 6000 元三件套")
    )
    plan = offline_plan(goal)
    steps = list(plan.steps)
    steps[0] = steps[0].model_copy(update={"depends_on": [steps[1].key]})
    steps[1] = steps[1].model_copy(
        update={"depends_on": [steps[0].key], "capability": "execute_code"}
    )
    errors = validate_plan(plan.model_copy(update={"steps": steps}))
    assert "dependency_cycle" in errors
    assert any(error.startswith("unknown_or_write_capability") for error in errors)


def test_stub_reviewer_cannot_override_budget_or_compatibility_rule() -> None:
    report = verify_task_output(
        "bundle_selection",
        {
            "bundle_proposal": {
                "outcome": "recommended",
                "constraints": {"budget": "100", "currency": "CNY"},
                "options": [
                    {
                        "total": "101",
                        "currency": "CNY",
                        "items": [{"sku_code": "A"}],
                        "compatibility": [
                            {
                                "left": "A",
                                "right": "B",
                                "state": "unsupported",
                                "reason": "rule",
                            }
                        ],
                    }
                ],
            }
        },
    )
    assert report.status != "pass"
    assert {issue.code for issue in report.issues} >= {
        "budget_exceeded",
        "compatibility_unsupported",
    }


def test_stub_cancelled_or_terminal_task_cannot_be_reactivated() -> None:
    task = type("Task", (), {"status": "queued", "version": 1})()
    transition_task(task, "cancelled")
    with pytest.raises(InvalidTaskTransition):
        transition_task(task, "queued")


def test_reviewer_cannot_approve_failed_rules_and_repair_only_invalidates_descendants() -> (
    None
):
    failed = VerificationReport(status="repairable", issues=[])
    assert (
        merge_reviewer_supplement(
            failed, VerificationReport(status="pass", issues=[])
        ).status
        == "repairable"
    )
    plan = offline_plan(
        build_goal(ShoppingTaskRequest(kind="bundle_selection", goal_text="预算 6000"))
    )
    revision = revise_plan_locally(
        plan, affected_steps={"lookup_compatibility"}, repair_count=0
    )
    assert {
        "lookup_compatibility",
        "solve_bundle",
        "verify_result",
        "compose_result",
    }.issubset(revision.invalidated_steps)


def test_model_plan_is_projected_onto_server_owned_capabilities() -> None:
    goal = GoalSpec(kind="compatibility_diagnosis", goal_text="no display")
    baseline = offline_plan(goal)
    payload = {
        "steps": [
            {
                "key": step.key,
                "capability": "untrusted-write-tool",
                "role": "coordinator",
                "depends_on": step.depends_on,
                "input_refs": step.input_refs,
            }
            for step in baseline.steps
        ],
        "endpoint": "https://untrusted.invalid",
    }

    result = _coerce_plan_response(payload, baseline=baseline, goal=goal)

    assert result.mode == "agent"
    assert [step.capability for step in result.steps] == [
        step.capability for step in baseline.steps
    ]
    assert all(step.read_only for step in result.steps)


def test_model_review_is_safely_normalized() -> None:
    result = _coerce_review_response(
        {
            "status": "repairable",
            "issues": [
                {
                    "code": "citation_gap",
                    "message": "citation missing",
                    "affected_steps": ["retrieve_evidence"],
                    "affected_artifacts": ["not-a-uuid"],
                    "owner_id": "must-not-pass-through",
                }
            ],
        }
    )

    assert result.reviewer_used is True
    assert result.issues[0].affected_steps == ["retrieve_evidence"]
    assert result.issues[0].affected_artifacts == []


def test_reasoning_extension_is_only_sent_to_openai_compatible_models(
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        model_gateway,
        "init_chat_model",
        lambda model, **kwargs: calls.append((model, kwargs)) or object(),
    )

    _chat_model(
        SimpleNamespace(model="openai:zai-org/GLM-5.3", total_timeout_ms=180_000),
        max_tokens=10,
    )
    _chat_model(
        SimpleNamespace(model="anthropic:claude-haiku-4-5", total_timeout_ms=180_000),
        max_tokens=10,
    )

    assert calls[0][1]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "extra_body" not in calls[1][1]
