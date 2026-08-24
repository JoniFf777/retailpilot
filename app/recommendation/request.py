"""Schema-guided, category-independent recommendation request extraction."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.recommendation.categories import (
    CategoryRegistry,
    StructuredRecommendationExtraction,
    default_category_registry,
)
from app.recommendation.categories.models import CategoryAttributeDefinition
from app.recommendation.categories.registry import alias_in_text
from app.recommendation.constraints import normalize_constraint
from app.schemas.recommendation import CategoryAttributeConstraint, RecommendationRequest


_BUDGET = re.compile(
    r"(?:预算\s*)?(?:(?P<amount_after>\d+(?:\.\d+)?)\s*(?P<currency_after>CNY|JPY|RMB|人民币|元|￥|¥)|(?P<currency_before>CNY|JPY|RMB|人民币|元|￥|¥)\s*(?P<amount_before>\d+(?:\.\d+)?))",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![A-Za-z])(\d+(?:\.\d+)?)")
_EXPLICIT_CATEGORY_TOKEN = re.compile(
    r"(?:(?:推荐|想要|想买|买|需要|寻找|找)|(?:recommend|buy|need|want))\s*(?:(?:a|an|the|one|some)\s*)?(?:一[个台部款件]?\s*)?(?P<token>[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,8})",
    re.IGNORECASE,
)
_GENERIC_CATEGORY_TOKENS = {"商品", "产品", "东西", "设备", "一个", "一台", "一种"}


def _budget(message: str) -> tuple[Decimal | None, str | None]:
    match = _BUDGET.search(message)
    if match is None:
        return None, None
    amount = match.group("amount_after") or match.group("amount_before")
    currency = match.group("currency_after") or match.group("currency_before")
    return Decimal(amount), currency


def _number_near_alias(message: str, aliases: tuple[str, ...]) -> Decimal | None:
    matches = [
        (message.casefold().find(alias.casefold()), len(alias))
        for alias in aliases
        if alias and message.casefold().find(alias.casefold()) >= 0
    ]
    if not matches:
        return None
    numeric_matches = list(_NUMBER.finditer(message))
    if not numeric_matches:
        return None
    # Prefer the longest matched unit/alias so the Chinese character 寸 does
    # not steal the number from the longer 英寸 token.
    position, _ = max(matches, key=lambda item: item[1])
    match = min(numeric_matches, key=lambda item: abs(position - item.start()))
    if abs(position - match.start()) > 32:
        return None
    return Decimal(match.group(1))


def _operator_for(definition: CategoryAttributeDefinition, message: str) -> str:
    text = message.casefold()
    if any(token in text for token in ("至少", "不低于", "不少于", ">=", "以上")) and "gte" in definition.allowed_operators:
        return "gte"
    if any(token in text for token in ("不超过", "以内", "最多", "至多", "<=", "以下")) and "lte" in definition.allowed_operators:
        return "lte"
    return definition.default_operator or definition.allowed_operators[0]


def _enum_values_from_message(
    definition: CategoryAttributeDefinition,
    message: str,
) -> list[str]:
    text = message.casefold()
    found: list[str] = []
    for canonical in definition.enum_values:
        candidates = (canonical, *[alias for alias, value in definition.enum_aliases.items() if value == canonical])
        if any(alias_in_text(text, alias) for alias in candidates):
            found.append(canonical)
    return list(dict.fromkeys(found))


def _extract_attribute(
    definition: CategoryAttributeDefinition,
    message: str,
) -> CategoryAttributeConstraint | None:
    if definition.type == "number":
        value = _number_near_alias(message, definition.aliases)
        if value is None:
            return None
    elif definition.type == "enum":
        values = _enum_values_from_message(definition, message)
        if not values:
            return None
        value: Any = values if definition.multi_valued else values[0]
    elif definition.type == "string":
        alias = next((alias for alias in definition.aliases if alias_in_text(message, alias)), None)
        if alias is None:
            return None
        match = re.search(re.escape(alias) + r"\s*[:：]?\s*([A-Za-z0-9_.-]+)", message, re.IGNORECASE)
        if match is None:
            return None
        value = match.group(1)
    else:
        text = message.casefold()
        true_aliases = ("是", "有", "支持", "true", "yes")
        false_aliases = ("否", "无", "不支持", "false", "no")
        if any(alias in text for alias in true_aliases):
            value = True
        elif any(alias in text for alias in false_aliases):
            value = False
        else:
            return None
    return normalize_constraint(
        definition,
        {"value": value, "operator": _operator_for(definition, message), "role": None},
    )


def parse_recommendation_request(
    message: str,
    category: str,
    *,
    registry: CategoryRegistry | None = None,
) -> RecommendationRequest:
    """Extract a typed request by iterating the selected definition."""

    active_registry = registry or default_category_registry()
    budget_max, budget_currency = _budget(message)
    attributes: dict[str, CategoryAttributeConstraint] = {}
    try:
        definition = active_registry.schema_for(category)
    except KeyError:
        return RecommendationRequest(category=category, budget_max=budget_max, budget_currency=budget_currency)
    for attribute in definition.attributes:
        extracted = _extract_attribute(attribute, message)
        if extracted is not None:
            attributes[attribute.key] = extracted
    attribute_map = {attribute.key: attribute for attribute in definition.attributes}
    generic_preferences = [
        str(item)
        for key, constraint in attributes.items()
        if (attribute_map[key].role == "soft")
        for item in (
            constraint.value
            if isinstance(constraint.value, list)
            else [constraint.value]
        )
    ]
    return RecommendationRequest(
        category=category,
        budget_max=budget_max,
        budget_currency=budget_currency,
        generic_preferences=generic_preferences,
        category_attributes=attributes,
    )


def infer_explicit_category_token(message: str) -> str | None:
    """Extract an explicit noun/code without knowing category business names."""

    match = _EXPLICIT_CATEGORY_TOKEN.search(message)
    if match is None:
        return None
    token = match.group("token").strip()
    return None if token in _GENERIC_CATEGORY_TOKENS else token


def parse_structured_extraction(
    extraction: StructuredRecommendationExtraction,
    *,
    registry: CategoryRegistry | None = None,
) -> RecommendationRequest:
    """Validate bounded extractor output against one registry definition."""

    active_registry = registry or default_category_registry()
    resolved = {
        active_registry.resolve_code_or_alias(candidate.code) or candidate.code
        for candidate in extraction.category_candidates
        if candidate.confidence > 0
    }
    if len(resolved) != 1:
        raise ValueError("category_ambiguous")
    category = next(iter(resolved))
    normalized = active_registry.validate_request_attributes(category, extraction.attributes)
    return RecommendationRequest(
        category=category,
        budget_max=extraction.budget_max,
        budget_currency=extraction.budget_currency,
        availability_required=extraction.availability_required,
        category_attributes=normalized,
        generic_preferences=[
            str(item)
            for constraint in normalized.values()
            if constraint.role == "soft"
            for item in (constraint.value if isinstance(constraint.value, list) else [constraint.value])
        ],
    )


__all__ = [
    "infer_explicit_category_token",
    "parse_recommendation_request",
    "parse_structured_extraction",
]
