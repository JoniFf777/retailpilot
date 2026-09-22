from decimal import Decimal
from uuid import uuid4

import pytest

from agents.shopmind_multi_agent.graph import invoke_shopmind_multi_agent
from app.recommendation.categories import (
    CategoryRegistry,
    StructuredRecommendationExtraction,
)
from app.recommendation.categories.models import CategoryDefinition
from app.recommendation.constraints import evaluate_constraint, normalize_constraint
from app.recommendation.gate import classify_recommendation_request
from app.recommendation.providers import (
    FakeCatalogCandidateProvider,
    FakeRecommendationPreferenceProvider,
)
from app.recommendation.rag import FakeRecommendationEvidenceProvider
from app.recommendation.request import (
    parse_recommendation_request,
    parse_structured_extraction,
)
from app.recommendation.service import build_recommendation
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import (
    CategoryAttributeConstraint,
    RecommendationRequest,
)


def accessory_registry() -> CategoryRegistry:
    return CategoryRegistry(
        [
            CategoryDefinition.model_validate(
                {
                    "code": "test_accessory",
                    "display_name": "测试配件",
                    "aliases": ["accessory", "配件测试"],
                    "definition_version": "test",
                    "display_fields": ["battery_wh", "connection", "waterproof"],
                    "attributes": [
                        {
                            "key": "battery_wh",
                            "label": "电池容量",
                            "type": "number",
                            "unit": "Wh",
                            "aliases": ["battery", "battery_wh"],
                            "allowed_operators": ["gte", "eq"],
                            "default_operator": "gte",
                            "role": "hard",
                            "ranking": "higher_is_better",
                            "missing": "reject_if_hard",
                            "required": True,
                            "weight": 20,
                            "bounds": {"minimum": 10, "maximum": 100},
                            "display_order": 10,
                            "comparable": True,
                        },
                        {
                            "key": "connection",
                            "label": "连接方式",
                            "type": "enum",
                            "enum_values": ["wired", "wireless"],
                            "allowed_operators": ["enum_match", "eq"],
                            "role": "soft",
                            "ranking": "preference_match",
                            "missing": "neutral",
                            "weight": 20,
                            "display_order": 20,
                            "comparable": True,
                        },
                        {
                            "key": "waterproof",
                            "label": "防水",
                            "type": "boolean",
                            "allowed_operators": ["eq"],
                            "role": "soft",
                            "ranking": "exact_match",
                            "missing": "deterministic_penalty",
                            "missing_penalty": "0.25",
                            "weight": 10,
                            "display_order": 30,
                            "comparable": True,
                        },
                    ],
                }
            )
        ]
    )


def accessory_candidate(
    code: str, *, battery: int, connection: str, waterproof: bool | None, price: str
) -> CatalogSkuCandidate:
    return CatalogSkuCandidate(
        product_id=uuid4(),
        product_code=f"ACC-{code}",
        product_name=f"Accessory {code}",
        brand="Test",
        sku_id=uuid4(),
        sku_code=code,
        sku_name=code,
        money_amount=Decimal(price),
        currency="CNY",
        product_attributes={
            "battery_wh": battery,
            "connection": connection,
            "waterproof": waterproof,
        },
        attribute_definitions=[
            CatalogAttributeDefinition(
                code="battery_wh",
                name="Battery",
                scope="spu",
                data_type="integer",
                unit="Wh",
                comparable=True,
                display_order=10,
            ),
            CatalogAttributeDefinition(
                code="connection",
                name="Connection",
                scope="spu",
                data_type="string",
                comparable=True,
                display_order=20,
            ),
            CatalogAttributeDefinition(
                code="waterproof",
                name="Waterproof",
                scope="spu",
                data_type="boolean",
                comparable=True,
                display_order=30,
            ),
        ],
        available_quantity=5,
    )


def test_registry_is_deterministic_and_fails_fast() -> None:
    registry = accessory_registry()
    assert registry.resolve_code_or_alias(" ACCESSORY ") == "test_accessory"
    assert [item.code for item in registry.supported_categories()] == ["test_accessory"]
    with pytest.raises(ValueError, match="conflicting"):
        CategoryRegistry(
            [
                CategoryDefinition.model_validate(
                    {
                        "code": "a",
                        "display_name": "A",
                        "aliases": ["same"],
                        "definition_version": "1",
                    }
                ),
                CategoryDefinition.model_validate(
                    {
                        "code": "b",
                        "display_name": "B",
                        "aliases": ["same"],
                        "definition_version": "1",
                    }
                ),
            ]
        )


