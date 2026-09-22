"""Deterministic combination of current store policy and owner order facts."""

from __future__ import annotations

from datetime import date
from typing import Any


def evaluate_order_policy_eligibility(
    *,
    policy: dict[str, Any] | None,
    order: dict[str, Any] | None,
    today: date,
) -> dict[str, str]:
    """Return only a bounded status; documents supply rules, orders supply facts."""

    if policy is None:
        return {"status": "policy_unavailable", "reason": "no_current_policy"}
    if order is None:
        return {"status": "needs_order_facts", "reason": "owner_order_required"}
    delivered = order.get("delivered_at")
    if not isinstance(delivered, date):
        return {"status": "needs_order_facts", "reason": "delivery_date_required"}
    window_days = int(policy.get("opened_window_days", 14))
    eligible = (today - delivered).days <= window_days and order.get("status") not in {
        "cancelled",
        "refunded",
    }
    return {
        "status": "eligible" if eligible else "ineligible",
        "reason": "current_policy_and_order_facts",
    }


__all__ = ["evaluate_order_policy_eligibility"]
