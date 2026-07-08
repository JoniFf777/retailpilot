from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Document
import tools.documents as document_tools
from tools.documents import search_policy_docs, search_product_docs


@pytest.fixture
def document_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    @contextmanager
    def fake_document_session():
        yield session

    monkeypatch.setattr(document_tools, "_get_document_session", fake_document_session)
    monkeypatch.setattr(document_tools, "_embed_query", lambda query: [0.1, 0.2, 0.3])
    yield session
    session.close()


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
                metadata_json={
                    "doc_type": "product",
                    "product_id": "TECH-KEY-010",
                    "product_name": "Mechanical Gaming Keyboard",
                },
                embedding="[0.1,0.2,0.3]",
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
                metadata_json={
                    "doc_type": "policy",
                    "policy_name": "return_policy",
                },
                embedding="[0.2,0.2,0.2]",
                embedding_provider="huggingface",
                embedding_model="sentence-transformers/all-mpnet-base-v2",
            ),
        ]
    )
    session.commit()


def test_search_product_docs_uses_document_repository(document_session):
    seed_documents(document_session)

    content, artifacts = search_product_docs.func("keyboard specs")

    assert "Mechanical Gaming Keyboard" in content
    assert "TECH-KEY-010" in content
    assert "Keyboard specs and switch details." in content
    assert len(artifacts) == 1
    assert artifacts[0].metadata["doc_type"] == "product"
    assert artifacts[0].metadata["product_id"] == "TECH-KEY-010"


def test_search_policy_docs_uses_document_repository(document_session):
    seed_documents(document_session)

    content, artifacts = search_policy_docs.func("return policy")

    assert "[return_policy]" in content
    assert "Return policy details." in content
    assert len(artifacts) == 1
    assert artifacts[0].metadata["doc_type"] == "policy"
    assert artifacts[0].metadata["policy_name"] == "return_policy"


def test_search_product_docs_returns_empty_message(document_session):
    content, artifacts = search_product_docs.func("missing")

    assert content == "No relevant product documentation found."
    assert artifacts == []
