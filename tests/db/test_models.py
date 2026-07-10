import ast
from configparser import ConfigParser
from pathlib import Path

from app.db.base import Base
from app.db import models  # noqa: F401


def test_metadata_contains_structured_business_tables():
    expected_tables = {
        "customers",
        "products",
        "orders",
        "order_items",
        "user_preferences",
        "cart_items",
        "pending_actions",
        "candidate_contexts",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))


def test_metadata_contains_documents_table():
    assert "documents" in Base.metadata.tables


def test_documents_table_contains_pgvector_rag_columns():
    documents = Base.metadata.tables["documents"]
    expected_columns = {
        "id",
        "doc_type",
        "source_path",
        "source_name",
        "product_id",
        "product_name",
        "policy_name",
        "chunk_index",
        "content",
        "metadata_json",
        "embedding",
        "embedding_provider",
        "embedding_model",
        "created_at",
    }

    assert expected_columns.issubset(set(documents.c.keys()))


def test_pending_actions_keeps_v1_payload_column_name():
    pending_actions = Base.metadata.tables["pending_actions"]

    assert "payload_json" in pending_actions.c


def test_candidate_contexts_table_contains_selection_context_columns():
    candidate_contexts = Base.metadata.tables["candidate_contexts"]
    expected_columns = {
        "user_id",
        "thread_id",
        "product_ids",
        "quantity",
        "expires_at",
        "created_at",
        "updated_at",
    }

    assert expected_columns.issubset(set(candidate_contexts.c.keys()))


def test_alembic_revision_ids_fit_default_version_table():
    revision_files = list(Path("alembic/versions").glob("*.py"))
    revision_ids = []
    for revision_file in revision_files:
        module = ast.parse(revision_file.read_text(encoding="utf-8"))
        for statement in module.body:
            if isinstance(statement, ast.AnnAssign) and statement.target.id == "revision":
                revision_ids.append(ast.literal_eval(statement.value))
                break

    assert revision_ids
    assert all(len(revision_id) <= 32 for revision_id in revision_ids)


def test_alembic_ini_uses_psycopg_driver_defaults():
    parser = ConfigParser()
    parser.read("alembic.ini", encoding="utf-8")

    url = parser.get("alembic", "sqlalchemy.url")

    assert url.startswith("postgresql+psycopg://")
    assert "@127.0.0.1:5432/" in url
    assert "connect_timeout=5" in url
