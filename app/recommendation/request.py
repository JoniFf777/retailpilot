"""Schema-guided, category-independent recommendation request extraction."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.recommendation.categories import (
    CategoryRegistry,
    StructuredRecommendationExtraction,
    default_category_registry,
)
from app.recommendation.categories.models import CategoryAttributeDefinition
from app.recommendation.categories.registry import alias_in_text
from app.recommendation.constraints import normalize_constraint
from app.schemas.recommendation import (
    CategoryAttributeConstraint,
    RecommendationRequest,
)


_AMOUNT_TOKEN = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二两三四五六七八九]+)?)"
_BUDGET_MARKED = re.compile(
    rf"(?:预算|budget|price|价格)\s*(?:(?P<currency_before>CNY|JPY|RMB|人民币|元|￥|¥)\s*)?"
    rf"(?:为|是|不超过|以内|最多|至多|上限)?\s*"
    rf"(?P<amount>{_AMOUNT_TOKEN})\s*(?P<scale>[kKwW千百千万亿])?\s*"
    rf"(?P<currency>CNY|JPY|RMB|人民币|元|￥|¥)?",
    re.IGNORECASE,
)
_BUDGET_CURRENCY = re.compile(
    rf"(?P<amount>{_AMOUNT_TOKEN})\s*(?P<scale>[kKwW千百千万亿])?\s*"
    rf"(?P<currency>CNY|JPY|RMB|人民币|元|￥|¥)",
    re.IGNORECASE,
)
_BUDGET_RANGE = re.compile(
    rf"(?:预算|budget|price|价格)\s*(?:为|是|在)?\s*"
    rf"(?P<lower>{_AMOUNT_TOKEN})\s*(?P<lower_scale>[kKwW千百千万亿])?\s*"
    rf"(?:到|至|-|~)\s*"
    rf"(?P<upper>{_AMOUNT_TOKEN})\s*(?P<upper_scale>[kKwW千百千万亿])?\s*"
    rf"(?P<currency>CNY|JPY|RMB|人民币|元|￥|¥)?",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![A-Za-z])(\d+(?:\.\d+)?)")
_EXPLICIT_CATEGORY_TOKEN = re.compile(
    r"(?:(?:推荐|想要|想买|买|需要|寻找|找)|(?:recommend|buy|need|want))\s*(?:(?:a|an|the|one|some)\s*)?(?:一[个台部款件]?\s*)?(?P<token>[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,8})",
    re.IGNORECASE,
)
_GENERIC_CATEGORY_TOKENS = {"商品", "产品", "东西", "设备", "一个", "一台", "一种"}
_NEGATION_MARKERS = (
    "不要",
    "不想",
    "不喜欢",
    "避免",
    "排除",
    "拒绝",
    "不是",
    "无",
    "不支持",
    "不需要",
)


def _chinese_amount(value: str) -> Decimal | None:
    """Parse the bounded Chinese amount forms used in shopping requests."""

    if not value or not any(
        char in "零〇一二两三四五六七八九十百千万亿" for char in value
    ):
        return None
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if "点" in value:
        integer_part, fraction_part = value.split("点", 1)
        integer = _chinese_amount(integer_part) or Decimal("0")
        trailing_scale = {"千": Decimal("1000"), "万": Decimal("10000")}.get(
            fraction_part[-1:] if fraction_part else ""
        )
        if trailing_scale is not None:
            fraction_part = fraction_part[:-1]
        if not fraction_part or any(char not in digits for char in fraction_part):
            return None
        fraction = "0." + "".join(str(digits[char]) for char in fraction_part)
        result = integer + Decimal(fraction)
        return result * trailing_scale if trailing_scale is not None else result
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in digits:
            number = digits[char]
            continue
        unit = units.get(char)
        if unit is None:
            return None
        if unit < 10000:
            section += (number or 1) * unit
        else:
            section = (section + number) * unit
            total += section
            section = 0
        number = 0
    return Decimal(total + section + number)


def _parse_amount(amount: str, scale: str | None) -> Decimal | None:
    try:
        value = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError):
        value = _chinese_amount(amount)
    if value is None:
        return None
    if scale and scale.casefold() in {"k", "千"}:
        value *= 1000
    elif scale and scale.casefold() in {"w", "万"}:
        value *= 10000
    elif scale in {"百", "亿"}:
        value *= {"百": 100, "亿": 100000000}[scale]
    return value


def _budget(message: str) -> tuple[Decimal | None, Decimal | None, str | None]:
    # A marked budget is allowed to omit the currency and defaults to CNY.
    range_match = _BUDGET_RANGE.search(message)
    if range_match is not None:
        lower = _parse_amount(
            range_match.group("lower"), range_match.group("lower_scale")
        )
        upper = _parse_amount(
            range_match.group("upper"), range_match.group("upper_scale")
        )
        if lower is not None and upper is not None and lower <= upper:
            return lower, upper, range_match.group("currency") or "CNY"
    match = _BUDGET_MARKED.search(message)
    if match is None:
        match = _BUDGET_CURRENCY.search(message)
    if match is None:
        return None, None, None
    amount = _parse_amount(match.group("amount"), match.group("scale"))
    if amount is None or amount <= 0:
        return None, None, None
    return (
        None,
        amount,
        match.group("currency") or match.group("currency_before") or "CNY",
    )


def _budget_provenance(message: str) -> tuple[str | None, tuple[int, int] | None]:
    match = (
        _BUDGET_RANGE.search(message)
        or _BUDGET_MARKED.search(message)
        or _BUDGET_CURRENCY.search(message)
    )
    if match is None:
        return None, None
    return match.group(0).strip(), (match.start(), match.end())


def _number_near_alias(
    message: str,
    aliases: tuple[str, ...],
    *,
    unit: str | None = None,
) -> Decimal | None:
    """Bind a number to the same local attribute phrase.

    The previous implementation selected the globally closest number.  That
    makes ``内存至少16GB，重量不超过1.5kg`` read as a 16kg request.  Numbers
    after an alias are preferred; a short backwards window supports forms such
    as ``16GB内存`` without crossing another attribute clause.
    """

    lowered = message.casefold()
    aliases_sorted = sorted(
        (alias for alias in aliases if alias), key=len, reverse=True
    )
    after: list[tuple[int, Decimal]] = []
    before: list[tuple[int, Decimal]] = []
    unit_pattern = {
        "GB": r"(?:GB|G|TB|T|吉(?:字节)?|太字节)",
        "kg": r"(?:kg|千克|公斤)",
        "英寸": r"(?:英寸|寸|inch|in|\")",
        "Hz": r"(?:Hz|赫兹)",
        "Wh": r"(?:Wh|瓦时)",
    }.get(unit or "")

    def candidate_number(
        fragment: str, *, preceding: bool
    ) -> tuple[int, Decimal] | None:
        matches = list(_NUMBER.finditer(fragment))
        if not matches:
            return None
        candidates = matches if preceding else matches[:1]
        for match in reversed(candidates) if preceding else candidates:
            suffix = fragment[match.end() :]
            if unit_pattern:
                if preceding:
                    suffix_text = suffix.strip()
                    if suffix_text and not re.fullmatch(
                        unit_pattern, suffix_text, re.IGNORECASE
                    ):
                        continue
                elif not re.match(rf"\s*{unit_pattern}", suffix, re.IGNORECASE):
                    continue
            try:
                distance = (len(fragment) - match.end()) if preceding else match.start()
                return distance, Decimal(match.group(1))
            except (InvalidOperation, TypeError, ValueError):
                continue
        return None

    for alias in aliases_sorted:
        for occurrence in re.finditer(re.escape(alias.casefold()), lowered):
            tail = re.split(
                r"[,，。；;\n]",
                message[occurrence.end() : occurrence.end() + 32],
                maxsplit=1,
            )[0]
            number = candidate_number(tail, preceding=False)
            if number:
                after.append(number)
            head = re.split(
                r"[,，。；;\n]",
                message[max(0, occurrence.start() - 20) : occurrence.start()][::-1],
                maxsplit=1,
            )[0][::-1]
            number = candidate_number(head, preceding=True)
            if number:
                before.append(number)
    if after:
        return min(after, key=lambda item: item[0])[1]
    if before:
        return min(before, key=lambda item: item[0])[1]
    return None


def _local_clauses_for(
    definition: CategoryAttributeDefinition, message: str
) -> list[str]:
    clauses: list[str] = []
    for alias in sorted(
        (item for item in definition.aliases if item), key=len, reverse=True
    ):
        for occurrence in re.finditer(re.escape(alias), message, re.IGNORECASE):
            start = (
                max(
                    message.rfind(separator, 0, occurrence.start())
                    for separator in (",", "，", "。", ";", "；", "\n")
                )
                + 1
            )
            end_candidates = [
                message.find(separator, occurrence.end())
                for separator in (",", "，", "。", ";", "；", "\n")
            ]
            end_candidates = [value for value in end_candidates if value >= 0]
            end = min(end_candidates, default=len(message))
            clauses.append(message[start:end].casefold())
    return clauses


def _polarity_for(definition: CategoryAttributeDefinition, message: str) -> str:
    clauses = _local_clauses_for(definition, message)
    text = " ".join(clauses) or message.casefold()
    return (
        "exclude" if any(marker in text for marker in _NEGATION_MARKERS) else "include"
    )


def _operator_for(definition: CategoryAttributeDefinition, message: str) -> str:
    # Operators belong to the same clause as the attribute.  Looking at the
    # whole request makes ``刷新率至少144Hz，尺寸27英寸`` accidentally apply
    # ``gte`` to the size field as well.
    clauses = [
        clause
        for clause in _local_clauses_for(definition, message)
        if _NUMBER.search(clause)
    ]
    text = " ".join(clauses) or message.casefold()
    if (
        any(token in text for token in ("至少", "不低于", "不少于", ">=", "以上"))
        and "gte" in definition.allowed_operators
    ):
        return "gte"
    if (
        any(token in text for token in ("不超过", "以内", "最多", "至多", "<=", "以下"))
        and "lte" in definition.allowed_operators
    ):
        return "lte"
    return definition.default_operator or definition.allowed_operators[0]


def _enum_values_from_message(
    definition: CategoryAttributeDefinition,
    message: str,
) -> list[str]:
    text = message.casefold()
    found: list[str] = []
    for canonical in definition.enum_values:
        candidates = (
            canonical,
            *[
                alias
                for alias, value in definition.enum_aliases.items()
                if value == canonical
            ],
        )
        for alias in candidates:
            if not alias_in_text(text, alias):
                continue
            found.append(canonical)
            break
    return list(dict.fromkeys(found))


def _extract_attribute(
    definition: CategoryAttributeDefinition,
    message: str,
) -> CategoryAttributeConstraint | None:
    negated = False
    if definition.type == "number":
        value = _number_near_alias(message, definition.aliases, unit=definition.unit)
        if value is None:
            return None
        if definition.unit == "GB":
            # Catalog values are normalized to GB while users commonly write
            # laptop/phone storage as TB. Only convert when the unit is in the
            # same local attribute clause; unrelated numbers stay untouched.
            clauses = _local_clauses_for(definition, message)
            if any(
                re.search(r"(?:TB|T|太字节)", clause, re.IGNORECASE)
                for clause in clauses
            ):
                value *= Decimal("1024")
    elif definition.type == "enum":
        values = _enum_values_from_message(definition, message)
        if not values:
            return None
        if _polarity_for(definition, message) == "exclude" and len(values) > 1:
            # One constraint cannot safely encode mixed ``不要 A、偏好 B``
            # polarity. Leave it for a clarification/model extractor rather
            # than excluding B by accident.
            return None
        value: Any = values if definition.multi_valued else values[0]
    elif definition.type == "string":
        alias = next(
            (alias for alias in definition.aliases if alias_in_text(message, alias)),
            None,
        )
        if alias is None:
            return None
        match = re.search(
            re.escape(alias) + r"\s*[:：]?\s*([A-Za-z0-9_.-]+)", message, re.IGNORECASE
        )
        if match is None:
            return None
        value = match.group(1)
    else:
        text = message.casefold()
        aliases = definition.aliases
        clauses = _local_clauses_for(definition, message) if aliases else [text]
        clause_text = " ".join(clauses)
        false_aliases = ("否", "无", "不支持", "不需要", "false", "no")
        true_aliases = ("是", "有", "支持", "true", "yes")
        negated = any(marker in clause_text for marker in _NEGATION_MARKERS)
        if negated:
            # ``不支持防水`` means exclude products that support waterproofing;
            # the polarity applies to the positive capability value.
            value = True
        elif any(alias in clause_text for alias in false_aliases):
            value = False
        elif any(alias in clause_text for alias in true_aliases):
            value = True
        else:
            return None
    polarity = "exclude" if negated else _polarity_for(definition, message)
    clauses = _local_clauses_for(definition, message)
    source_text = clauses[0] if clauses else None
    source_span = None
    if source_text:
        start = message.casefold().find(source_text.casefold())
        if start >= 0:
            source_span = (start, start + len(source_text))
    return normalize_constraint(
        definition,
        {
            "value": value,
            "operator": _operator_for(definition, message),
            "role": None,
            "polarity": polarity,
            "source_text": source_text,
            "source_span": source_span,
        },
    )


def parse_recommendation_request(
    message: str,
    category: str,
    *,
    registry: CategoryRegistry | None = None,
) -> RecommendationRequest:
    """Extract a typed request by iterating the selected definition."""

    active_registry = registry or default_category_registry()
    budget_min, budget_max, budget_currency = _budget(message)
    budget_source_text, budget_source_span = _budget_provenance(message)
    attributes: dict[str, CategoryAttributeConstraint] = {}
    try:
        definition = active_registry.schema_for(category)
    except KeyError:
        return RecommendationRequest(
            category=category,
            budget_min=budget_min,
            budget_max=budget_max,
            budget_currency=budget_currency,
            budget_source_text=budget_source_text,
            budget_source_span=budget_source_span,
        )
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
        budget_min=budget_min,
        budget_max=budget_max,
        budget_currency=budget_currency,
        budget_source_text=budget_source_text,
        budget_source_span=budget_source_span,
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
    normalized = active_registry.validate_request_attributes(
        category, extraction.attributes
    )
    return RecommendationRequest(
        category=category,
        budget_min=extraction.budget_min,
        budget_max=extraction.budget_max,
        budget_currency=extraction.budget_currency,
        availability_required=extraction.availability_required,
        category_attributes=normalized,
        generic_preferences=[
            str(item)
            for constraint in normalized.values()
            if constraint.role == "soft"
            for item in (
                constraint.value
                if isinstance(constraint.value, list)
                else [constraint.value]
            )
        ],
    )


__all__ = [
    "infer_explicit_category_token",
    "parse_recommendation_request",
    "parse_structured_extraction",
]
