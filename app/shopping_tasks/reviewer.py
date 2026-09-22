"""Constrained reviewer merge: explanations may only tighten rule outcomes."""

from __future__ import annotations

from .contracts import VerificationIssue, VerificationReport


def merge_reviewer_supplement(
    rules: VerificationReport,
    supplement: VerificationReport | None,
) -> VerificationReport:
    """Never let a model reviewer approve a deterministic rule failure."""
    if supplement is None:
        return rules
    issues = [*rules.issues, *supplement.issues]
    if rules.status in {"rejected", "needs_input", "repairable"}:
        return rules.model_copy(update={"issues": issues, "reviewer_used": True})
    status = supplement.status if supplement.status != "pass" else "pass"
    return rules.model_copy(
        update={"status": status, "issues": issues, "reviewer_used": True}
    )


__all__ = ["merge_reviewer_supplement"]
