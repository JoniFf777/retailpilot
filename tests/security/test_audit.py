import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.settings import Settings
from app.runtime import (
    ActionRiskClass,
    MemoryKind,
    MemoryScope,
    ToolCallRecord,
    ToolCallStatus,
    ToolSideEffectClass,
)
from app.security import (
    AuditActorKind,
    AuditCategory,
    AuditDecision,
    AuditDeletionTarget,
    AuditFingerprintNamespace,
    AuditOperation,
    AuditReason,
    AuditRequestOperation,
    GovernanceAuditFactory,
    GovernanceAuditMetadata,
    GovernanceAuditRecord,
    IdentityProviderName,
    build_identity_boundary,
    governance_fingerprint,
)


FIXED_NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
FIXED_AUDIT_ID = UUID("00000000-0000-0000-0000-000000000040")


def _factory() -> GovernanceAuditFactory:
    return GovernanceAuditFactory(
        clock=lambda: FIXED_NOW,
        audit_id_factory=lambda: FIXED_AUDIT_ID,
    )


def _principal():
    binding = build_identity_boundary(Settings()).bind_user(
        "private-user-001",
        require_user=True,
    )
    assert binding.principal is not None
    return binding.principal


def _serialized(record: GovernanceAuditRecord) -> str:
    return json.dumps(record.model_dump(mode="json"), sort_keys=True)


def test_governance_fingerprint_is_domain_separated_and_never_echoes_input() -> None:
    actor = governance_fingerprint(
        AuditFingerprintNamespace.ACTOR,
        "private-user-001",
    )
    owner = governance_fingerprint(
        AuditFingerprintNamespace.OWNER,
        "private-user-001",
    )

    assert len(actor) == 64
    assert actor != owner
    assert "private-user-001" not in actor
    with pytest.raises(ValueError, match="invalid"):
        governance_fingerprint(AuditFingerprintNamespace.OWNER, " \n ")


def test_authentication_audit_contains_only_fingerprints_and_closed_metadata() -> None:
    principal = _principal()
    record = _factory().authentication_decision(
        provider=IdentityProviderName.DEVELOPMENT_PAYLOAD,
        request_operation=AuditRequestOperation.CHAT,
        decision=AuditDecision.ALLOWED,
        reason=AuditReason.AUTHENTICATED,
        principal=principal,
        requested_user_id="private-user-001",
    )
    serialized = _serialized(record)

    assert record.schema_version == "shopmind.governance-audit.v1"
    assert record.audit_id == FIXED_AUDIT_ID
    assert record.occurred_at == FIXED_NOW
    assert record.category == "authentication"
    assert record.actor_kind == "principal"
    assert record.actor_fingerprint == governance_fingerprint(
        AuditFingerprintNamespace.ACTOR,
        principal.subject_id,
    )
    assert record.actor_fingerprint != principal.subject_fingerprint
    assert record.owner_fingerprint is not None
    assert "private-user-001" not in serialized
    assert set(record.metadata.model_dump(exclude_none=True)) == {
        "provider",
        "request_operation",
    }


def test_authentication_denial_can_be_audited_without_an_authenticated_actor() -> None:
    record = _factory().authentication_decision(
        provider=IdentityProviderName.TRUSTED_HEADER,
        request_operation=AuditRequestOperation.CHAT_STREAM,
        decision=AuditDecision.DENIED,
        reason=AuditReason.AUTHENTICATION_REQUIRED,
        requested_user_id="untrusted-payload-owner",
    )

    assert record.actor_kind == "anonymous"
    assert record.actor_fingerprint is None
    assert record.owner_fingerprint is not None
    assert "untrusted-payload-owner" not in _serialized(record)


def test_tool_audit_drops_unknown_result_metadata_and_raw_audit_reference() -> None:
    secret_url = "postgresql://private-user:private-password@private-host/db"
    provider_error = "provider said private customer message"
    record = ToolCallRecord(
        tool_call_id="tool-call-private-id",
        tool_name="confirm_add_to_cart",
        caller="confirmation_boundary",
        capability="confirmation_boundary",
        argument_hash="a" * 64,
        status=ToolCallStatus.FAILED,
        side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
        requires_confirmation=True,
        audit_reference="raw-private-reference",
        audit_sequence=3,
        duration_ms=12,
        result_metadata={
            "connection_url": secret_url,
            "provider_error": provider_error,
        },
    )

    audit = _factory().tool_decision(
        record=record,
        principal=_principal(),
        owner_id="private-user-001",
        thread_id="private-thread-001",
        run_id="private-run-001",
    )
    serialized = _serialized(audit)

    assert audit.decision == "failed"
    assert audit.resource_fingerprint is not None
    assert audit.metadata.input_fingerprint == "a" * 64
    assert set(audit.metadata.model_dump(exclude_none=True)) == {
        "capability",
        "side_effect_class",
        "requires_confirmation",
        "audit_sequence",
        "duration_ms",
        "input_fingerprint",
    }
    for private_value in (
        secret_url,
        provider_error,
        "raw-private-reference",
        "tool-call-private-id",
        "private-thread-001",
        "private-run-001",
    ):
        assert private_value not in serialized


