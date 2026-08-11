from decimal import Decimal
from uuid import uuid4

from agents.shopmind_multi_agent.graph import invoke_shopmind_multi_agent
from app.recommendation.providers import (
    FakeCatalogCandidateProvider,
    FakeRecommendationPreferenceProvider,
)
from app.recommendation.rag import (
    FakeRecommendationEvidenceProvider,
    RecommendationEvidence,
)
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import EvidenceView, RecommendationResult


def _candidate(code: str, *, price: str, use_cases: list[str]) -> CatalogSkuCandidate:
    return CatalogSkuCandidate(
        product_id=uuid4(), product_code=f"P-{code}", product_name=f"Laptop {code}",
        brand="Test", sku_id=uuid4(), sku_code=code, sku_name=code,
        money_amount=Decimal(price), currency="CNY", available_quantity=4,
        product_attributes={"memory_gb": 16, "storage_gb": 512, "use_cases": use_cases, "internal": "hidden"},
        attribute_definitions=[
            CatalogAttributeDefinition(code="memory_gb", name="Memory", scope="spu", data_type="integer", unit="GB", comparable=True, display_order=10),
            CatalogAttributeDefinition(code="storage_gb", name="Storage", scope="spu", data_type="integer", unit="GB", comparable=True, display_order=20),
            CatalogAttributeDefinition(code="use_cases", name="Use cases", scope="spu", data_type="string_list", display_order=30),
        ],
    )


def test_structured_laptop_graph_uses_catalog_top_k_before_exact_rag() -> None:
    first = _candidate("LAP-A", price="4999", use_cases=["java_development"])
    second = _candidate("LAP-B", price="5599", use_cases=["office"])
    candidates = FakeCatalogCandidateProvider([second, first])
    evidence = FakeRecommendationEvidenceProvider(
        RecommendationEvidence(
            product_evidence={"LAP-A": [EvidenceView(source="product_rag", type="product_document", field="document_excerpt", value="safe", ref="doc-1")]},
            policy_evidence=[], diagnostics={"product_document_count": 1},
        )
    )
    result = invoke_shopmind_multi_agent(
        "预算 6000 元以内，推荐一台用于 Java 开发的笔记本，内存至少 16GB",
        catalog_candidate_provider=candidates,
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=evidence,
    )

    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert candidates.calls == 1
    assert evidence.calls == [["LAP-A", "LAP-B"]]
    assert [item.sku_id for item in recommendation.recommendations] == [first.sku_id, second.sku_id]
    assert recommendation.recommendations[0].evidence[0].source == "product_rag"
    assert [spec.code for spec in recommendation.recommendations[0].specifications] == ["memory_gb", "storage_gb", "use_cases"]
    assert "internal" not in str(recommendation.model_dump())
    assert result["raw_result"]["agent_steps"][-1]["node"] == "recommendation_decision"


def test_incomplete_laptop_request_returns_structured_clarification_without_rag() -> None:
    evidence = FakeRecommendationEvidenceProvider()
    result = invoke_shopmind_multi_agent(
        "推荐一台笔记本",
        catalog_candidate_provider=FakeCatalogCandidateProvider([_candidate("LAP-A", price="4999", use_cases=[])]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=evidence,
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "clarification_required"
    assert evidence.calls == []
