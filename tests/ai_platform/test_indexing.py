from app.ai_platform.ingestion import classify_legacy_source
from app.ai_platform.indexing import FakeEvidenceIndexer


def test_fake_indexer_records_business_source():
    descriptor = classify_legacy_source("data/documents/products/TECH-LAP-001.md", "# laptop")
    indexer = FakeEvidenceIndexer()
    assert indexer.index([], descriptor) == 0
    assert indexer.calls == [(descriptor.source_path, 0)]
