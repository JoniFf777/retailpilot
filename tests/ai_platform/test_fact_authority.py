from app.ai_platform.guards import catalog_authority


def test_catalog_wins_when_evidence_contains_stale_price():
    assert catalog_authority("6299", "5999") == ("6299", True)
