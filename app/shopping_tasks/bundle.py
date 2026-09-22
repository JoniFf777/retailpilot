"""Deterministic bounded three-slot bundle solver."""

from __future__ import annotations

from itertools import product
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .compatibility import CompatibilityRule, resolve_compatibility


class BundleItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    slot: str
    sku_id: str
    sku_code: str
    name: str
    price: str
    currency: str
    quantity: int = Field(default=1, ge=1, le=10)
    available_quantity: int = Field(ge=0)


class BundleOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: list[BundleItem]
    total: str
    currency: str
    compatibility: list[dict[str, str]] = Field(default_factory=list)
    score: float
    evidence_refs: list[str] = Field(default_factory=list)


class BundleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: str
    options: list[BundleOption] = Field(default_factory=list, max_length=3)
    search_truncated: bool = False
    searched_candidates: dict[str, int] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


def _decimal(value: Any):
    from decimal import Decimal
    return Decimal(str(value))


def solve_bundle(
    candidates: dict[str, list[dict[str, Any]]],
    rules: list[CompatibilityRule],
    *,
    budget: Any | None = None,
    currency: str = "CNY",
    locked: dict[str, str] | None = None,
    excluded_skus: list[str] | None = None,
) -> BundleProposal:
    slots = ("laptop", "monitor", "dock")
    limited: dict[str, list[dict[str, Any]]] = {}
    truncated = False
    excluded = set(excluded_skus or [])
    for slot in slots:
        values = [item for item in candidates.get(slot, []) if item.get("sku_code") not in excluded]
        if len(values) > 5:
            truncated = True
        limited[slot] = sorted(values, key=lambda item: (str(item.get("sku_code")), str(item.get("sku_id"))))[:5]
    missing = [slot for slot in slots if not limited[slot]]
    if missing:
        return BundleProposal(outcome="needs_information" if any(candidates.get(slot) for slot in missing) else "no_solution", search_truncated=truncated, searched_candidates={slot: len(limited[slot]) for slot in slots}, constraints={"budget": str(budget) if budget is not None else None, "currency": currency}, issues=[f"missing_candidates:{slot}" for slot in missing])
    locked = locked or {}
    for slot, sku in locked.items():
        if slot in limited:
            limited[slot] = [item for item in limited[slot] if item.get("sku_code") == sku]
    if any(not limited[slot] for slot in slots if slot in locked):
        return BundleProposal(outcome="no_solution", search_truncated=truncated, searched_candidates={slot: len(limited[slot]) for slot in slots}, constraints={"locked": locked}, issues=["locked_selection_unavailable"])
    options: list[BundleOption] = []
    for laptop, monitor, dock in product(limited["laptop"], limited["monitor"], limited["dock"]):
        items = (laptop, monitor, dock)
        if any(str(item.get("currency")) != currency for item in items):
            continue
        total = sum((_decimal(item.get("money_amount", item.get("price", "0"))) for item in items), _decimal("0"))
        if budget is not None and total > _decimal(budget):
            continue
        if any(int(item.get("available_quantity", 0)) < 1 for item in items):
            continue
        compatibility: list[dict[str, str]] = []
        valid = True
        for left, right in ((laptop, dock), (monitor, dock)):
            fact = resolve_compatibility(str(left["sku_code"]), str(right["sku_code"]), rules)
            compatibility.append({"left": fact.left_sku, "right": fact.right_sku, "state": fact.state, "reason": fact.reason, "source": fact.source_ref.source})
            if fact.state != "supported":
                valid = False
        if not valid:
            continue
        bundle_items = [BundleItem(slot=slot, sku_id=str(item["sku_id"]), sku_code=str(item["sku_code"]), name=str(item.get("sku_name") or item.get("name") or item["sku_code"]), price=f"{_decimal(item.get('money_amount', item.get('price', '0'))):.2f}", currency=currency, available_quantity=int(item.get("available_quantity", 0))) for slot, item in zip(slots, items)]
        options.append(BundleOption(items=bundle_items, total=f"{total:.2f}", currency=currency, compatibility=compatibility, score=float(total), evidence_refs=[]))
    options.sort(key=lambda option: (option.score, tuple(item.sku_code for item in option.items)))
    return BundleProposal(outcome="recommended" if options else "no_solution", options=options[:3], search_truncated=truncated, searched_candidates={slot: len(limited[slot]) for slot in slots}, constraints={"budget": str(budget) if budget is not None else None, "currency": currency, "locked": locked}, issues=[] if options else ["no_compatible_combination_in_checked_candidates"])


__all__ = ["BundleItem", "BundleOption", "BundleProposal", "solve_bundle"]
