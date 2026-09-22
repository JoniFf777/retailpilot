from datetime import datetime, timedelta, timezone

from app.recommendation.retrieval_pipeline import DisabledExternalChannel, EvidenceGate, RetrievalPipeline, SearchRequest


def test_external_channels_are_explicit_noops_by_default():
    values, statuses = RetrievalPipeline([DisabledExternalChannel("graph"), DisabledExternalChannel("web_search")]).search(
        SearchRequest(query="compatibility", evidence_type="compatibility")
    )
    assert values == []
    assert statuses == {"graph": "empty", "web_search": "empty"}


def test_evidence_gate_excludes_expired_policy():
    class PolicyChannel:
        name = "policy"

        def search(self, request):
            del request
            return [{
                "id": "old",
                "metadata": {
                    "evidence_type": "store_policy",
                    "authority": "evidence_only",
                    "policy_type": "return",
                    "valid_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                },
            }]

    values, _ = RetrievalPipeline(
        [PolicyChannel()],
        post_processors=[EvidenceGate()],
    ).search(SearchRequest(query="return", evidence_type="store_policy", policy_type="return"))
    assert values == []
