"""Private PostgreSQL evidence-version/document visibility acceptance."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1", allow_module_level=True)

from app.ai_platform.contracts import EvidenceType
from app.ai_platform.indexing import PostgreSQLEvidenceIndexer
from app.ai_platform.ingestion import ShoppingEvidencePipeline, classify_legacy_source
from app.ai_platform.models import ShoppingEvidencePublication, ShoppingEvidenceVersion
from app.core.settings import get_settings
from app.db.models import Document
from app.repositories.shopping_evidence import list_current_evidence, revoke_evidence


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


class _Embeddings:
    def embed_documents(self, texts):
        return [[0.01] * 768 for _ in texts]


def test_evidence_version_links_documents_and_revoke_hides_them() -> None:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    schema = f"shopmind_evidence_version_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            connection.execute(text(f'CREATE TABLE "{schema}".alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
            connection.commit()
            command.upgrade(_alembic(connection), "head")
            assert "evidence_version_id" in {column["name"] for column in inspect(connection).get_columns("documents", schema=schema)}
            session = sessionmaker(bind=connection, expire_on_commit=False)()
            try:
                descriptor = classify_legacy_source("data/documents/products/TECH-LAP-001.md", "# Laptop\n\nA trusted versioned guide")
                result = ShoppingEvidencePipeline(indexer=PostgreSQLEvidenceIndexer(session, _Embeddings(), embedding_provider="test", embedding_model="fixture-768")).run(session, descriptor, "# Laptop\n\nA trusted versioned guide")
                session.commit()
                document = session.scalar(select(Document).where(Document.evidence_version_id == result.evidence_version_id))
                assert document is not None
                assert document.metadata_json["evidence_version_id"] == result.evidence_version_id
                assert list_current_evidence(session, evidence_type=EvidenceType.PRODUCT_GUIDE.value)
                assert revoke_evidence(session, descriptor.source_path)
                session.commit()
                assert list_current_evidence(session, evidence_type=EvidenceType.PRODUCT_GUIDE.value) == []
            finally:
                session.close()
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()
