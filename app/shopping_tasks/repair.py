"""Bounded business repair helpers; no hard constraint is widened."""

from __future__ import annotations

from typing import Any

from .bundle import BundleProposal, solve_bundle
from .compatibility import CompatibilityRule
from .contracts import PlanProposal, PlanRevision


def targeted_bundle_repair(
    candidates: dict[str, list[dict[str, Any]]],
    rules: list[CompatibilityRule],
    previous: BundleProposal,
    *,
    budget: Any | None,
    currency: str,
    locked: dict[str, str] | None = None,
    excluded_skus: list[str] | None = None,
) -> BundleProposal:
    """Replace only explicitly unsupported components and preserve locks."""
    locked = locked or {}
    excluded = set(excluded_skus or [])
    for option in previous.options:
        for fact in option.compatibility:
            if fact.get("state") == "unsupported":
                right = str(fact.get("right") or "")
                if right and right not in locked.values():
                    excluded.add(right)
    return solve_bundle(candidates, rules, budget=budget, currency=currency, locked=locked, excluded_skus=sorted(excluded))


__all__ = ["targeted_bundle_repair", "revise_plan_locally"]


def revise_plan_locally(
    plan: PlanProposal,
    *,
    affected_steps: set[str],
    repair_count: int,
) -> PlanRevision:
    """Invalidate affected descendants; preserve independent completed branches."""
    if repair_count >= 2:
        raise ValueError("plan_repair_budget_exceeded")
    descendants = set(affected_steps)
    changed = True
    while changed:
        changed = False
        for step in plan.steps:
            if step.key not in descendants and any(dep in descendants for dep in step.depends_on):
                descendants.add(step.key)
                changed = True
    proposal = plan.model_copy(update={"revision": plan.revision + 1, "reason": "local_repair"})
    return PlanRevision(revision=proposal.revision, parent_revision=plan.revision, proposal=proposal, repair_reason="verification_directed_repair", invalidated_steps=sorted(descendants))
