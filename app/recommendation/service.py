"""Pure, deterministic SKU filtering, scoring, and SPU-deduplicated ranking."""

from __future__ import annotations

from decimal import Decimal

from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import (
    AlternativeSkuView, AvailabilityView, LaptopConstraints, Money, ProductSpecificationView,
    Recommendation, RecommendationResult, ScoreBreakdownItem,
)


RANKING_POLICY_VERSION = "shopmind.laptop-ranking.v1"
_TIER_ORDER = {"entry": 1, "i5": 2, "ryzen5": 2, "i7": 3, "ryzen7": 3, "i9": 4, "ryzen9": 4, "m2": 3, "m3": 4, "rtx4050": 3, "rtx4060": 4}


def build_laptop_recommendation(candidates: list[CatalogSkuCandidate], constraints: LaptopConstraints, request_summary: str = "") -> RecommendationResult:
    if constraints.budget_max is not None and constraints.budget_currency != "CNY":
        return RecommendationResult(outcome="clarification_required", ranking_policy_version=RANKING_POLICY_VERSION,
            request_summary=request_summary, structured_constraints=constraints, missing_fields=["budget_currency"],
            clarification_question="Phase 1 only supports CNY catalog pricing; please provide a CNY budget.")

    scored = [_score(candidate, constraints) for candidate in candidates]
    eligible = [item for item in scored if item[1] is not None]
    if not eligible:
        return RecommendationResult(outcome="no_match", ranking_policy_version=RANKING_POLICY_VERSION,
            request_summary=request_summary, structured_constraints=constraints,
            no_match_reason="No active in-stock SKU satisfies the requested hard constraints.")
    eligible.sort(key=lambda item: (-item[1], item[0].money_amount, item[0].sku_code))
    winners: list[tuple[CatalogSkuCandidate, int, list[ScoreBreakdownItem], list[str]]] = []
    seen_products = set()
    for candidate, score, breakdown, matched in eligible:
        if candidate.product_id not in seen_products:
            winners.append((candidate, score, breakdown, matched))
            seen_products.add(candidate.product_id)
        if len(winners) == 3:
            break
    recommendations = [_to_recommendation(candidate, score, breakdown, matched, eligible) for candidate, score, breakdown, matched in winners]
    return RecommendationResult(outcome="recommended", ranking_policy_version=RANKING_POLICY_VERSION,
        request_summary=request_summary, structured_constraints=constraints, recommendations=recommendations)


def _number(candidate: CatalogSkuCandidate, code: str) -> Decimal | None:
    value = candidate.attributes.get(code)
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def _tier(value: object) -> int:
    return _TIER_ORDER.get(str(value).replace(" ", "").lower(), 0)


def _score(candidate: CatalogSkuCandidate, constraints: LaptopConstraints) -> tuple[CatalogSkuCandidate, int | None, list[ScoreBreakdownItem], list[str]]:
    if constraints.budget_max is not None and candidate.money_amount > constraints.budget_max:
        return candidate, None, [], []
    hard_fields = (("memory_min_gb", "memory_gb", lambda a, b: a >= b), ("storage_min_gb", "storage_gb", lambda a, b: a >= b), ("weight_max_kg", "weight_kg", lambda a, b: a <= b))
    for constraint_name, attribute, predicate in hard_fields:
        expected = getattr(constraints, constraint_name)
        actual = _number(candidate, attribute)
        if expected is not None and (actual is None or not predicate(actual, Decimal(str(expected)))):
            return candidate, None, [], []
    for constraint_name, attribute in (("cpu_tier_min", "cpu_tier"), ("gpu_tier_min", "gpu_tier")):
        expected = getattr(constraints, constraint_name)
        if expected is not None and _tier(candidate.attributes.get(attribute)) < _tier(expected):
            return candidate, None, [], []
    if constraints.screen_inches is not None and _number(candidate, "screen_inches") != constraints.screen_inches:
        return candidate, None, [], []
    breakdown = [ScoreBreakdownItem(code="base", name="Eligible SKU", points=50, max_points=50, reason="All hard constraints passed.")]
    matched = ["availability"]
    for code, constraint_name, label in (("memory_gb", "memory_min_gb", "Memory"), ("storage_gb", "storage_min_gb", "Storage")):
        if getattr(constraints, constraint_name) is not None:
            breakdown.append(ScoreBreakdownItem(code=code, name=label, points=10, max_points=10, reason="Meets requested minimum."))
            matched.append(constraint_name)
    preference_points = min(30, 10 * len(set(constraints.primary_use_cases) & set(candidate.attributes.get("use_cases", []))))
    breakdown.append(ScoreBreakdownItem(code="use_cases", name="Use cases", points=preference_points, max_points=30, reason="Matches declared primary uses."))
    return candidate, sum(item.points for item in breakdown), breakdown, matched