def test_action_memory_and_deletion_converters_never_retain_raw_resource_ids() -> None:
    factory = _factory()
    principal = _principal()
    action = factory.action_decision(
        operation=AuditOperation.ACTION_CONFIRM,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.COMPLETED,
        action_type="add_to_cart",
        action_id="private-action-id",
        principal=principal,
        owner_id="private-user-001",
        thread_id="private-thread-001",
        run_id="private-run-001",
        risk_class=ActionRiskClass.HIGH,
    )
    memory = factory.memory_decision(
        operation=AuditOperation.MEMORY_DELETE,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.USER_REQUESTED,
        memory_id="private-memory-id",
        memory_kind=MemoryKind.LONG_TERM,
        memory_scope=MemoryScope.USER,
        principal=principal,
        owner_id="private-user-001",
        records_affected=1,
    )
    deletion = factory.deletion_decision(
        operation=AuditOperation.DELETION_EXECUTE,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.USER_REQUESTED,
        deletion_request_id="private-deletion-id",
        deletion_target=AuditDeletionTarget.USER_DATA,
        principal=principal,
        owner_id="private-user-001",
        records_affected=7,
    )

    assert action.category == "action"
    assert memory.category == "memory"
    assert deletion.category == "deletion"
    combined = "".join(_serialized(item) for item in (action, memory, deletion))
    for private_value in (
        "private-action-id",
        "private-memory-id",
        "private-deletion-id",
        "private-user-001",
        "private-thread-001",
        "private-run-001",
    ):
        assert private_value not in combined


def test_missing_memory_audit_omits_unknown_kind_and_scope() -> None:
    audit = _factory().memory_decision(
        operation=AuditOperation.MEMORY_DELETE,
        decision=AuditDecision.NOT_FOUND,
        reason=AuditReason.NOT_FOUND,
        memory_id="private-missing-memory-id",
        memory_kind=None,
        memory_scope=None,
        principal=_principal(),
        owner_id="private-user-001",
        records_affected=0,
    )

    assert audit.decision == "not_found"
    assert audit.metadata.model_dump(exclude_none=True) == {
        "records_affected": 0
    }
    serialized = _serialized(audit)
    assert "private-missing-memory-id" not in serialized
    assert "private-user-001" not in serialized


def test_audit_contract_rejects_category_decision_and_actor_drift() -> None:
    metadata = GovernanceAuditMetadata(
        provider=IdentityProviderName.TRUSTED_HEADER,
        request_operation=AuditRequestOperation.CHAT,
    )
    values = {
        "category": AuditCategory.TOOL,
        "operation": AuditOperation.AUTHENTICATION_BIND,
        "decision": AuditDecision.ALLOWED,
        "reason": AuditReason.AUTHENTICATED,
        "actor_kind": AuditActorKind.ANONYMOUS,
        "metadata": metadata,
    }
    with pytest.raises(ValidationError, match="category"):
        GovernanceAuditRecord(**values)

    with pytest.raises(ValidationError, match="decision"):
        GovernanceAuditRecord(
            **{
                **values,
                "category": AuditCategory.AUTHENTICATION,
                "decision": AuditDecision.SUCCEEDED,
            }
        )

    with pytest.raises(ValidationError, match="fingerprint"):
        GovernanceAuditRecord(
            **{
                **values,
                "category": AuditCategory.AUTHENTICATION,
                "actor_kind": AuditActorKind.PRINCIPAL,
            }
        )


def test_audit_metadata_rejects_raw_message_credentials_and_connection_url() -> None:
    with pytest.raises(ValidationError) as exc_info:
        GovernanceAuditMetadata.model_validate(
            {
                "provider": "trusted_header",
                "request_operation": "chat",
                "message": "private shopping request",
                "credential": "private-token",
                "connection_url": "https://private.example/path",
            }
        )

    assert {error["loc"][0] for error in exc_info.value.errors()} == {
        "message",
        "credential",
        "connection_url",
    }


def test_factory_rejects_cross_category_operations_before_record_creation() -> None:
    factory = _factory()
    principal = _principal()

    with pytest.raises(ValueError, match="Action audit operation"):
        factory.action_decision(
            operation=AuditOperation.MEMORY_DELETE,
            decision=AuditDecision.SUCCEEDED,
            reason=AuditReason.COMPLETED,
            action_type="add_to_cart",
            action_id="action-1",
            principal=principal,
            owner_id="private-user-001",
        )
