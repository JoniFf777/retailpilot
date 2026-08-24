"""Narrow released-contract adapters kept outside the generic engine."""

from __future__ import annotations

from decimal import Decimal

from app.schemas.recommendation import CategoryAttributeConstraint, LaptopConstraints, RecommendationRequest


def laptop_constraints_from_request(request: RecommendationRequest) -> LaptopConstraints:
    values: dict[str, object] = {
        "budget_max": request.budget_max,
        "budget_currency": request.budget_currency,
    }
    for key in (
        "memory_min_gb",
        "storage_min_gb",
        "weight_max_kg",
        "cpu_tier_min",
        "gpu_tier_min",
        "screen_inches",
    ):
        constraint = request.category_attributes.get(key)
        if isinstance(constraint, CategoryAttributeConstraint):
            values[key] = constraint.value
        elif isinstance(constraint, dict) and "value" in constraint:
            values[key] = constraint["value"]
        elif constraint is not None:
            values[key] = constraint
    primary = request.category_attributes.get("primary_use_cases")
    secondary = request.category_attributes.get("secondary_use_cases")
    values["primary_use_cases"] = _constraint_values(primary)
    values["secondary_use_cases"] = _constraint_values(secondary)
    return LaptopConstraints.model_validate(values)


def request_attributes_from_laptop_constraints(constraints: LaptopConstraints) -> dict[str, CategoryAttributeConstraint]:
    values: dict[str, CategoryAttributeConstraint] = {}
    operators = {
        "memory_min_gb": "gte",
        "storage_min_gb": "gte",
        "weight_max_kg": "lte",
        "cpu_tier_min": "gte",
        "gpu_tier_min": "gte",
        "screen_inches": "eq",
    }
    for key, operator in operators.items():
        value = getattr(constraints, key)
        if value is not None:
            values[key] = CategoryAttributeConstraint(value=value, operator=operator, role="hard")
    if constraints.primary_use_cases:
        values["primary_use_cases"] = CategoryAttributeConstraint(value=list(constraints.primary_use_cases), operator="enum_match", role="soft")
    if constraints.secondary_use_cases:
        values["secondary_use_cases"] = CategoryAttributeConstraint(value=list(constraints.secondary_use_cases), operator="enum_match", role="soft")
    return values


def structured_constraints_compatibility(request: RecommendationRequest) -> LaptopConstraints:
    """Return the released Laptop-shaped field only at the compatibility edge."""

    if request.category == "laptop":
        return laptop_constraints_from_request(request)
    return LaptopConstraints()


def _constraint_values(value: object) -> list[str]:
    if isinstance(value, CategoryAttributeConstraint):
        raw = value.value
    elif isinstance(value, dict) and "value" in value:
        raw = value["value"]
    else:
        raw = value
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [] if raw in (None, "") else [str(raw)]
