import pytest

from app.recommendation.retrieval_pipeline import RerankPostProcessor, SearchRequest


def test_reranker_can_only_reorder_trusted_candidates():
    candidates = [{"id": "a"}, {"id": "b"}]
    processor = RerankPostProcessor(lambda _q, _items, _limit: [{"id": "b"}])
    result = processor.process(candidates, SearchRequest(query="q", evidence_type="product_guide"))
    assert [item["id"] for item in result] == ["b", "a"]


def test_reranker_unknown_id_fails_closed():
    processor = RerankPostProcessor(lambda _q, _items, _limit: [{"id": "missing"}])
    with pytest.raises(ValueError):
        processor.process([{"id": "a"}], SearchRequest(query="q", evidence_type="product_guide"))