def test_test_accessory_proves_schema_driven_resolution_validation_filter_rank_projection() -> (
    None
):
    registry = accessory_registry()
    request = RecommendationRequest(
        category="test_accessory",
        budget_max=Decimal("100"),
        budget_currency="CNY",
        category_attributes={
            "battery_wh": CategoryAttributeConstraint(
                value=20, operator="gte", role="hard"
            ),
            "connection": CategoryAttributeConstraint(
                value="wireless", operator="enum_match", role="soft"
            ),
            "waterproof": CategoryAttributeConstraint(
                value=True, operator="eq", role="soft"
            ),
        },
    )
    result = build_recommendation(
        [
            accessory_candidate(
                "A", battery=60, connection="wireless", waterproof=False, price="80"
            ),
            accessory_candidate(
                "B", battery=30, connection="wired", waterproof=True, price="70"
            ),
            accessory_candidate(
                "C", battery=5, connection="wireless", waterproof=True, price="60"
            ),
        ],
        request,
        registry=registry,
    )
    assert result.outcome == "recommended"
    assert [item.sku_name for item in result.recommendations] == ["A", "B"]
    assert [field.key for field in result.recommendations[0].comparison_fields] == [
        "battery_wh",
        "connection",
        "waterproof",
    ]
    assert result.recommendations[0].sku_id
    assert "battery_wh" not in "".join(
        path.read_text(encoding="utf-8")
        for path in (
            __import__("pathlib").Path("app/recommendation/request.py"),
            __import__("pathlib").Path("app/recommendation/constraints.py"),
            __import__("pathlib").Path("app/recommendation/ranking.py"),
        )
    )


def test_unknown_cross_category_and_invalid_values_fail_closed() -> None:
    registry = accessory_registry()
    for attributes in (
        {"not_declared": {"value": 1, "operator": "gte", "role": "hard"}},
        {"battery_wh": {"value": "not-a-number", "operator": "gte", "role": "hard"}},
    ):
        request = RecommendationRequest(
            category="test_accessory", category_attributes=attributes
        )
        result = build_recommendation([], request, registry=registry)
        assert result.outcome == "clarification_required"
        assert result.error_code == "invalid_category_attribute"


def test_structured_extraction_is_registry_validated() -> None:
    registry = accessory_registry()
    extraction = StructuredRecommendationExtraction.model_validate(
        {
            "category_candidates": [{"code": "accessory", "confidence": 1}],
            "attributes": {
                "battery_wh": {"value": 40, "operator": "gte", "role": "hard"}
            },
        }
    )
    decision = classify_recommendation_request(
        "recommend an accessory", structured_extraction=extraction, registry=registry
    )
    request = parse_structured_extraction(extraction, registry=registry)
    assert decision.category == "test_accessory"
    assert request.category == "test_accessory"
    assert request.category_attributes["battery_wh"].value == Decimal("40")


