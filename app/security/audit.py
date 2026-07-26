"""PII-safe governance audit contracts and boundary converters."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.runtime.contracts import (
    ActionRiskClass,
    MemoryKind,
    MemoryScope,
    ToolCallRecord,
    ToolCallStatus,
    ToolSideEffectClass,
)
from app.security.identity import AuthenticatedPrincipal, IdentityProviderName


GOVERNANCE_AUDIT_SCHEMA_VERSION = "shopmind.governance-audit.v1"
_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
_SAFE_NAME_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
_FINGERPRINT_RE = re.compile(_FINGERPRINT_PATTERN)


class AuditCategory(StrEnum):
    AUTHENTICATION = "authentication"
    TOOL = "tool"
    ACTION = "action"
    MEMORY = "memory"
    DELETION = "deletion"


class AuditOperation(StrEnum):
    AUTHENTICATION_BIND = "authentication.bind"
    TOOL_INVOKE = "tool.invoke"
    ACTION_PREPARE = "action.prepare"
    ACTION_RESUME = "action.resume"
    ACTION_CONFIRM = "action.confirm"
    ACTION_CANCEL = "action.cancel"
    ACTION_EXPIRE = "action.expire"
    MEMORY_CREATE = "memory.create"
    MEMORY_INSPECT = "memory.inspect"
    MEMORY_CORRECT = "memory.correct"
    MEMORY_DELETE = "memory.delete"
    DELETION_REQUEST = "deletion.request"
    DELETION_EXECUTE = "deletion.execute"


class AuditDecision(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_FOUND = "not_found"


class AuditReason(StrEnum):
    AUTHENTICATED = "authenticated"
    ANONYMOUS_COMPATIBILITY = "anonymous_compatibility"
    AUTHENTICATION_REQUIRED = "authentication_required"
    OWNER_MATCHED = "owner_matched"
    OWNER_MISMATCH = "owner_mismatch"
    POLICY_ALLOWED = "policy_allowed"
    POLICY_DENIED = "policy_denied"
    COMPLETED = "completed"
    VALIDATION_FAILED = "validation_failed"
    PROVIDER_FAILED = "provider_failed"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    USER_REQUESTED = "user_requested"
    RETENTION_EXPIRED = "retention_expired"
    ALREADY_DELETED = "already_deleted"
    CANCELLED = "cancelled"
    BUDGET_BLOCKED = "budget_blocked"


class AuditActorKind(StrEnum):
    PRINCIPAL = "principal"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"


class AuditRequestOperation(StrEnum):
    CHAT = "chat"
    CONFIRM_PENDING_ACTION = "confirm_pending_action"
    CHAT_STREAM = "chat_stream"
    OWNER_DATA_INSPECT = "owner_data_inspect"
    OWNER_MEMORY_CORRECT = "owner_memory_correct"
    OWNER_MEMORY_DELETE = "owner_memory_delete"
    OWNER_DATA_DELETE = "owner_data_delete"


class AuditDeletionTarget(StrEnum):
    CONVERSATION = "conversation"
    MEMORY = "memory"
    RUNTIME = "runtime"
    USER_DATA = "user_data"


class AuditFingerprintNamespace(StrEnum):
    ACTOR = "actor"
    OWNER = "owner"
    THREAD = "thread"
    RUN = "run"
    ACTION = "action"
    MEMORY = "memory"
    DELETION_REQUEST = "deletion_request"
    TOOL_CALL = "tool_call"


_OPERATION_CATEGORY = {
    AuditOperation.AUTHENTICATION_BIND: AuditCategory.AUTHENTICATION,
    AuditOperation.TOOL_INVOKE: AuditCategory.TOOL,
    AuditOperation.ACTION_PREPARE: AuditCategory.ACTION,
    AuditOperation.ACTION_RESUME: AuditCategory.ACTION,
    AuditOperation.ACTION_CONFIRM: AuditCategory.ACTION,
    AuditOperation.ACTION_CANCEL: AuditCategory.ACTION,
    AuditOperation.ACTION_EXPIRE: AuditCategory.ACTION,
    AuditOperation.MEMORY_CREATE: AuditCategory.MEMORY,
    AuditOperation.MEMORY_INSPECT: AuditCategory.MEMORY,
    AuditOperation.MEMORY_CORRECT: AuditCategory.MEMORY,
    AuditOperation.MEMORY_DELETE: AuditCategory.MEMORY,
    AuditOperation.DELETION_REQUEST: AuditCategory.DELETION,
    AuditOperation.DELETION_EXECUTE: AuditCategory.DELETION,
}

_ALLOWED_DECISIONS = {
    AuditOperation.AUTHENTICATION_BIND: {
        AuditDecision.ALLOWED,
        AuditDecision.DENIED,
    },
    AuditOperation.TOOL_INVOKE: {
        AuditDecision.ALLOWED,
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.SKIPPED,
    },
    AuditOperation.ACTION_PREPARE: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
    },
    AuditOperation.ACTION_RESUME: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.NOT_FOUND,
    },
    AuditOperation.ACTION_CONFIRM: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.NOT_FOUND,
    },
    AuditOperation.ACTION_CANCEL: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.NOT_FOUND,
    },
    AuditOperation.ACTION_EXPIRE: {
        AuditDecision.SUCCEEDED,
        AuditDecision.SKIPPED,
        AuditDecision.NOT_FOUND,
    },
    AuditOperation.MEMORY_CREATE: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
    },
    AuditOperation.MEMORY_INSPECT: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.NOT_FOUND,
    },
    AuditOperation.MEMORY_CORRECT: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.NOT_FOUND,
    },
    AuditOperation.MEMORY_DELETE: {
        AuditDecision.DENIED,
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.NOT_FOUND,
    },
    AuditOperation.DELETION_REQUEST: {
        AuditDecision.REQUESTED,
        AuditDecision.DENIED,
    },
    AuditOperation.DELETION_EXECUTE: {
        AuditDecision.SUCCEEDED,
        AuditDecision.FAILED,
        AuditDecision.SKIPPED,
        AuditDecision.NOT_FOUND,
    },
}

_ALLOWED_METADATA_FIELDS = {
    AuditCategory.AUTHENTICATION: {"provider", "request_operation"},
    AuditCategory.TOOL: {
        "capability",
        "side_effect_class",
        "requires_confirmation",
        "audit_sequence",
        "duration_ms",
        "input_fingerprint",
    },
    AuditCategory.ACTION: {"action_type", "risk_class"},
    AuditCategory.MEMORY: {"memory_kind", "memory_scope", "records_affected"},
    AuditCategory.DELETION: {"deletion_target", "records_affected"},
}

_REQUIRED_METADATA_FIELDS = {
    AuditCategory.AUTHENTICATION: {"provider", "request_operation"},
    AuditCategory.TOOL: {
        "capability",
        "side_effect_class",
        "requires_confirmation",
    },
    AuditCategory.ACTION: {"action_type"},
    AuditCategory.MEMORY: {"memory_kind", "memory_scope"},
    AuditCategory.DELETION: {"deletion_target"},
}


def governance_fingerprint(
    namespace: AuditFingerprintNamespace,
    value: str,
) -> str:
    """Return a domain-separated fingerprint without retaining the raw value."""

    if not isinstance(namespace, AuditFingerprintNamespace):
        namespace = AuditFingerprintNamespace(namespace)
    if not isinstance(value, str):
        raise ValueError("Governance audit fingerprint input is invalid.")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 1024
        or any(ord(character) < 32 for character in normalized)
    ):
        raise ValueError("Governance audit fingerprint input is invalid.")
    encoded = (
        f"shopmind.governance-audit.v1\0{namespace.value}\0{normalized}".encode(
            "utf-8"
        )
    )
    return hashlib.sha256(encoded).hexdigest()


class GovernanceAuditMetadata(BaseModel):
    """Closed metadata allowlist; raw payload dictionaries are never accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    provider: IdentityProviderName | None = None
    request_operation: AuditRequestOperation | None = None
    capability: str | None = Field(default=None, pattern=_SAFE_NAME_PATTERN)
    side_effect_class: ToolSideEffectClass | None = None
    requires_confirmation: bool | None = None
    audit_sequence: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)
    input_fingerprint: str | None = Field(
        default=None,
        pattern=_FINGERPRINT_PATTERN,
    )
    action_type: str | None = Field(default=None, pattern=_SAFE_NAME_PATTERN)
    risk_class: ActionRiskClass | None = None
    memory_kind: MemoryKind | None = None
    memory_scope: MemoryScope | None = None
    deletion_target: AuditDeletionTarget | None = None
    records_affected: int | None = Field(default=None, ge=0)


