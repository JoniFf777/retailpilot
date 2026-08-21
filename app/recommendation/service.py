"""Pure, deterministic SKU filtering, scoring, and SPU-deduplicated ranking."""

from __future__ import annotations

from decimal import Decimal

from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import (
    AlternativeSkuView, AvailabilityView, LaptopConstraints, Money, ProductSpecificationView,
    Recommendation, RecommendationRequest, RecommendationResult, ScoreBreakdownItem,
)
from app.recommendation.request import MonitorCategoryAttributes


RANKING_POLICY_VERSION = "shopmind.laptop-ranking.v1"
MONITOR_RANKING_POLICY_VERSION = "shopmind.monitor-ranking.v1"
_TIER_ORDER = {"entry": 1, "i5": 2, "ryzen5": 2, "i7": 3, "ryzen7": 3, "i9": 4, "ryzen9": 4, "m2": 3, "m3": 4, "rtx4050": 3, "rtx4060": 4}


def build_recommendation(
    candidates: list[CatalogSkuCandidate],
    request: RecommendationRequest,
    *,
    request_summary: str = "",
) -> RecommendationResult:
    """Shared orchestration entry point for registered deterministic policies."""

    if request.category == "laptop":
        constraints = LaptopConstraints.model_validate(
            {
                **request.category_attributes,
                "budget_max": request.budget_max,
                "budget_currency": request.budget_currency,
            }
        )
        result = build_laptop_recommendation(
            candidates,
            constraints,
            request_summary=request_summary,
        )
        return result.model_copy(
            update={
                "category": "laptop",
                "recommendation_request": request,
                "category_attributes": dict(request.category_attributes),
            }
        )
    if request.category == "monitor":
        return build_monitor_recommendation(
            candidates,
            request,
            request_summary=request_summary,
        )
    return RecommendationResult(
        category="unknown",
        outcome="clarification_required",
        error_code="unsupported_category",
        ranking_policy_version=MONITOR_RANKING_POLICY_VERSION,
        request_summary=request_summary,
        structured_constraints=LaptopConstraints(),
        recommendation_request=request,
        missing_fields=["category"],
        clarification_question="当前暂不支持该商品品类，请选择笔记本或显示器。",
    )


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
    if candidate.available_quantity <= 0:
        return candidate, None, [], []
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


_MONITOR_RESOLUTION_ORDER = {"1080p": 1, "1440p": 2, "4k": 3}


def _monitor_number(candidate: CatalogSkuCandidate, code: str) -> Decimal | None:
    value = candidate.attributes.get(code)
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def _monitor_resolution(candidate: CatalogSkuCandidate) -> int:
    return _MONITOR_RESOLUTION_ORDER.get(
        str(candidate.attributes.get("resolution", "")).strip().lower(),
        0,
    )


