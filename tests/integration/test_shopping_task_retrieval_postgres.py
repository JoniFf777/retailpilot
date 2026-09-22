"""Read-only real PostgreSQL retrieval gate for the task QuerySpec."""

import os

import pytest

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1", allow_module_level=True)

from app.db.session import SessionLocal
from app.shopping_tasks.evidence import TaskQuerySpec, retrieve_task_evidence


def test_task_query_uses_real_postgres_lexical_evidence_scope() -> None:
    result = retrieve_task_evidence(
        TaskQuerySpec(
            original_question="商城退货政策和期限",
            evidence_type="store_policy",
            policy_type="return",
            region="CN",
            channel="online",
            limit=3,
        ),
        session_factory=SessionLocal,
    )
    assert result.status in {"ok", "degraded", "empty", "unavailable"}
    assert result.channel_statuses
    assert all(item.evidence_type == "store_policy" for item in result.citations)