def test_test_accessory_uses_the_same_graph_path() -> None:
    registry = accessory_registry()
    candidate = accessory_candidate(
        "GRAPH-A", battery=60, connection="wireless", waterproof=True, price="80"
    )
    result = invoke_shopmind_multi_agent(
        "recommend accessory",
        catalog_candidate_provider=FakeCatalogCandidateProvider([candidate]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
        recommendation_registry=registry,
    )
    assert result["recommendation"]["category"] == "test_accessory"
    assert result["recommendation"]["recommendations"][0]["sku_id"] == str(
        candidate.sku_id
    )


def test_generic_operator_matrix_and_missing_semantics() -> None:
    number = CategoryDefinition.model_validate(
        {
            "code": "number_category",
            "display_name": "Number",
            "definition_version": "1",
            "attributes": [
                {
                    "key": "value",
                    "label": "Value",
                    "type": "number",
                    "allowed_operators": ["eq", "gte", "lte"],
                    "role": "soft",
                    "ranking": "higher_is_better",
                    "missing": "neutral",
                    "bounds": {"minimum": 0, "maximum": 100},
                }
            ],
        }
    ).attribute_for("value")
    text = CategoryDefinition.model_validate(
        {
            "code": "string_category",
            "display_name": "String",
            "definition_version": "1",
            "attributes": [
                {
                    "key": "value",
                    "label": "Value",
                    "type": "string",
                    "allowed_operators": ["eq", "contains", "match"],
                    "role": "soft",
                    "ranking": "exact_match",
                    "missing": "neutral",
                }
            ],
        }
    ).attribute_for("value")
    enum = CategoryDefinition.model_validate(
        {
            "code": "enum_category",
            "display_name": "Enum",
            "definition_version": "1",
            "attributes": [
                {
                    "key": "value",
                    "label": "Value",
                    "type": "enum",
                    "enum_values": ["low", "high"],
                    "allowed_operators": ["eq", "gte", "lte", "enum_match"],
                    "role": "soft",
                    "ranking": "preference_match",
                    "missing": "neutral",
                }
            ],
        }
    ).attribute_for("value")
    boolean = CategoryDefinition.model_validate(
        {
            "code": "boolean_category",
            "display_name": "Boolean",
            "definition_version": "1",
            "attributes": [
                {
                    "key": "value",
                    "label": "Value",
                    "type": "boolean",
                    "allowed_operators": ["eq"],
                    "role": "soft",
                    "ranking": "exact_match",
                    "missing": "deterministic_penalty",
                    "missing_penalty": "0.25",
                }
            ],
        }
    ).attribute_for("value")
    assert number and text and enum and boolean
    assert evaluate_constraint(
        number,
        normalize_constraint(number, {"value": 10, "operator": "gte", "role": "soft"}),
        10,
    )
    assert evaluate_constraint(
        number,
        normalize_constraint(number, {"value": 10, "operator": "lte", "role": "soft"}),
        9,
    )
    assert evaluate_constraint(
        number,
        normalize_constraint(number, {"value": 10, "operator": "eq", "role": "soft"}),
        10,
    )
    assert evaluate_constraint(
        text,
        normalize_constraint(
            text, {"value": "wire", "operator": "contains", "role": "soft"}
        ),
        "wireless",
    )
    assert evaluate_constraint(
        text,
        normalize_constraint(
            text, {"value": "wire", "operator": "match", "role": "soft"}
        ),
        "wireless",
    )
    assert evaluate_constraint(
        enum,
        normalize_constraint(
            enum, {"value": "high", "operator": "gte", "role": "soft"}
        ),
        "high",
    )
    assert evaluate_constraint(
        enum,
        normalize_constraint(
            enum, {"value": "high", "operator": "enum_match", "role": "soft"}
        ),
        ["low", "high"],
    )
    assert evaluate_constraint(
        boolean,
        normalize_constraint(
            boolean, {"value": True, "operator": "eq", "role": "soft"}
        ),
        True,
    )


@pytest.mark.parametrize(
    ("message", "budget", "memory", "weight"),
    [
        (
            "推荐笔记本，预算6000元，内存至少16GB，重量不超过1.5kg",
            Decimal("6000"),
            Decimal("16"),
            Decimal("1.5"),
        ),
        (
            "推荐笔记本，预算六千元，内存16GB，重量1.2kg",
            Decimal("6000"),
            Decimal("16"),
            Decimal("1.2"),
        ),
        (
            "推荐笔记本，预算6k，内存至少32GB，重量不超过1.5kg",
            Decimal("6000"),
            Decimal("32"),
            Decimal("1.5"),
        ),
        (
            "推荐笔记本，预算1.2w，内存至少16GB，重量不超过1.5kg",
            Decimal("12000"),
            Decimal("16"),
            Decimal("1.5"),
        ),
        (
            "推荐笔记本，预算六点五千元，内存16GB，重量1.2kg",
            Decimal("6500"),
            Decimal("16"),
            Decimal("1.2"),
        ),
        (
            "推荐笔记本，预算6000到7000元，内存至少16GB，重量不超过1.5kg",
            Decimal("7000"),
            Decimal("16"),
            Decimal("1.5"),
        ),
    ],
)
def test_recommendation_request_binds_local_numbers_and_budget_units(
    message: str, budget: Decimal, memory: Decimal, weight: Decimal
) -> None:
    request = parse_recommendation_request(message, "laptop")
    assert request.budget_max == budget
    assert request.budget_currency == "CNY"
    assert request.category_attributes["memory_min_gb"].value == memory
    assert request.category_attributes["weight_max_kg"].value == weight
    assert request.category_attributes["memory_min_gb"].normalized_value == memory
    assert request.category_attributes["memory_min_gb"].source_text
    assert request.category_attributes["memory_min_gb"].source_span is not None
    assert request.budget_source_text


def test_recommendation_request_does_not_cross_clause_for_qualitative_alias() -> None:
    request = parse_recommendation_request("推荐轻薄便携的笔记本，内存16GB", "laptop")
    assert "weight_max_kg" not in request.category_attributes
    assert request.category_attributes["memory_min_gb"].value == Decimal("16")


def test_recommendation_request_converts_storage_tb_to_catalog_gb() -> None:
    request = parse_recommendation_request("推荐一台笔记本，1TB存储", "laptop")
    assert request.category_attributes["storage_min_gb"].value == Decimal("1024")


def test_recommendation_request_preserves_exclusion_polarity() -> None:
    request = parse_recommendation_request(
        "预算6000元以内，推荐一台笔记本，不要独显", "laptop"
    )
    constraint = request.category_attributes["gpu_tier_min"]
    assert constraint.value == "rtx4050"
    assert constraint.polarity == "exclude"


def test_excluded_boolean_constraint_does_not_match_supported_value() -> None:
    registry = accessory_registry()
    request = parse_recommendation_request(
        "不支持防水", "test_accessory", registry=registry
    )
    constraint = request.category_attributes["waterproof"]
    assert constraint.value is True
    assert constraint.polarity == "exclude"
    definition = registry.schema_for("test_accessory").attribute_for("waterproof")
    assert definition is not None
    assert evaluate_constraint(definition, constraint, True) is False
    assert evaluate_constraint(definition, constraint, False) is True
