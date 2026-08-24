"""Generic deterministic recommendation orchestration and compatibility adapters."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.recommendation.categories import CategoryRegistry, default_category_registry
from app.recommendation.compatibility import (
    request_attributes_from_laptop_constraints,
    structured_constraints_compatibility,
)
from app.recommendation.ranking import RankedCandidate, rank_candidates
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import (
    AlternativeSkuView,
    AvailabilityView,
    CategoryAttributeConstraint,
    ComparisonField,
    LaptopConstraints,
    Money,
    ProductSpecificationView,
    Recommendation,
    RecommendationRequest,
    RecommendationResult,
)


RANKING_POLICY_VERSION = "shopmind.schema-ranking.v1"
MONITOR_RANKING_POLICY_VERSION = RANKING_POLICY_VERSION


def _policy_version(definition) -> str:
    return f"{RANKING_POLICY_VERSION}:{definition.code}:{definition.definition_version}"


def _empty_result(
    request: RecommendationRequest,
    *,
    definition,
    error_code: str,
    missing_fields: list[str],
    clarification_question: str,
    recognized: dict[str, CategoryAttributeConstraint] | None = None,
) -> RecommendationResult:
    return RecommendationResult(
        category=request.category,
        category_display_name=definition.display_name,
        outcome="clarification_required",
        error_code=error_code,
        ranking_policy_version=_policy_version(definition),
        request_summary="",
        structured_constraints=LaptopConstraints(),
        recommendation_request=request,
        category_attributes=dict(request.category_attributes),
        recognized_constraints=recognized or {},
        constraint_fields=_constraint_fields(definition, recognized or {}),
        missing_fields=missing_fields,
        clarification_question=clarification_question,
    )


def build_recommendation(
    candidates: list[CatalogSkuCandidate],
    request: RecommendationRequest,
    *,
    request_summary: str = "",
    registry: CategoryRegistry | None = None,
    enforce_request_minimum: bool = False,
) -> RecommendationResult:
    """Resolve definition, validate request, filter, rank, and project generically."""

    active_registry = registry or default_category_registry()
    try:
        definition = active_registry.schema_for(request.category)
    except KeyError:
        return RecommendationResult(
            category=request.category,
            outcome="clarification_required",
            error_code="unsupported_category",
            ranking_policy_version=RANKING_POLICY_VERSION,
            request_summary=request_summary,
            structured_constraints=LaptopConstraints(),
            recommendation_request=request,
            missing_fields=["category"],
            clarification_question="当前暂不支持该商品品类，请补充一个已支持的商品类别。",
        )
    try:
        normalized = active_registry.validate_request_attributes(
            request.category,
            request.category_attributes,
        )
    except ValueError as exc:
        return _empty_result(
            request,
            definition=definition,
            error_code="invalid_category_attribute",
            missing_fields=["category_attributes"],
            clarification_question=f"请补充有效的{definition.display_name}选购条件。",
        ).model_copy(update={"request_summary": request_summary})
    normalized_request = request.model_copy(update={"category_attributes": normalized})
    if (
        enforce_request_minimum
        and definition.request_requires_any
        and normalized_request.budget_max is None
        and not normalized
    ):
        return _empty_result(
            normalized_request,
            definition=definition,
            error_code="insufficient_constraints",
            missing_fields=["budget_or_category_attribute"],
            clarification_question=definition.clarification_question,
            recognized=normalized,
        ).model_copy(update={"request_summary": request_summary})
    if normalized_request.budget_max is not None and normalized_request.budget_currency != "CNY":
        return _empty_result(
            normalized_request,
            definition=definition,
            error_code="budget_currency_unsupported",
            missing_fields=["budget_currency"],
            clarification_question="当前目录仅支持 CNY 预算，请补充人民币预算。",
            recognized=normalized,
        ).model_copy(update={"request_summary": request_summary})

    ranked = rank_candidates(
        candidates,
        definition,
        normalized,
        budget_max=normalized_request.budget_max,
        budget_currency=normalized_request.budget_currency,
        availability_required=normalized_request.availability_required,
    )
    if not ranked:
        return RecommendationResult(
            category=definition.code,
            category_display_name=definition.display_name,
            outcome="no_match",
            error_code="no_candidates",
            ranking_policy_version=_policy_version(definition),
            request_summary=request_summary,
            structured_constraints=structured_constraints_compatibility(normalized_request),
            recommendation_request=normalized_request,
            category_attributes=dict(normalized),
            recognized_constraints=normalized,
            constraint_fields=_constraint_fields(definition, normalized),
            no_match_reason="没有满足硬约束且仍可售的 SKU。",
        )

    winners: list[RankedCandidate] = []
    seen_products: set[Any] = set()
    for item in ranked:
        if item.candidate.product_id in seen_products:
            continue
        winners.append(item)
        seen_products.add(item.candidate.product_id)
        if len(winners) == 3:
            break
    recommendations = [
        _to_recommendation(item, definition, ranked)
        for item in winners
    ]
    return RecommendationResult(
        category=definition.code,
        category_display_name=definition.display_name,
        outcome="recommended",
        ranking_policy_version=_policy_version(definition),
        request_summary=request_summary,
        structured_constraints=structured_constraints_compatibility(normalized_request),
        recommendation_request=normalized_request,
        category_attributes=dict(normalized),
        recognized_constraints=normalized,
        constraint_fields=_constraint_fields(definition, normalized),
        recommendations=recommendations,
        comparison_fields=recommendations[0].comparison_fields if recommendations else [],
    )


def build_laptop_recommendation(
    candidates: list[CatalogSkuCandidate],
    constraints: LaptopConstraints,
    request_summary: str = "",
) -> RecommendationResult:
    """Released Laptop API adapter; generic engine owns the actual ranking."""

    request = RecommendationRequest(
        category="laptop",
        budget_max=constraints.budget_max,
        budget_currency=constraints.budget_currency,
        category_attributes=request_attributes_from_laptop_constraints(constraints),
    )
    return build_recommendation(candidates, request, request_summary=request_summary)


def build_monitor_recommendation(
    candidates: list[CatalogSkuCandidate],
    request: RecommendationRequest,
    *,
    request_summary: str = "",
) -> RecommendationResult:
    """Released Monitor entry point retained as a thin compatibility adapter."""

    return build_recommendation(candidates, request, request_summary=request_summary)


def _catalog_value(
    candidate: CatalogSkuCandidate,
    catalog_key: str,
) -> Any:
    return candidate.attributes.get(catalog_key)


def _constraint_fields(definition, constraints: dict[str, CategoryAttributeConstraint]) -> list[ComparisonField]:
    fields: list[ComparisonField] = []
    for key, constraint in constraints.items():
        attribute = definition.attribute_for(key)
        if attribute is None:
            continue
        value = constraint.value
        if attribute.type == "number":
            decimal = Decimal(str(value))
            public_value: str | int | bool | list[str] = (
                int(decimal) if decimal == decimal.to_integral_value() else format(decimal.normalize(), "f")
            )
            value_type = "number"
        elif attribute.type == "enum":
            public_value = value if isinstance(value, list) else str(value)
            value_type = "string_list" if isinstance(public_value, list) else "enum"
        elif attribute.type == "boolean":
            public_value = bool(value)
            value_type = "boolean"
        else:
            public_value = str(value)
            value_type = "string"
        fields.append(
            ComparisonField(
                key=key,
                label=attribute.label,
                value=public_value,
                value_type=value_type,
                unit=attribute.unit,
                display_order=attribute.display_order,
                comparable=attribute.comparable,
                format_hint=attribute.format_hint,
            )
        )
    return sorted(fields, key=lambda item: (item.display_order, item.key))


def _comparison_fields(candidate: CatalogSkuCandidate, definition) -> list[ComparisonField]:
    fields: list[ComparisonField] = []
    seen_catalog_keys: set[str] = set()
    for key in definition.display_fields:
        attribute = definition.attribute_for(key)
        if attribute is None:
            continue
        catalog_key = attribute.canonical_catalog_key
        if catalog_key in seen_catalog_keys:
            continue
        value = _catalog_value(candidate, catalog_key)
        if value is None:
            continue
        seen_catalog_keys.add(catalog_key)
        if attribute.type == "number":
            decimal = Decimal(str(value))
            if decimal == decimal.to_integral_value():
                public_value: str | int | bool | list[str] = int(decimal)
            else:
                public_value = format(decimal.normalize(), "f")
            value_type = "number"
        elif attribute.type == "enum":
            raw_values = value if isinstance(value, list) else [value]
            public_values = [attribute.canonicalize_enum(item) for item in raw_values]
            if attribute.multi_valued:
                public_value = public_values
                value_type = "string_list"
            else:
                public_value = public_values[0]
                value_type = "enum"
        elif attribute.type == "boolean":
            public_value = bool(value)
            value_type = "boolean"
        else:
            public_value = str(value)
            value_type = "string"
        fields.append(
            ComparisonField(
                key=attribute.key,
                label=attribute.label,
                value=public_value,
                value_type=value_type,
                unit=attribute.unit,
                display_order=attribute.display_order,
                comparable=attribute.comparable,
                format_hint=attribute.format_hint,
            )
        )
    return sorted(fields, key=lambda item: (item.display_order, item.key))


def _specification_value(
    value: object,
    definition: CatalogAttributeDefinition,
) -> str | int | bool | list[str]:
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
    result: list[ProductSpecificationView] = []
    for definition in candidate.attribute_definitions:
        source = candidate.product_attributes if definition.scope == "spu" else candidate.variant_attributes
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
    return AvailabilityView(
        sale_status="active",
        available_quantity=candidate.available_quantity,
        in_stock=candidate.available_quantity > 0,
    )


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


def _to_recommendation(
    ranked: RankedCandidate,
    definition,
    eligible: list[RankedCandidate],
) -> Recommendation:
    candidate = ranked.candidate
    alternatives: list[AlternativeSkuView] = []
    for other in eligible:
        if other.candidate.product_id != candidate.product_id or other.candidate.sku_id == candidate.sku_id:
            continue
        other_candidate = other.candidate
        alternatives.append(
            AlternativeSkuView(
                sku_id=other_candidate.sku_id,
                sku_code=other_candidate.sku_code,
                sku_name=other_candidate.sku_name,
                money=Money(amount=str(other_candidate.money_amount), currency=other_candidate.currency),
                differing_specifications=_differing_specifications(candidate, other_candidate),
                availability=_availability(other_candidate),
            )
        )
    return Recommendation(
        category=definition.code,
        category_display_name=definition.display_name,
        product_id=candidate.product_id,
        sku_id=candidate.sku_id,
        product_name=candidate.product_name,
        sku_name=candidate.sku_name,
        money=Money(amount=str(candidate.money_amount), currency=candidate.currency),
        specifications=_specifications(candidate),
        comparison_fields=_comparison_fields(candidate, definition),
        score=ranked.score,
        score_breakdown=ranked.breakdown,
        matched_hard_constraints=ranked.matched_hard,
        matched_soft_preferences=ranked.matched_soft,
        unmatched_soft_constraints=ranked.unmatched_soft,
        reason="Deterministic catalog ranking after definition-driven hard filtering.",
        availability=_availability(candidate),
        alternative_skus=alternatives,
    )
