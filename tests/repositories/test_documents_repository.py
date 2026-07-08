from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Document
from app.repositories.documents import (
    _row_to_dict,
    search_policy_documents,
    search_product_documents,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed_documents(session):
    session.add_all(
        [
            Document(
                doc_type="product",
                source_path="data/documents/products/TECH-KEY-010.md",
                source_name="TECH-KEY-010.md",
                product_id="TECH-KEY-010",
                product_name="Mechanical Gaming Keyboard",
                policy_name=None,
                chunk_index=0,
                content="Keyboard specs and switch details.",
                metadata_json={"doc_type": "product", "product_id": "TECH-KEY-010"},
                embedding="[0.1,0.2,0.3]",
                embedding_provider="huggingface",
                embedding_model="sentence-transformers/all-mpnet-base-v2",
            ),
            Document(
                doc_type="product",
                source_path="data/documents/products/TECH-LAP-001.md",
                source_name="TECH-LAP-001.md",
                product_id="TECH-LAP-001",
                product_name="MacBook Air M2",
                policy_name=None,
                chunk_index=0,
                content="Laptop specs and battery details.",
                metadata_json={"doc_type": "product", "product_id": "TECH-LAP-001"},
                embedding="[0.3,0.2,0.1]",
                embedding_provider="huggingface",
                embedding_model="sentence-transformers/all-mpnet-base-v2",
            ),
            Document(
                doc_type="policy",
                source_path="data/documents/policies/return_policy.md",
                source_name="return_policy.md",
                product_id=None,
                product_name=None,
                policy_name="return_policy",
                chunk_index=0,
                content="Return policy details.",
                metadata_json={"doc_type": "policy", "policy_name": "return_policy"},
                embedding="[0.2,0.2,0.2]",
                embedding_provider="huggingface",
                embedding_model="sentence-transformers/all-mpnet-base-v2",
            ),
        ]
    )
    session.commit()


def test_search_product_documents_filters_products_and_limits_results():
    session = make_session()
    seed_documents(session)

    results = search_product_documents(session, [0.1, 0.2, 0.3], k=1)

    assert len(results) == 1
    assert results[0]["doc_type"] == "product"
    assert results[0]["product_id"] == "TECH-KEY-010"
    assert results[0]["content"] == "Keyboard specs and switch details."


def test_search_policy_documents_filters_policies():
    session = make_session()
    seed_documents(session)

    results = search_policy_documents(session, [0.1, 0.2, 0.3], k=2)

    assert len(results) == 1
    assert results[0]["doc_type"] == "policy"
    assert results[0]["policy_name"] == "return_policy"
    assert results[0]["metadata"]["policy_name"] == "return_policy"


def test_row_to_dict_supports_mapping_rows():
    row = {
        "id": 1,
        "doc_type": "product",
        "source_path": "data/documents/products/TECH-LAP-001.md",
        "source_name": "TECH-LAP-001.md",
        "product_id": "TECH-LAP-001",
        "product_name": "Laptop",
        "policy_name": None,
        "chunk_index": 0,
        "content": "Laptop specs.",
        "metadata_json": {"doc_type": "product"},
        "embedding_provider": "huggingface",
        "embedding_model": "sentence-transformers/all-mpnet-base-v2",
        "distance": 0.25,
    }

    result = _row_to_dict(row)

    assert result["metadata"] == {"doc_type": "product"}
    assert result["score"] == 0.25
