"""Real PostgreSQL acceptance for the shopping evidence lifecycle."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1", allow_module_level=True)

from app.ai_platform.ingestion import ShoppingEvidencePipeline, classify_legacy_source
from app.ai_platform.models import (
    ShoppingEvidencePublication,
    ShoppingEvidenceVersion,
    ShoppingIngestionNode,
)
from app.core.settings import get_settings


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def test_shopping_evidence_migrations_and_pipeline_acceptance():
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    schema = f"shopmind_evidence_test_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            connection.execute(text(f'CREATE TABLE "{schema}".alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
            connection.commit()
            command.upgrade(_alembic(connection), "0017_ai_extension_registry")
            tables = set(inspect(connection).get_table_names(schema=schema))
            assert {
                "shopmind_evidence_versions",
                "shopmind_evidence_ingestion_tasks",
                "shopmind_evidence_ingestion_nodes",
                "shopmind_evidence_publications",
                "shopmind_ai_extension_definitions",
                "shopmind_ai_extension_publications",
            }.issubset(tables)
            factory = sessionmaker(bind=connection, expire_on_commit=False)
            session = factory()
            try:
                descriptor = classify_legacy_source(
                    "data/documents/products/TECH-LAP-001.md", "# Laptop\n\nBattery"
                )
                result = ShoppingEvidencePipeline().run(session, descriptor, "# Laptop\n\nBattery")
                session.commit()
                evidence = session.get(ShoppingEvidenceVersion, result.evidence_version_id)
                publication = session.scalar(select(ShoppingEvidencePublication))
                nodes = session.scalars(select(ShoppingIngestionNode)).all()
                assert evidence is not None and evidence.status == "published"
                assert publication is not None and publication.evidence_version_id == evidence.id
                assert {node.status for node in nodes} == {"completed"}
            finally:
                session.close()
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()
