from decimal import Decimal
from uuid import uuid4

from app.recommendation.gate import classify_recommendation_request
from app.recommendation.providers import FakeCatalogCandidateProvider, FakeRecommendationPreferenceProvider
from app.recommendation.rag import FakeRecommendationEvidenceProvider
from app.recommendation.request import parse_recommendation_request
from app.recommendation.service import build_monitor_recommendation, build_recommendation
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import LaptopConstraints, RecommendationRequest
from agents.shopmind_multi_agent.graph import invoke_shopmind_multi_agent


def monitor_candidate(
    sku_code: str,
    *,
    price: str,
    resolution: str,
    refresh_rate: int,
    panel_type: str = "ips",
    use_cases: list[str] | None = None,
    stock: int = 5,
    size: str = "27",
) -> CatalogSkuCandidate:
    definitions = [
        CatalogAttributeDefinition(code="size_inches", name="Screen size", scope="spu", data_type="decimal", unit="in", comparable=True, display_order=10),
        CatalogAttributeDefinition(code="resolution", name="Resolution", scope="spu", data_type="string", comparable=True, display_order=20),
        CatalogAttributeDefinition(code="refresh_rate_hz", name="Refresh rate", scope="spu", data_type="integer", unit="Hz", comparable=True, display_order=30),
        CatalogAttributeDefinition(code="panel_type", name="Panel type", scope="spu", data_type="string", comparable=True, display_order=40),
        CatalogAttributeDefinition(code="use_cases", name="Use cases", scope="spu", data_type="string_list", comparable=True, display_order=50),
    ]
    product_id = uuid4()
    return CatalogSkuCandidate(
        product_id=product_id,
        product_code=f"P-{sku_code}",
        legacy_product_id=None,
        product_name=sku_code,
        brand="Test Monitor",
        sku_id=uuid4(),
        sku_code=sku_code,
        sku_name="Standard",
        money_amount=Decimal(price),
        currency="CNY",
        product_attributes={
            "size_inches": Decimal(size),
            "resolution": resolution,
            "refresh_rate_hz": refresh_rate,
            "panel_type": panel_type,
            "use_cases": use_cases or ["office"],
        },
        variant_attributes={},
        attribute_definitions=definitions,
        available_quantity=stock,
    )


def test_category_gate_resolves_monitor_and_rejects_unsupported_or_ambiguous() -> None:
    monitor = classify_recommendation_request("推荐一台 27 英寸 4K 显示器")
    unsupported = classify_recommendation_request("推荐一部手机")
    ambiguous = classify_recommendation_request("推荐一个商品")

    assert monitor.mode == "structured_monitor_recommendation"
    assert monitor.category == "monitor"
    assert unsupported.mode == "unsupported_category"
    assert unsupported.code == "unsupported_category"
    assert ambiguous.mode == "recommendation_clarification"
    assert ambiguous.code == "category_ambiguous"


def test_monitor_request_parser_keeps_category_attributes_out_of_global_laptop_fields() -> None:
    request = parse_recommendation_request(
        "预算 4000 元，推荐 27 英寸 4K 144Hz IPS 显示器用于设计",
        "monitor",
    )

    assert request.category == "monitor"
    assert request.budget_max == Decimal("4000")
    assert request.category_attributes == {
        "size_min_inches": Decimal("27"),
        "resolution_min": "4k",
        "refresh_rate_min_hz": 144,
        "panel_type": "ips",
        "use_case": "design",
    }
    assert "memory_min_gb" not in request.category_attributes


def test_monitor_policy_filters_hard_constraints_and_ranks_soft_preferences() -> None:
    candidates = [
        monitor_candidate("MON-A", price="3000", resolution="4k", refresh_rate=144, use_cases=["design"]),
        monitor_candidate("MON-B", price="2500", resolution="4k", refresh_rate=60, use_cases=["office"]),
        monitor_candidate("MON-C", price="2000", resolution="1080p", refresh_rate=165, use_cases=["gaming"]),
        monitor_candidate("MON-OOS", price="1000", resolution="4k", refresh_rate=240, stock=0),
    ]
    request = parse_recommendation_request(
        "预算 4000 元，推荐 27 英寸 4K 144Hz IPS 显示器用于设计",
        "monitor",
    )
    result = build_monitor_recommendation(candidates, request, request_summary="monitor")

    assert result.category == "monitor"
    assert result.outcome == "recommended"
    assert [item.sku_name for item in result.recommendations] == ["Standard"]
    assert result.recommendations[0].category == "monitor"
    assert {item.code for item in result.recommendations[0].specifications} == {
        "size_inches", "resolution", "refresh_rate_hz", "panel_type", "use_cases"
    }
    assert "MON-C" not in str(result)
    assert "MON-OOS" not in str(result)


def test_monitor_missing_hard_attribute_is_no_match_and_soft_missing_is_safe() -> None:
    candidate = monitor_candidate("MON-MISSING", price="2000", resolution="4k", refresh_rate=60)
    candidate = candidate.model_copy(update={"product_attributes": {"resolution": "4k"}})
    request = RecommendationRequest(
        category="monitor",
        budget_max=Decimal("4000"),
        budget_currency="CNY",
        category_attributes={"size_min_inches": Decimal("27")},
    )

    result = build_recommendation([candidate], request, request_summary="missing size")

    assert result.outcome == "no_match"
    assert result.error_code == "no_candidates"


def test_category_ranking_is_deterministic_and_laptop_fields_do_not_bleed() -> None:
    first = monitor_candidate("MON-Z", price="2000", resolution="1440p", refresh_rate=60)
    second = monitor_candidate("MON-A", price="2000", resolution="1440p", refresh_rate=60)
    request = RecommendationRequest(
        category="monitor",
        budget_max=Decimal("3000"),
        budget_currency="CNY",
        category_attributes={"size_min_inches": Decimal("24")},
    )
    first_result = build_recommendation([first, second], request)
    second_result = build_recommendation([second, first], request)

    assert [item.product_name for item in first_result.recommendations] == ["MON-A", "MON-Z"]
    assert [item.product_name for item in first_result.recommendations] == [item.product_name for item in second_result.recommendations]

    laptop_request = RecommendationRequest(
        category="laptop",
        category_attributes={"size_min_inches": Decimal("99")},
    )
    laptop_candidate = monitor_candidate("LAP-FAKE", price="1000", resolution="1080p", refresh_rate=60)
    laptop_result = build_recommendation([laptop_candidate], laptop_request)
    assert laptop_result.category == "laptop"


def test_monitor_graph_uses_shared_path_and_returns_structured_result() -> None:
    candidates = [
        monitor_candidate("MON-GRAPH", price="2500", resolution="4k", refresh_rate=144, use_cases=["gaming"])
    ]
    result = invoke_shopmind_multi_agent(
        "预算 4000 元，推荐一台 27 英寸 4K 144Hz 显示器用于游戏",
        catalog_candidate_provider=FakeCatalogCandidateProvider(candidates),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
    )

    assert result["recommendation"]["category"] == "monitor"
    assert result["recommendation"]["recommendations"][0]["category"] == "monitor"
    assert result["raw_result"]["recommendation_diagnostics"]["category"] == "monitor"
