from uuid import uuid4
from decimal import Decimal

from app.recommendation.rag import RecommendationEvidence
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import EvidenceView
from evaluation.retrieval_capture import capture_retrieval_cases


def test_retrieval_capture_keeps_ids_metadata_and_failures_separate() -> None:
    candidate = CatalogSkuCandidate(
        product_id=uuid4(),
        product_code="P-1",
        product_name="P1",
        brand="B",
        sku_id=uuid4(),
        sku_code="S-1",
        sku_name="S1",
        money_amount=Decimal("1"),
        currency="CNY",
        available_quantity=1,
        product_attributes={},
        attribute_definitions=[],
    )

    class Provider:
        def retrieve(self, *, message, top_k):
            if "fail" in message:
                raise RuntimeError("private")
            return RecommendationEvidence(
                product_evidence={
                    top_k[0].sku_code: [
                        EvidenceView(
                            source="rag",
                            type="product",
                            field="x",
                            value="safe",
                            ref="doc-1",
                        )
                    ]
                },
                policy_evidence=[],
                diagnostics={"evidence_status": "available"},
            )

    report = capture_retrieval_cases(
        Provider(),
        [
            {
                "case_id": "ok",
                "message": "ok",
                "top_k": [candidate.model_dump(mode="json")],
            },
            {"case_id": "bad", "message": "fail", "top_k": []},
        ],
        code_version="test",
        model_version="fake",
        prompt_version="p1",
        config_version="c1",
    )
    assert report["case_count"] == 2
    assert report["captures"][0]["retrieved_ids"] == ["doc-1"]
    assert report["captures"][1]["execution_ok"] is False
    assert "private" not in str(report)
