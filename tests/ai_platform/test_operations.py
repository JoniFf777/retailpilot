from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ai_platform.operations import project_trace, record_admin_operation
from app.db.base import Base
from app.db.models import GovernanceAuditRecord


def test_trace_projection_excludes_payload_content():
    result = project_trace([{
        "sequence": 1,
        "event_type": "tool.completed",
        "agent_name": "rag_agent",
        "visibility": "client",
        "payload": {"status": "completed", "message": "private text", "tool_arguments": {"secret": "x"}},
    }])
    assert result == [{"sequence": 1, "event_type": "tool.completed", "agent_name": "rag_agent", "visibility": "client", "status": "completed"}]


def test_admin_operation_can_emit_pii_safe_governance_fact():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    record_admin_operation(
        operation="extension_published",
        resource_type="extension",
        resource_key="decision",
        version=2,
        audit_enabled=True,
        session_factory=factory,
    )
    session = factory()
    try:
        records = session.scalars(select(GovernanceAuditRecord)).all()
        assert len(records) == 1
        assert "decision" not in records[0].metadata_json
    finally:
        session.close()
