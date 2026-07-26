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
        "conversation_threads",
        "conversation_messages",
        "agent_runs",
        "agent_run_events",
        "conversation_summaries",
        "idempotency_records",
        "runtime_memory_records",
        "governance_audit_records",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))


def test_metadata_contains_documents_table():
    assert "documents" in Base.metadata.tables


def test_runtime_memory_table_contains_scope_and_provenance_columns():
    memory = Base.metadata.tables["runtime_memory_records"]
    expected_columns = {
        "id",
        "user_id",
        "thread_id",
        "memory_kind",
        "scope",
        "content_text",
        "provenance_json",
        "priority",
        "token_count",
        "expires_at",
        "deleted_at",
    }

    assert expected_columns.issubset(set(memory.c.keys()))


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
    assert {
        "risk_class",
        "preview_text",
        "expires_at",
        "metadata_json",
    }.issubset(set(pending_actions.c.keys()))


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


def test_runtime_persistence_tables_contain_expected_columns():
    expected_thread_columns = {
        "id",
        "user_id",
        "client_thread_id",
        "status",
        "metadata_json",
        "last_message_at",
        "last_run_at",
        "expires_at",
        "created_at",
        "updated_at",
    }
    expected_message_columns = {
        "id",
        "thread_id",
        "user_id",
        "run_id",
        "sequence",
        "role",
        "message_type",
        "content_text",
        "content_json",
        "metadata_json",
    }
    expected_run_columns = {
        "id",
        "thread_id",
        "user_id",
        "operation",
        "mode",
        "status",
        "request_id",
        "trace_id",
        "request_json",
        "result_json",
        "usage_json",
        "tool_call_records_json",
        "started_at",
        "completed_at",
    }
    expected_summary_columns = {
        "id",
        "thread_id",
        "user_id",
        "source_run_id",
        "start_message_sequence",
        "end_message_sequence",
        "summary_text",
        "summary_json",
        "status",
    }
    expected_idempotency_columns = {
        "id",
        "user_id",
        "thread_id",
        "run_id",
        "operation",
        "idempotency_key",
        "request_hash",
        "status",
    }

    assert expected_thread_columns.issubset(
        set(Base.metadata.tables["conversation_threads"].c.keys())
    )
    assert expected_message_columns.issubset(
        set(Base.metadata.tables["conversation_messages"].c.keys())
    )
    assert expected_run_columns.issubset(
        set(Base.metadata.tables["agent_runs"].c.keys())
    )
    assert expected_summary_columns.issubset(
        set(Base.metadata.tables["conversation_summaries"].c.keys())
    )
    assert expected_idempotency_columns.issubset(
        set(Base.metadata.tables["idempotency_records"].c.keys())
    )


def test_governance_audit_table_contains_only_fingerprinted_identity_columns():
    audit = Base.metadata.tables["governance_audit_records"]
    expected_columns = {
        "audit_id",
        "schema_version",
        "category",
        "operation",
        "decision",
        "reason",
        "actor_kind",
        "actor_fingerprint",
        "owner_fingerprint",
        "thread_fingerprint",
        "run_fingerprint",
        "resource_fingerprint",
        "metadata_json",
        "occurred_at",
        "expires_at",
        "created_at",
    }

    assert expected_columns == set(audit.c.keys())
    assert {
        "user_id",
        "thread_id",
        "run_id",
        "resource_id",
        "request_json",
        "result_json",
    }.isdisjoint(audit.c.keys())


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