class GovernanceAuditRecord(BaseModel):
    """One persistable governance decision containing no direct identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    schema_version: Literal["shopmind.governance-audit.v1"] = (
        GOVERNANCE_AUDIT_SCHEMA_VERSION
    )
    audit_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    category: AuditCategory
    operation: AuditOperation
    decision: AuditDecision
    reason: AuditReason
    actor_kind: AuditActorKind
    actor_fingerprint: str | None = Field(
        default=None,
        pattern=_FINGERPRINT_PATTERN,
    )
    owner_fingerprint: str | None = Field(
        default=None,
        pattern=_FINGERPRINT_PATTERN,
    )
    thread_fingerprint: str | None = Field(
        default=None,
        pattern=_FINGERPRINT_PATTERN,
    )
    run_fingerprint: str | None = Field(
        default=None,
        pattern=_FINGERPRINT_PATTERN,
    )
    resource_fingerprint: str | None = Field(
        default=None,
        pattern=_FINGERPRINT_PATTERN,
    )
    metadata: GovernanceAuditMetadata

    @model_validator(mode="after")
    def validate_closed_contract(self) -> "GovernanceAuditRecord":
        operation = AuditOperation(self.operation)
        category = AuditCategory(self.category)
        decision = AuditDecision(self.decision)
        actor_kind = AuditActorKind(self.actor_kind)
        if _OPERATION_CATEGORY[operation] != category:
            raise ValueError("Governance audit category does not match operation.")
        if decision not in _ALLOWED_DECISIONS[operation]:
            raise ValueError("Governance audit decision is invalid for operation.")
        if actor_kind == AuditActorKind.PRINCIPAL:
            if self.actor_fingerprint is None:
                raise ValueError("Principal audit actors require a fingerprint.")
        elif self.actor_fingerprint is not None:
            raise ValueError("Only principal audit actors may carry a fingerprint.")
        present_metadata = set(
            self.metadata.model_dump(exclude_none=True, mode="json")
        )
        if not present_metadata.issubset(_ALLOWED_METADATA_FIELDS[category]):
            raise ValueError("Governance audit metadata is invalid for category.")
        required_metadata = set(_REQUIRED_METADATA_FIELDS[category])
        if (
            category == AuditCategory.MEMORY
            and decision == AuditDecision.NOT_FOUND
        ):
            required_metadata.difference_update({"memory_kind", "memory_scope"})
        missing = required_metadata.difference(present_metadata)
        if missing:
            raise ValueError("Governance audit metadata is incomplete for category.")
        if category != AuditCategory.AUTHENTICATION and self.resource_fingerprint is None:
            raise ValueError("Governance resource decisions require a fingerprint.")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("Governance audit timestamps must be timezone-aware.")
        return self


class GovernanceAuditFactory:
    """Create audit records from current typed runtime boundaries."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        audit_id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._audit_id_factory = audit_id_factory or uuid4

    def authentication_decision(
        self,
        *,
        provider: IdentityProviderName,
        request_operation: AuditRequestOperation,
        decision: AuditDecision,
        reason: AuditReason,
        principal: AuthenticatedPrincipal | None = None,
        requested_user_id: str | None = None,
    ) -> GovernanceAuditRecord:
        actor_kind, actor_fingerprint = self._actor(principal, anonymous=True)
        owner_id = requested_user_id
        if owner_id is None and principal is not None:
            owner_id = principal.subject_id
        return self._record(
            category=AuditCategory.AUTHENTICATION,
            operation=AuditOperation.AUTHENTICATION_BIND,
            decision=decision,
            reason=reason,
            actor_kind=actor_kind,
            actor_fingerprint=actor_fingerprint,
            owner_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.OWNER,
                owner_id,
            ),
            metadata=GovernanceAuditMetadata(
                provider=provider,
                request_operation=request_operation,
            ),
        )

    def tool_decision(
        self,
        *,
        record: ToolCallRecord,
        principal: AuthenticatedPrincipal | None,
        owner_id: str | None,
        thread_id: str | None = None,
        run_id: str | None = None,
        decision: AuditDecision | None = None,
        reason: AuditReason | None = None,
    ) -> GovernanceAuditRecord:
        resolved_decision = AuditDecision(
            decision or self._tool_decision(record.status)
        )
        if resolved_decision not in _ALLOWED_DECISIONS[AuditOperation.TOOL_INVOKE]:
            raise ValueError("Tool audit decision is invalid.")
        resolved_reason = reason or self._tool_reason(resolved_decision)
        actor_kind, actor_fingerprint = self._actor(principal)
        input_fingerprint = (
            record.argument_hash
            if record.argument_hash and _FINGERPRINT_RE.fullmatch(record.argument_hash)
            else None
        )
        return self._record(
            category=AuditCategory.TOOL,
            operation=AuditOperation.TOOL_INVOKE,
            decision=resolved_decision,
            reason=resolved_reason,
            actor_kind=actor_kind,
            actor_fingerprint=actor_fingerprint,
            owner_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.OWNER,
                owner_id,
            ),
            thread_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.THREAD,
                thread_id,
            ),
            run_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.RUN,
                run_id,
            ),
            resource_fingerprint=governance_fingerprint(
                AuditFingerprintNamespace.TOOL_CALL,
                record.tool_call_id,
            ),
            metadata=GovernanceAuditMetadata(
                capability=record.capability or record.tool_name,
                side_effect_class=record.side_effect_class,
                requires_confirmation=record.requires_confirmation,
                audit_sequence=record.audit_sequence,
                duration_ms=record.duration_ms,
                input_fingerprint=input_fingerprint,
            ),
        )

    def action_decision(
        self,
        *,
        operation: AuditOperation,
        decision: AuditDecision,
        reason: AuditReason,
        action_type: str,
        action_id: str,
        principal: AuthenticatedPrincipal | None,
        owner_id: str,
        thread_id: str | None = None,
        run_id: str | None = None,
        risk_class: ActionRiskClass | None = None,
    ) -> GovernanceAuditRecord:
        if _OPERATION_CATEGORY.get(operation) != AuditCategory.ACTION:
            raise ValueError("Action audit operation is invalid.")
        actor_kind, actor_fingerprint = self._actor(principal)
        return self._record(
            category=AuditCategory.ACTION,
            operation=operation,
            decision=decision,
            reason=reason,
            actor_kind=actor_kind,
            actor_fingerprint=actor_fingerprint,
            owner_fingerprint=governance_fingerprint(
                AuditFingerprintNamespace.OWNER,
                owner_id,
            ),
            thread_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.THREAD,
                thread_id,
            ),
            run_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.RUN,
                run_id,
            ),
            resource_fingerprint=governance_fingerprint(
                AuditFingerprintNamespace.ACTION,
                action_id,
            ),
            metadata=GovernanceAuditMetadata(
                action_type=action_type,
                risk_class=risk_class,
            ),
        )

    def memory_decision(
        self,
        *,
        operation: AuditOperation,
        decision: AuditDecision,
        reason: AuditReason,
        memory_id: str,
        memory_kind: MemoryKind | None,
        memory_scope: MemoryScope | None,
        principal: AuthenticatedPrincipal | None,
        owner_id: str | None,
        thread_id: str | None = None,
        run_id: str | None = None,
        records_affected: int | None = None,
    ) -> GovernanceAuditRecord:
        if _OPERATION_CATEGORY.get(operation) != AuditCategory.MEMORY:
            raise ValueError("Memory audit operation is invalid.")
        actor_kind, actor_fingerprint = self._actor(principal)
        return self._record(
            category=AuditCategory.MEMORY,
            operation=operation,
            decision=decision,
            reason=reason,
            actor_kind=actor_kind,
            actor_fingerprint=actor_fingerprint,
            owner_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.OWNER,
                owner_id,
            ),
            thread_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.THREAD,
                thread_id,
            ),
            run_fingerprint=self._optional_fingerprint(
                AuditFingerprintNamespace.RUN,
                run_id,
            ),
            resource_fingerprint=governance_fingerprint(
                AuditFingerprintNamespace.MEMORY,
                memory_id,
            ),
            metadata=GovernanceAuditMetadata(
                memory_kind=memory_kind,
                memory_scope=memory_scope,
                records_affected=records_affected,
            ),
        )

    def deletion_decision(
        self,
        *,
        operation: AuditOperation,
        decision: AuditDecision,
        reason: AuditReason,
        deletion_request_id: str,
        deletion_target: AuditDeletionTarget,
        principal: AuthenticatedPrincipal | None,
        owner_id: str,
        records_affected: int | None = None,
    ) -> GovernanceAuditRecord:
        if _OPERATION_CATEGORY.get(operation) != AuditCategory.DELETION:
            raise ValueError("Deletion audit operation is invalid.")
        actor_kind, actor_fingerprint = self._actor(principal)
        return self._record(
            category=AuditCategory.DELETION,
            operation=operation,
            decision=decision,
            reason=reason,
            actor_kind=actor_kind,
            actor_fingerprint=actor_fingerprint,
            owner_fingerprint=governance_fingerprint(
                AuditFingerprintNamespace.OWNER,
                owner_id,
            ),
            resource_fingerprint=governance_fingerprint(
                AuditFingerprintNamespace.DELETION_REQUEST,
                deletion_request_id,
            ),
            metadata=GovernanceAuditMetadata(
                deletion_target=deletion_target,
                records_affected=records_affected,
            ),
        )

    def _record(self, **values: object) -> GovernanceAuditRecord:
        return GovernanceAuditRecord(
            audit_id=self._audit_id_factory(),
            occurred_at=self._clock(),
            **values,
        )

    @staticmethod
    def _actor(
        principal: AuthenticatedPrincipal | None,
        *,
        anonymous: bool = False,
    ) -> tuple[AuditActorKind, str | None]:
        if principal is not None:
            return (
                AuditActorKind.PRINCIPAL,
                governance_fingerprint(
                    AuditFingerprintNamespace.ACTOR,
                    principal.subject_id,
                ),
            )
        return (
            AuditActorKind.ANONYMOUS if anonymous else AuditActorKind.SYSTEM,
            None,
        )

    @staticmethod
    def _optional_fingerprint(
        namespace: AuditFingerprintNamespace,
        value: str | None,
    ) -> str | None:
        if value is None or not value.strip():
            return None
        return governance_fingerprint(namespace, value)

    @staticmethod
    def _tool_decision(status: ToolCallStatus) -> AuditDecision:
        return {
            ToolCallStatus.COMPLETED: AuditDecision.SUCCEEDED,
            ToolCallStatus.FAILED: AuditDecision.FAILED,
            ToolCallStatus.SKIPPED: AuditDecision.SKIPPED,
            ToolCallStatus.STARTED: AuditDecision.ALLOWED,
        }[ToolCallStatus(status)]

    @staticmethod
    def _tool_reason(decision: AuditDecision) -> AuditReason:
        return {
            AuditDecision.ALLOWED: AuditReason.POLICY_ALLOWED,
            AuditDecision.DENIED: AuditReason.POLICY_DENIED,
            AuditDecision.SUCCEEDED: AuditReason.COMPLETED,
            AuditDecision.FAILED: AuditReason.PROVIDER_FAILED,
            AuditDecision.SKIPPED: AuditReason.CANCELLED,
        }[AuditDecision(decision)]


__all__ = [
    "GOVERNANCE_AUDIT_SCHEMA_VERSION",
    "AuditActorKind",
    "AuditCategory",
    "AuditDecision",
    "AuditDeletionTarget",
    "AuditFingerprintNamespace",
    "AuditOperation",
    "AuditReason",
    "AuditRequestOperation",
    "GovernanceAuditFactory",
    "GovernanceAuditMetadata",
    "GovernanceAuditRecord",
    "governance_fingerprint",
]
