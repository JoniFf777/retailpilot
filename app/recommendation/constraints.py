"""Name-agnostic typed constraint primitives for recommendation categories."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.recommendation.categories.models import CategoryAttributeDefinition
from app.schemas.recommendation import CategoryAttributeConstraint


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("value must be numeric") from exc
    if not result.is_finite():
        raise ValueError("value must be finite")
    return result


def _normalize_text(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def normalize_constraint(
    definition: CategoryAttributeDefinition,
    raw: Any,
) -> CategoryAttributeConstraint:
    if isinstance(raw, CategoryAttributeConstraint):
        constraint = raw
    elif isinstance(raw, dict) and "value" in raw:
        constraint = CategoryAttributeConstraint.model_validate(raw)
    else:
        operator = definition.default_operator or definition.allowed_operators[0]
        constraint = CategoryAttributeConstraint(value=raw, operator=operator)
    role = constraint.role or definition.role
    if definition.role == "hard_or_soft" and constraint.role is None:
        raise ValueError(
            f"attribute {definition.key} requires an explicit constraint role"
        )
    if role == "hard_or_soft":
        raise ValueError(
            f"attribute {definition.key} cannot use unresolved hard_or_soft role"
        )
    if constraint.operator not in definition.allowed_operators:
        raise ValueError(
            f"operator {constraint.operator} is not allowed for {definition.key}"
        )
    value = constraint.value
    if definition.type == "number":
        value = _decimal(value)
    elif definition.type == "string":
        if not isinstance(value, str):
            raise ValueError(f"{definition.key} must be a string")
        value = value.strip()
    elif definition.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{definition.key} must be a boolean")
    elif definition.type == "enum":
        values = value if definition.multi_valued else [value]
        if not isinstance(values, (list, tuple, set)):
            values = [values]
        canonical = tuple(definition.canonicalize_enum(item) for item in values)
        value = (
            list(dict.fromkeys(canonical)) if definition.multi_valued else canonical[0]
        )
    return CategoryAttributeConstraint(
        value=value,
        operator=constraint.operator,
        role=role,
        polarity=constraint.polarity,
        source_text=constraint.source_text,
        source_span=constraint.source_span,
        normalized_value=value,
    )


def validate_catalog_value(definition: CategoryAttributeDefinition, value: Any) -> None:
    values = value if definition.multi_valued else [value]
    if definition.multi_valued and not isinstance(value, (list, tuple, set)):
        raise ValueError(f"{definition.key} must be a list")
    if definition.type == "number":
        for item in values:
            _decimal(item)
    elif definition.type == "string":
        if not isinstance(value, str):
            raise ValueError(f"{definition.key} must be a string")
    elif definition.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{definition.key} must be a boolean")
    elif definition.type == "enum":
        catalog_values = value if isinstance(value, (list, tuple, set)) else values
        for item in catalog_values:
            definition.canonicalize_enum(item)


def candidate_value(
    definition: CategoryAttributeDefinition,
    attributes: dict[str, Any],
) -> Any:
    return attributes.get(definition.canonical_catalog_key)


def _ordered_enum_value(definition: CategoryAttributeDefinition, value: Any) -> int:
    canonical = definition.canonicalize_enum(value)
    return definition.enum_values.index(canonical)


def _enum_match(
    definition: CategoryAttributeDefinition, candidate: Any, requested: Any
) -> bool:
    candidate_values = set(
        candidate if isinstance(candidate, (list, tuple, set)) else [candidate]
    )
    requested_values = set(
        requested if isinstance(requested, (list, tuple, set)) else [requested]
    )
    candidate_canonical = {
        definition.canonicalize_enum(item) for item in candidate_values
    }
    requested_canonical = {
        definition.canonicalize_enum(item) for item in requested_values
    }
    return requested_canonical <= candidate_canonical


def _evaluate_constraint_inclusion(
    definition: CategoryAttributeDefinition,
    constraint: CategoryAttributeConstraint,
    candidate: Any,
) -> bool:
    if candidate is None:
        return False
    operator = constraint.operator
    requested = constraint.value
    try:
        if definition.type == "number":
            actual = _decimal(candidate)
            expected = _decimal(requested)
            if operator == "eq":
                return actual == expected
            if operator == "gte":
                return actual >= expected
            if operator == "lte":
                return actual <= expected
        if definition.type == "string":
            actual_text = _normalize_text(candidate)
            expected_text = _normalize_text(requested)
            if operator == "eq":
                return actual_text == expected_text
            if operator == "contains":
                return expected_text in actual_text
            if operator == "match":
                return bool(re.search(re.escape(expected_text), actual_text))
        if definition.type == "boolean" and operator == "eq":
            return candidate is requested
        if definition.type == "enum":
            if operator == "enum_match":
                return _enum_match(definition, candidate, requested)
            if operator == "eq":
                candidate_values = (
                    candidate
                    if isinstance(candidate, (list, tuple, set))
                    else [candidate]
                )
                return any(
                    definition.canonicalize_enum(item)
                    == definition.canonicalize_enum(requested)
                    for item in candidate_values
                )
            candidate_values = (
                candidate if isinstance(candidate, (list, tuple, set)) else [candidate]
            )
            actual_orders = [
                _ordered_enum_value(definition, item) for item in candidate_values
            ]
            expected_order = _ordered_enum_value(definition, requested)
            if operator == "gte":
                return any(
                    actual_order >= expected_order for actual_order in actual_orders
                )
            if operator == "lte":
                return any(
                    actual_order <= expected_order for actual_order in actual_orders
                )
    except (ValueError, TypeError, InvalidOperation):
        return False
    return False


def evaluate_constraint_status(
    definition: CategoryAttributeDefinition,
    constraint: CategoryAttributeConstraint,
    candidate: Any,
) -> Literal["match", "mismatch", "unknown"]:
    """Return tri-state evidence for a constraint.

    Missing and malformed catalog values are unknown.  They must not be
    mistaken for proof that an exclusion matched (or that an inclusion failed)
    and are therefore kept visible to diagnostics and later evidence checks.
    """

    if candidate is None:
        return "unknown"
    try:
        validate_catalog_value(definition, candidate)
        matched = _evaluate_constraint_inclusion(definition, constraint, candidate)
    except (ValueError, TypeError, InvalidOperation):
        return "unknown"
    if constraint.polarity == "exclude":
        matched = not matched
    return "match" if matched else "mismatch"


def evaluate_constraint(
    definition: CategoryAttributeDefinition,
    constraint: CategoryAttributeConstraint,
    candidate: Any,
) -> bool:
    """Evaluate an include or exclude constraint without changing old callers."""

    return evaluate_constraint_status(definition, constraint, candidate) == "match"


def preference_signal(
    definition: CategoryAttributeDefinition,
    constraint: CategoryAttributeConstraint,
    candidate: Any,
) -> Decimal:
    if candidate is None:
        return Decimal("0.5")
    if definition.type == "enum" and constraint.operator == "enum_match":
        candidate_values = {
            definition.canonicalize_enum(item)
            for item in (
                candidate if isinstance(candidate, (list, tuple, set)) else [candidate]
            )
        }
        requested_values = {
            definition.canonicalize_enum(item)
            for item in (
                constraint.value
                if isinstance(constraint.value, (list, tuple, set))
                else [constraint.value]
            )
        }
        if not requested_values:
            return Decimal("0.5")
        overlap = Decimal(len(candidate_values & requested_values)) / Decimal(
            len(requested_values)
        )
        return Decimal("1") - overlap if constraint.polarity == "exclude" else overlap
    return (
        Decimal("1")
        if evaluate_constraint(definition, constraint, candidate)
        else Decimal("0")
    )


def parse_laptop_constraints(message: str):
    """Deprecated released-test adapter; extraction remains schema-guided."""

    from app.recommendation.compatibility import laptop_constraints_from_request
    from app.recommendation.request import parse_recommendation_request

    return laptop_constraints_from_request(
        parse_recommendation_request(message, "laptop")
    )
