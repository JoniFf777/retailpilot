import time

from app.recommendation.retrieval_pipeline import (
    EvidenceGate,
    RetrievalPipeline,
    SearchRequest,
    deduplicate_candidates,
    rrf_fuse,
)


class Channel:
    def __init__(self, name, values, delay=0):
        self.name = name
        self.values = values
        self.delay = delay

    def search(self, request):
        del request
        if self.delay:
            time.sleep(self.delay)
        return [dict(value) for value in self.values]


def evidence(identifier, product_id="TECH-LAP-001"):
    return {
        "id": identifier,
        "product_id": product_id,
        "metadata": {
            "evidence_type": "product_guide",
            "product_ids": [product_id],
            "authority": "evidence_only",
        },
    }


def test_rrf_is_stable_and_deduplicates_by_identifier():
    result = rrf_fuse([[evidence("a"), evidence("b")], [evidence("b"), evidence("a")]], limit=2)
    assert [item["id"] for item in result] == ["a", "b"]
    assert len(deduplicate_candidates(result + [result[0]], SearchRequest(query="q", evidence_type="product_guide"))) == 2


def test_pipeline_keeps_success_when_one_channel_fails():
    class Broken:
        name = "broken"

        def search(self, request):
            del request
            raise TimeoutError()

    result, statuses = RetrievalPipeline([Channel("vector", [evidence("a")]), Broken()], post_processors=[EvidenceGate()]).search(
        SearchRequest(query="laptop", evidence_type="product_guide", product_ids=("TECH-LAP-001",))
    )
    assert [item["id"] for item in result] == ["a"]
    assert statuses["broken"] == "degraded"


def test_evidence_gate_rejects_cross_product_result():
    result, _ = RetrievalPipeline([Channel("vector", [evidence("wrong", "TECH-LAP-002")])]).search(
        SearchRequest(query="laptop", evidence_type="product_guide", product_ids=("TECH-LAP-001",))
    )
    assert result == []