def _specification_value(
    value: object,
    definition: CatalogAttributeDefinition,
) -> str | int | bool | list[str]:
    """Validate and normalize a declared catalog attribute for the public contract."""

    if definition.data_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{definition.code} must be a boolean")
        return value
    if definition.data_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{definition.code} must be an integer")
        return value
    if definition.data_type == "decimal":
        if isinstance(value, bool):
            raise ValueError(f"{definition.code} must be a decimal")
        return format(Decimal(str(value)).normalize(), "f")
    if definition.data_type == "string_list":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{definition.code} must be a string list")
        return value
    return str(value)


def _specifications(candidate: CatalogSkuCandidate) -> list[ProductSpecificationView]:
    """Expose only fields declared by AttributeDefinition, in catalog order."""

    result: list[ProductSpecificationView] = []
    for definition in candidate.attribute_definitions:
        source = (
            candidate.product_attributes
            if definition.scope == "spu"
            else candidate.variant_attributes
        )
        if definition.code not in source:
            continue
        result.append(
            ProductSpecificationView(
                code=definition.code,
                name=definition.name,
                value_type=definition.data_type,
                value=_specification_value(source[definition.code], definition),
                unit=definition.unit,
                comparable=definition.comparable,
                display_order=definition.display_order,
            )
        )
    return result


def _availability(candidate: CatalogSkuCandidate) -> AvailabilityView:
    return AvailabilityView(sale_status="active", available_quantity=candidate.available_quantity, in_stock=candidate.available_quantity > 0)


def _differing_specifications(
    primary: CatalogSkuCandidate,
    alternative: CatalogSkuCandidate,
) -> list[ProductSpecificationView]:
    primary_specs = {spec.code: spec for spec in _specifications(primary)}
    return [
        spec
        for spec in _specifications(alternative)
        if spec.code not in primary_specs or spec.value != primary_specs[spec.code].value
    ]


def _to_recommendation(candidate: CatalogSkuCandidate, score: int, breakdown: list[ScoreBreakdownItem], matched: list[str], eligible: list[tuple[CatalogSkuCandidate, int, list[ScoreBreakdownItem], list[str]]]) -> Recommendation:
    alternatives = []
    for other, _, _, _ in eligible:
        if other.product_id == candidate.product_id and other.sku_id != candidate.sku_id:
            alternatives.append(AlternativeSkuView(sku_id=other.sku_id, sku_code=other.sku_code, sku_name=other.sku_name,
                money=Money(amount=str(other.money_amount), currency=other.currency), differing_specifications=_differing_specifications(candidate, other), availability=_availability(other)))
    return Recommendation(product_id=candidate.product_id, sku_id=candidate.sku_id, product_name=candidate.product_name,
        sku_name=candidate.sku_name, money=Money(amount=str(candidate.money_amount), currency=candidate.currency),
        specifications=_specifications(candidate), score=score, score_breakdown=breakdown, matched_hard_constraints=matched,
        reason="Deterministic catalog ranking after hard-constraint filtering.", availability=_availability(candidate), alternative_skus=alternatives)
