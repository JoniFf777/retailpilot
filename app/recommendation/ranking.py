"""Deterministic generic filtering, normalization, and ranking."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.recommendation.categories.models import CategoryAttributeDefinition, CategoryDefinition
from app.recommendation.constraints import (
    candidate_value,
    evaluate_constraint,
    preference_signal,
)
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import CategoryAttributeConstraint, ScoreBreakdownItem


@dataclass(frozen=True)
class RankedCandidate:
    candidate: CatalogSkuCandidate
    score: int
    breakdown: list[ScoreBreakdownItem]
    matched_hard: list[str]
    matched_soft: list[str]
    unmatched_soft: list[str]


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _enum_numeric(definition: CategoryAttributeDefinition, value: Any) -> Decimal:
    return Decimal(definition.enum_values.index(definition.canonicalize_enum(value)))


def _normalization_bounds(
    definition: CategoryAttributeDefinition,
    candidates: list[CatalogSkuCandidate],
) -> tuple[Decimal, Decimal] | None:
    if definition.bounds is not None:
        return definition.bounds.minimum, definition.bounds.maximum
    values: list[Decimal] = []
    for candidate in candidates:
        value = candidate_value(definition, candidate.attributes)
        if value is None:
            continue
        try:
            values.append(_enum_numeric(definition, value) if definition.type == "enum" else _decimal(value))
        except (TypeError, ValueError, ArithmeticError):
            continue
    if not values:
        return None
    return min(values), max(values)


def _intrinsic_signal(
    definition: CategoryAttributeDefinition,
    value: Any,
    candidates: list[CatalogSkuCandidate],
) -> Decimal:
    if definition.ranking == "neutral":
        return Decimal("0.5")
    if definition.ranking in {"exact_match", "preference_match"}:
        return Decimal("0.5")
    try:
        numeric = _enum_numeric(definition, value) if definition.type == "enum" else _decimal(value)
    except (TypeError, ValueError, ArithmeticError):
        return Decimal("0")
    bounds = _normalization_bounds(definition, candidates)
    if bounds is None:
        return Decimal("0.5")
    minimum, maximum = bounds
    if minimum == maximum:
        return Decimal("1")
    if definition.ranking == "higher_is_better":
        signal = (numeric - minimum) / (maximum - minimum)
    else:
        signal = (maximum - numeric) / (maximum - minimum)
    return max(Decimal("0"), min(Decimal("1"), signal))


def _missing_signal(definition: CategoryAttributeDefinition) -> Decimal | None:
    if definition.missing == "neutral":
        return Decimal("0.5")
    if definition.missing == "deterministic_penalty":
        return definition.missing_penalty or Decimal("0")
    if definition.missing == "ignore":
        return None
    return Decimal("0")


def _score_candidate(
    candidate: CatalogSkuCandidate,
    definition: CategoryDefinition,
    constraints: dict[str, CategoryAttributeConstraint],
    eligible_snapshot: list[CatalogSkuCandidate],
) -> RankedCandidate:
    breakdown: list[ScoreBreakdownItem] = []
    matched_hard: list[str] = ["availability"]
    matched_soft: list[str] = []
    unmatched_soft: list[str] = []
    weighted_total = Decimal("0")
    active_weight = Decimal("0")
    attributes = candidate.attributes
    for attribute in definition.attributes:
        value = candidate_value(attribute, attributes)
        constraint = constraints.get(attribute.key)
        role = constraint.role if constraint is not None and constraint.role is not None else attribute.role
        if role == "display_only":
            continue
        if value is None:
            signal = _missing_signal(attribute)
            if signal is None:
                continue
            reason = "缺少该字段，使用声明的缺失语义。"
        elif constraint is not None and role == "soft":
            signal = preference_signal(attribute, constraint, value)
            reason = "匹配声明的软偏好。" if signal > 0 else "未匹配声明的软偏好。"
            if signal > 0:
                matched_soft.append(attribute.key)
            else:
                unmatched_soft.append(attribute.key)
        elif constraint is not None and role == "hard":
            signal = Decimal("1")
            reason = "通过声明的硬约束。"
            matched_hard.append(attribute.key)
        else:
            signal = _intrinsic_signal(attribute, value, eligible_snapshot)
            reason = "使用声明的有界排序信号。"
        weight = attribute.weight
        active_weight += weight
        weighted_total += weight * signal
        max_points = max(1, int(weight.to_integral_value(rounding=ROUND_HALF_UP)))
        points = int((Decimal(max_points) * signal).to_integral_value(rounding=ROUND_HALF_UP))
        breakdown.append(
            ScoreBreakdownItem(
                code=attribute.key,
                name=attribute.label,
                points=max(0, min(max_points, points)),
                max_points=max_points,
                reason=reason,
            )
        )
    if active_weight == 0:
        score = 50
    else:
        score = int((Decimal("100") * weighted_total / active_weight).to_integral_value(rounding=ROUND_HALF_UP))
    return RankedCandidate(
        candidate=candidate,
        score=max(0, min(100, score)),
        breakdown=breakdown,
        matched_hard=matched_hard,
        matched_soft=matched_soft,
        unmatched_soft=unmatched_soft,
    )


def filter_candidates(
    candidates: list[CatalogSkuCandidate],
    definition: CategoryDefinition,
    constraints: dict[str, CategoryAttributeConstraint],
    *,
    budget_max: Decimal | None,
    budget_currency: str | None,
    availability_required: bool,
) -> list[CatalogSkuCandidate]:
    if budget_max is not None and budget_currency != "CNY":
        return []
    eligible: list[CatalogSkuCandidate] = []
    for candidate in candidates:
        if availability_required and candidate.available_quantity <= 0:
            continue
        if budget_max is not None and candidate.money_amount > budget_max:
            continue
        candidate_attributes = candidate.attributes
        rejected = False
        for attribute in definition.attributes:
            value = candidate_value(attribute, candidate_attributes)
            if value is None and (attribute.required or attribute.missing == "reject_if_hard"):
                rejected = True
                break
            constraint = constraints.get(attribute.key)
            if constraint is None or constraint.role not in {"hard", "hard_or_soft"}:
                continue
            if value is None or not evaluate_constraint(attribute, constraint, value):
                rejected = True
                break
        if not rejected:
            eligible.append(candidate)
    return eligible


def rank_candidates(
    candidates: list[CatalogSkuCandidate],
    definition: CategoryDefinition,
    constraints: dict[str, CategoryAttributeConstraint],
    *,
    budget_max: Decimal | None,
    budget_currency: str | None,
    availability_required: bool,
) -> list[RankedCandidate]:
    eligible = filter_candidates(
        candidates,
        definition,
        constraints,
        budget_max=budget_max,
        budget_currency=budget_currency,
        availability_required=availability_required,
    )
    ranked = [
        _score_candidate(candidate, definition, constraints, eligible)
        for candidate in eligible
    ]
    return sorted(ranked, key=lambda item: (-item.score, item.candidate.money_amount, item.candidate.sku_code))
