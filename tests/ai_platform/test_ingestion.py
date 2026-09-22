from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_platform.contracts import EvidenceType
from app.ai_platform.ingestion import (
    ShoppingEvidencePipelineError,
    ShoppingEvidencePipeline,
    classify_legacy_source,
    load_legacy_sources,
    validate_descriptor_against_catalog,
)
from app.db.base import Base
from app.repositories.shopping_evidence import (
    list_current_evidence,
    revoke_evidence,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_legacy_sources_map_to_shopping_evidence_types() -> None:
    product = classify_legacy_source(
        "data/documents/products/TECH-LAP-001.md", "# Laptop\n\nSpecs"
    )
    policy = classify_legacy_source(
        "data/documents/policies/return_policy.md", "# Returns\n\n14 days"
    )
    compatibility = classify_legacy_source(
        "data/documents/policies/compatibility_guide.md", "# Compatibility\n\nUSB-C"
    )
    assert product.evidence_type == EvidenceType.PRODUCT_GUIDE
    assert policy.scope.policy_type == "return_policy"
    assert compatibility.evidence_type == EvidenceType.COMPATIBILITY


def test_pipeline_publishes_only_after_all_nodes_complete() -> None:
    session = make_session()
    descriptor = classify_legacy_source(
        "data/documents/products/TECH-LAP-001.md", "# Laptop\n\nBattery details"
    )
    result = ShoppingEvidencePipeline().run(
        session, descriptor, "# Laptop\n\nBattery details"
    )
    session.commit()
    current = list_current_evidence(session, product_ids=["TECH-LAP-001"])
    assert result.status == "completed"
    assert result.chunk_count == 1
    assert len(current) == 1
    assert current[0].status == "published"


def test_revoke_removes_active_publication() -> None:
    session = make_session()
    descriptor = classify_legacy_source(
        "data/documents/policies/return_policy.md", "# Returns\n\n14 days"
    )
    ShoppingEvidencePipeline().run(session, descriptor, "# Returns\n\n14 days")
    session.commit()
    assert revoke_evidence(session, descriptor.source_path)
    session.commit()
    assert list_current_evidence(session, policy_type="return_policy") == []


def test_pipeline_replays_completed_idempotent_task() -> None:
    session = make_session()
    descriptor = classify_legacy_source(
        "data/documents/products/TECH-LAP-001.md", "# Laptop\n\nBattery details"
    )
    pipeline = ShoppingEvidencePipeline()
    first = pipeline.run(session, descriptor, "# Laptop\n\nBattery details")
    second = pipeline.run(session, descriptor, "# Laptop\n\nBattery details")
    assert second.task_id == first.task_id
    assert second.evidence_version_id == first.evidence_version_id


def test_pipeline_failure_is_recorded_before_retry() -> None:
    session = make_session()
    descriptor = classify_legacy_source(
        "data/documents/products/TECH-LAP-001.md", "# Laptop\n\nBattery details"
    )
    from app.ai_platform.indexing import FakeEvidenceIndexer

    class BrokenIndexer(FakeEvidenceIndexer):
        def index(self, chunks, descriptor):
            raise ShoppingEvidencePipelineError("index_down")

    pipeline = ShoppingEvidencePipeline(BrokenIndexer())
    try:
        pipeline.run(session, descriptor, "# Laptop\n\nBattery details")
    except ShoppingEvidencePipelineError:
        pass
    else:
        raise AssertionError("pipeline should fail")
    session.flush()
    task = session.query(
        __import__(
            "app.ai_platform.models", fromlist=["ShoppingIngestionTask"]
        ).ShoppingIngestionTask
    ).one()
    assert task.status == "pending"
    assert task.last_error_code == "pipeline_failed"


def test_catalog_snapshot_rejects_unknown_product() -> None:
    descriptor = classify_legacy_source(
        "data/documents/products/TECH-LAP-001.md", "# Laptop"
    )
    try:
        validate_descriptor_against_catalog(descriptor, known_product_ids={"known"})
    except ShoppingEvidencePipelineError as error:
        assert str(error) == "dangling_product_reference"
    else:
        raise AssertionError("unknown product must fail closed")


def test_current_corpus_is_loadable() -> None:
    sources = load_legacy_sources(Path("data/documents"))
    assert len(sources) >= 100
    assert any(item.evidence_type == EvidenceType.COMPATIBILITY for item, _ in sources)