def build_monitor_recommendation(
    candidates: list[CatalogSkuCandidate],
    request: RecommendationRequest,
    *,
    request_summary: str = "",
) -> RecommendationResult:
    """Deterministic Monitor policy behind the shared recommendation envelope."""

    attributes = MonitorCategoryAttributes.model_validate(request.category_attributes)
    if not request.category_attributes and request.budget_max is None:
        return RecommendationResult(
            category="monitor",
            outcome="clarification_required",
            error_code="insufficient_constraints",
            ranking_policy_version=MONITOR_RANKING_POLICY_VERSION,
            request_summary=request_summary,
            structured_constraints=LaptopConstraints(),
            recommendation_request=request,
            category_attributes=attributes.model_dump(exclude_none=True),
            missing_fields=["budget_or_monitor_attribute"],
            clarification_question="请补充显示器预算、尺寸、分辨率或刷新率要求。",
        )
    if request.budget_max is not None and request.budget_currency != "CNY":
        return RecommendationResult(
            category="monitor",
            outcome="clarification_required",
            error_code="budget_currency_unsupported",
            ranking_policy_version=MONITOR_RANKING_POLICY_VERSION,
            request_summary=request_summary,
            structured_constraints=LaptopConstraints(),
            recommendation_request=request,
            category_attributes=attributes.model_dump(exclude_none=True),
            missing_fields=["budget_currency"],
            clarification_question="当前显示器目录仅支持 CNY 预算，请补充人民币预算。",
        )

    scored: list[tuple[CatalogSkuCandidate, int, list[ScoreBreakdownItem], list[str]]] = []
    for candidate in candidates:
        if request.availability_required and candidate.available_quantity <= 0:
            continue
        if request.budget_max is not None and candidate.money_amount > request.budget_max:
            continue
        size = _monitor_number(candidate, "size_inches")
        if attributes.size_min_inches is not None and (
            size is None or size < attributes.size_min_inches
        ):
            continue
        resolution = _monitor_resolution(candidate)
        if attributes.resolution_min is not None and (
            resolution < _MONITOR_RESOLUTION_ORDER[attributes.resolution_min]
        ):
            continue
        refresh = _monitor_number(candidate, "refresh_rate_hz")
        if attributes.refresh_rate_min_hz is not None and (
            refresh is None or refresh < attributes.refresh_rate_min_hz
        ):
            continue

        breakdown = [
            ScoreBreakdownItem(
                code="eligible",
                name="Eligible monitor",
                points=50,
                max_points=50,
                reason="Passed category, availability, budget, and requested hard constraints.",
            )
        ]
        matched = ["availability"]
        if attributes.size_min_inches is not None:
            matched.append("size_min_inches")
        if attributes.resolution_min is not None:
            matched.append("resolution_min")
        if attributes.refresh_rate_min_hz is not None:
            matched.append("refresh_rate_min_hz")

        soft_points = 0
        panel = str(candidate.attributes.get("panel_type", "")).lower()
        if attributes.panel_type is not None:
            points = 10 if panel == attributes.panel_type else 0
            soft_points += points
            breakdown.append(
                ScoreBreakdownItem(
                    code="panel_type",
                    name="Panel preference",
                    points=points,
                    max_points=10,
                    reason=(
                        "Matches the requested panel type."
                        if points
                        else "Panel type is unavailable or does not match."
                    ),
                )
            )
        if attributes.use_case is not None:
            use_cases = candidate.attributes.get("use_cases", [])
            matches_use_case = isinstance(use_cases, list) and attributes.use_case in use_cases
            points = 15 if matches_use_case else 0
            soft_points += points
            breakdown.append(
                ScoreBreakdownItem(
                    code="use_case",
                    name="Use case",
                    points=points,
                    max_points=15,
                    reason=(
                        "Matches the requested Monitor use case."
                        if points
                        else "Use-case attribute is unavailable or does not match."
                    ),
                )
            )
        if attributes.resolution_min is None:
            points = min(10, resolution * 3)
            soft_points += points
            breakdown.append(
                ScoreBreakdownItem(
                    code="resolution",
                    name="Resolution",
                    points=points,
                    max_points=10,
                    reason="Higher declared resolution receives a bounded preference score.",
                )
            )
        score = min(100, 50 + soft_points)
        scored.append((candidate, score, breakdown, matched))

    if not scored:
        return RecommendationResult(
            category="monitor",
            outcome="no_match",
            error_code="no_candidates",
            ranking_policy_version=MONITOR_RANKING_POLICY_VERSION,
            request_summary=request_summary,
            structured_constraints=LaptopConstraints(),
            recommendation_request=request,
            category_attributes=attributes.model_dump(exclude_none=True),
            no_match_reason="没有满足显示器硬约束且仍可售的 SKU。",
        )

    scored.sort(key=lambda item: (-item[1], item[0].money_amount, item[0].sku_code))
    winners: list[tuple[CatalogSkuCandidate, int, list[ScoreBreakdownItem], list[str]]] = []
    seen_products: set[object] = set()
    for item in scored:
        if item[0].product_id in seen_products:
            continue
        winners.append(item)
        seen_products.add(item[0].product_id)
        if len(winners) == 3:
            break
    recommendations = [
        _to_recommendation(candidate, score, breakdown, matched, scored).model_copy(
            update={"category": "monitor"}
        )
        for candidate, score, breakdown, matched in winners
    ]
    return RecommendationResult(
        category="monitor",
        outcome="recommended",
        ranking_policy_version=MONITOR_RANKING_POLICY_VERSION,
        request_summary=request_summary,
        structured_constraints=LaptopConstraints(),
        recommendation_request=request,
        category_attributes=attributes.model_dump(exclude_none=True),
        recommendations=recommendations,
    )
