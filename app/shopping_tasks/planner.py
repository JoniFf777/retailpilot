"""Offline planner and server-side plan validation."""

from __future__ import annotations

from collections import defaultdict
import re

from .contracts import (
    CAPABILITIES,
    MAX_PARALLEL_STEPS,
    MAX_PLAN_STEPS,
    READ_ONLY_CAPABILITIES,
    REQUIRED_VERIFY,
    GoalSpec,
    Fact,
    PlanProposal,
    PlanStep,
    Role,
    ShoppingTaskRequest,
    SourceRef,
)


def _step(key: str, capability: str, role: Role, output_kind: str, *deps: str, refs: list[str] | None = None) -> PlanStep:
    return PlanStep(key=key, capability=capability, role=role, output_kind=output_kind, depends_on=list(deps), input_refs=refs or [])


def build_goal(request: ShoppingTaskRequest) -> GoalSpec:
    facts = list(request.known_facts)
    if request.kind == "bundle_selection" and not any(fact.key in {"budget", "total_budget"} for fact in facts):
        match = re.search(r"(?:预算|budget)\s*[:：]?\s*(\d+(?:\.\d+)?)", request.goal_text, flags=re.IGNORECASE)
        if match:
            facts.append(Fact(key="budget", value=float(match.group(1)), source_ref=SourceRef(source="derived", source_id="goal-text-budget", verified=False)))
    locked: dict[str, str] = {}
    excluded: list[str] = []
    for fact in facts:
        if fact.key.startswith("locked_") and isinstance(fact.value, str):
            locked[fact.key.removeprefix("locked_")] = fact.value
        if fact.key in {"exclude_sku", "excluded_sku"}:
            values = fact.value if isinstance(fact.value, list) else [fact.value]
            excluded.extend(str(value) for value in values if value)
    if request.kind == "bundle_selection":
        required = ["laptop", "monitor", "dock"]
        questions = []
        if not any(f.key in {"budget", "total_budget"} for f in facts):
            questions.append("total_budget")
        hard = {f.key: f.value for f in facts if f.key in {"budget", "total_budget", "currency", "quantity"}}
        soft = {f.key: f.value for f in facts if f.key not in hard}
    elif request.kind == "compatibility_diagnosis":
        required = ["device", "symptom"]
        questions = [key for key in required if not any(f.key == key for f in facts)]
        hard, soft = {}, {f.key: f.value for f in facts}
    else:
        required = ["order"]
        questions = []
        hard, soft = {}, {f.key: f.value for f in facts}
    return GoalSpec(kind=request.kind, goal_text=request.goal_text, required_slots=required, hard_constraints=hard, soft_requirements=soft, locked_selections=locked, excluded_skus=excluded, open_questions=questions, facts=facts)


def offline_plan(goal: GoalSpec) -> PlanProposal:
    if goal.kind == "bundle_selection":
        steps = [
            _step("extract_goal", "extract_goal", "coordinator", "goal_spec"),
            _step("catalog_candidates", "catalog_candidates", "catalog_analyst", "candidate_set", "extract_goal"),
            _step("lookup_compatibility", "lookup_compatibility", "catalog_analyst", "compatibility_report", "catalog_candidates"),
            _step("solve_bundle", "solve_bundle", "catalog_analyst", "bundle_proposal", "catalog_candidates", "lookup_compatibility"),
            _step("retrieve_evidence", "retrieve_evidence", "evidence_researcher", "evidence_bundle", "extract_goal"),
            _step("verify_result", "verify_result", "reviewer", "verification_report", "solve_bundle", "retrieve_evidence"),
            _step("compose_result", "compose_result", "coordinator", "task_result", "verify_result", "solve_bundle", "retrieve_evidence"),
        ]
    elif goal.kind == "compatibility_diagnosis":
        steps = [
            _step("extract_goal", "extract_goal", "coordinator", "goal_spec"),
            _step("retrieve_evidence", "retrieve_evidence", "evidence_researcher", "evidence_bundle", "extract_goal"),
            _step("suggest_diagnostic_check", "suggest_diagnostic_check", "evidence_researcher", "diagnostic_check", "extract_goal", "retrieve_evidence"),
            _step("verify_result", "verify_result", "reviewer", "verification_report", "suggest_diagnostic_check", "retrieve_evidence"),
            _step("compose_result", "compose_result", "coordinator", "task_result", "verify_result", "suggest_diagnostic_check"),
        ]
    else:
        steps = [
            _step("extract_goal", "extract_goal", "coordinator", "goal_spec"),
            _step("read_owned_order", "read_owned_order", "catalog_analyst", "order_facts", "extract_goal"),
            _step("retrieve_evidence", "retrieve_evidence", "evidence_researcher", "policy_evidence", "extract_goal"),
            _step("assess_policy", "assess_policy", "evidence_researcher", "policy_assessment", "read_owned_order", "retrieve_evidence"),
            _step("verify_result", "verify_result", "reviewer", "verification_report", "assess_policy", "retrieve_evidence"),
            _step("compose_result", "compose_result", "coordinator", "task_result", "verify_result", "assess_policy"),
        ]
    return PlanProposal(steps=steps, mode="offline")


def validate_plan(plan: PlanProposal, *, goal: GoalSpec | None = None) -> list[str]:
    errors: list[str] = []
    if len(plan.steps) > MAX_PLAN_STEPS:
        errors.append("plan_too_large")
    keys = [step.key for step in plan.steps]
    if len(set(keys)) != len(keys):
        errors.append("duplicate_step_key")
    known = set(keys)
    graph: dict[str, list[str]] = defaultdict(list)
    indegree = {key: 0 for key in keys}
    for step in plan.steps:
        if step.capability not in READ_ONLY_CAPABILITIES:
            errors.append(f"unknown_or_write_capability:{step.capability}")
        if step.capability not in CAPABILITIES[step.role]:
            errors.append(f"role_capability_mismatch:{step.key}")
        if not step.read_only:
            errors.append(f"write_step_forbidden:{step.key}")
        for dep in step.depends_on:
            if dep not in known:
                errors.append(f"missing_dependency:{step.key}:{dep}")
            else:
                graph[dep].append(step.key)
                indegree[step.key] += 1
        if goal is not None and any(ref not in known for ref in step.input_refs):
            errors.append(f"unknown_input_ref:{step.key}")
    root_count = sum(1 for degree in indegree.values() if degree == 0)
    if root_count > MAX_PARALLEL_STEPS:
        errors.append("parallel_frontier_too_large")
    queue = [key for key, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        key = queue.pop(0)
        visited += 1
        for child in graph[key]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(keys):
        errors.append("dependency_cycle")
    if REQUIRED_VERIFY not in {step.capability for step in plan.steps}:
        errors.append("verification_step_required")
    return list(dict.fromkeys(errors))


def assert_valid_plan(plan: PlanProposal, *, goal: GoalSpec | None = None) -> None:
    errors = validate_plan(plan, goal=goal)
    if errors:
        raise ValueError("invalid_plan:" + ",".join(errors))


__all__ = ["assert_valid_plan", "build_goal", "offline_plan", "validate_plan"]
