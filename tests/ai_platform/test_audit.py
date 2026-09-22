from pathlib import Path

from app.ai_platform.audit import audit_legacy_corpus


def test_current_corpus_audit_matches_updated_overview() -> None:
    root = Path("data/documents")
    report = audit_legacy_corpus(root, root / "DOCUMENTS_OVERVIEW.md")
    assert report["product_count"] >= 100
    assert report["policy_count"] == 5
    assert report["overview_drift"] is False
    assert report["duplicate_names"] == []
