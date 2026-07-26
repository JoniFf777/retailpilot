"""Authenticated owner-data lifecycle with PII-safe governance emission."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.governance.emitter import GovernanceAuditEmitter
from app.repositories.owner_data import (
    MAX_OWNER_MEMORY_INSPECTION_RECORDS,
    correct_owner_memory_record,
    delete_all_owner_data,
    delete_owner_memory_record,
    inspect_owner_data,
)
from app.repositories.runtime_runs import inspect_owner_agent_run
from app.runtime.contracts import (
    EventVisibility,
    MemoryKind,
    MemoryScope,
    RunMode,
    RunOperation,
    RunStatus,
    RunUsage,
)
from app.security.audit import (
    AuditDecision,
    AuditDeletionTarget,
    AuditOperation,
    AuditReason,
    GovernanceAuditFactory,
)
from app.security.identity import AuthenticatedPrincipal


_OWNER_DELETION_AUDIT_NAMESPACE = UUID(
    "790ea7ad-e41c-4cdf-bca2-89f6e7ea2478"
)
MAX_OWNER_RUN_INSPECTION_EVENTS = 100


class OwnerDataStorageError(RuntimeError):
    """Raised with no backend details when owner-data storage is unavailable."""


class OwnerDataCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preferences: int = Field(ge=0)
    cart_items: int = Field(ge=0)
    pending_actions: int = Field(ge=0)
    candidate_contexts: int = Field(ge=0)
    conversation_threads: int = Field(ge=0)
    conversation_messages: int = Field(ge=0)
    agent_runs: int = Field(ge=0)
    agent_run_events: int = Field(ge=0)
    conversation_summaries: int = Field(ge=0)
    idempotency_records: int = Field(ge=0)
    memory_records: int = Field(ge=0)


class OwnerMemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    memory_id: str = Field(min_length=1, max_length=128)
    thread_id: str | None = Field(default=None, max_length=128)
    kind: MemoryKind
    scope: MemoryScope
    content: str
    content_json: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(ge=0)
    token_count: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: Literal["active", "superseded", "deleted"]
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OwnerDataSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    counts: OwnerDataCounts
    total_records: int = Field(ge=0)
    memories: list[OwnerMemoryRecord]
    memory_limit: int = Field(
        ge=1,
        le=MAX_OWNER_MEMORY_INSPECTION_RECORDS,
    )
    memory_truncated: bool


class OwnerMemoryCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["corrected"] = "corrected"
    memory: OwnerMemoryRecord


class OwnerMemoryDeletion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["deleted"] = "deleted"
    memory_id: str


class OwnerDataDeletion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["deleted", "already_deleted"]
    deletion_request_id: UUID
    records_affected: int = Field(ge=0)
    counts: OwnerDataCounts


class OwnerRunEventSummary(BaseModel):
    """Client-visible event metadata with no arbitrary event payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=128)
    agent_name: str | None = Field(default=None, max_length=128)
    visibility: EventVisibility
    created_at: datetime


class OwnerRunInspection(BaseModel):
    """Exact-owner run projection safe for the reference client."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    schema_version: Literal["shopmind.owner-run-inspection.v1"] = (
        "shopmind.owner-run-inspection.v1"
    )
    run_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    operation: RunOperation
    mode: RunMode
    status: RunStatus
    pending_action_id: str | None = Field(default=None, max_length=128)
    usage: RunUsage
    started_at: datetime
    completed_at: datetime | None = None
    client_event_count: int = Field(ge=0)
    events: list[OwnerRunEventSummary]
    event_limit: int = Field(
        ge=1,
        le=MAX_OWNER_RUN_INSPECTION_EVENTS,
    )
    events_truncated: bool


def _deletion_factory(
    *,
    request_id: UUID,
    phase: str,
    decision: AuditDecision,
    occurred_at: datetime,
) -> GovernanceAuditFactory:
    audit_id = uuid5(
        _OWNER_DELETION_AUDIT_NAMESPACE,
        f"{request_id}\0{phase}\0{decision.value}",
    )
    return GovernanceAuditFactory(
        clock=lambda: occurred_at,
        audit_id_factory=lambda: audit_id,
    )


class OwnerDataService:
    """Execute exact-owner operations without exposing storage failure details."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        audit_emitter: GovernanceAuditEmitter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit_emitter = audit_emitter or GovernanceAuditEmitter(None)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def inspect(
        self,
        *,
        owner_id: str,
        principal: AuthenticatedPrincipal,
        memory_limit: int,
        audit_enabled: bool,
    ) -> OwnerDataSnapshot:
        session = self._open_session()
        try:
            raw = inspect_owner_data(
                session,
                owner_id=owner_id,
                memory_limit=memory_limit,
            )
            snapshot = OwnerDataSnapshot.model_validate(raw)
        except Exception as exc:
            self._rollback(session)
            raise OwnerDataStorageError("Owner data storage unavailable.") from exc
        finally:
            self._close(session)

        if audit_enabled:
            records = []
            for memory in snapshot.memories:
                try:
                    records.append(
                        GovernanceAuditFactory(clock=self._clock).memory_decision(
                            operation=AuditOperation.MEMORY_INSPECT,
                            decision=AuditDecision.SUCCEEDED,
                            reason=AuditReason.OWNER_MATCHED,
                            memory_id=memory.memory_id,
                            memory_kind=MemoryKind(memory.kind),
                            memory_scope=MemoryScope(memory.scope),
                            principal=principal,
                            owner_id=owner_id,
                            thread_id=memory.thread_id,
                            records_affected=1,
                        )
                    )
                except Exception:
                    continue
            self._audit_emitter.emit_many(records)
        return snapshot

    def inspect_run(
        self,
        *,
        owner_id: str,
        run_id: str | None,
        trace_id: str | None,
        event_limit: int,
    ) -> OwnerRunInspection | None:
        """Return only exact-owner run metadata and client-visible events."""

        session = self._open_session()
        try:
            raw = inspect_owner_agent_run(
                session,
                owner_id=owner_id,
                run_id=run_id,
                trace_id=trace_id,
                event_limit=event_limit,
            )
            result = (
                None
                if raw is None
                else OwnerRunInspection.model_validate(raw)
            )
        except Exception as exc:
            self._rollback(session)
            raise OwnerDataStorageError(
                "Owner data storage unavailable."
            ) from exc
        finally:
            self._close(session)
        return result

    def correct_memory(
        self,
        *,
        owner_id: str,
        principal: AuthenticatedPrincipal,
        memory_id: str,
        content: str,
        audit_enabled: bool,
    ) -> OwnerMemoryCorrection | None:
        session = self._open_session()
        try:
            raw = correct_owner_memory_record(
                session,
                owner_id=owner_id,
                memory_id=memory_id,
                content=content,
                now=self._clock(),
            )
            if raw is None:
                session.rollback()
                if audit_enabled:
                    self._emit_missing_memory(
                        operation=AuditOperation.MEMORY_CORRECT,
                        memory_id=memory_id,
                        principal=principal,
                        owner_id=owner_id,
                    )
                return None
            result = OwnerMemoryCorrection(
                memory=OwnerMemoryRecord.model_validate(raw)
            )
            session.commit()
        except Exception as exc:
            self._rollback(session)
            raise OwnerDataStorageError("Owner data storage unavailable.") from exc
        finally:
            self._close(session)

        if audit_enabled:
            self._emit_memory(
                operation=AuditOperation.MEMORY_CORRECT,
                memory=result.memory,
                principal=principal,
                owner_id=owner_id,
            )
        return result

    def delete_memory(
        self,
        *,
        owner_id: str,
        principal: AuthenticatedPrincipal,
        memory_id: str,
        audit_enabled: bool,
    ) -> OwnerMemoryDeletion | None:
        session = self._open_session()
        try:
            raw = delete_owner_memory_record(
                session,
                owner_id=owner_id,
                memory_id=memory_id,
            )
            if raw is None:
                session.rollback()
                if audit_enabled:
                    self._emit_missing_memory(
                        operation=AuditOperation.MEMORY_DELETE,
                        memory_id=memory_id,
                        principal=principal,
                        owner_id=owner_id,
                    )
                return None
            result = OwnerMemoryDeletion(memory_id=raw["memory_id"])
            session.commit()
        except Exception as exc:
            self._rollback(session)
            raise OwnerDataStorageError("Owner data storage unavailable.") from exc
        finally:
            self._close(session)

        if audit_enabled:
            try:
                record = GovernanceAuditFactory(clock=self._clock).memory_decision(
                    operation=AuditOperation.MEMORY_DELETE,
                    decision=AuditDecision.SUCCEEDED,
                    reason=AuditReason.USER_REQUESTED,
                    memory_id=raw["memory_id"],
                    memory_kind=MemoryKind(raw["kind"]),
                    memory_scope=MemoryScope(raw["scope"]),
                    principal=principal,
                    owner_id=owner_id,
                    thread_id=raw["thread_id"],
                    records_affected=1,
                )
                self._audit_emitter.emit(record)
            except Exception:
                pass
        return result

    def delete_all(
        self,
        *,
        owner_id: str,
        principal: AuthenticatedPrincipal,
        deletion_request_id: UUID,
        audit_enabled: bool,
    ) -> OwnerDataDeletion:
        occurred_at = self._clock()
        if audit_enabled:
            self._emit_deletion(
                request_id=deletion_request_id,
                phase="request",
                operation=AuditOperation.DELETION_REQUEST,
                decision=AuditDecision.REQUESTED,
                reason=AuditReason.USER_REQUESTED,
                principal=principal,
                owner_id=owner_id,
                records_affected=None,
                occurred_at=occurred_at,
            )

        try:
            session = self._open_session()
        except OwnerDataStorageError:
            if audit_enabled:
                self._emit_deletion(
                    request_id=deletion_request_id,
                    phase="execute",
                    operation=AuditOperation.DELETION_EXECUTE,
                    decision=AuditDecision.FAILED,
                    reason=AuditReason.PROVIDER_FAILED,
                    principal=principal,
                    owner_id=owner_id,
                    records_affected=None,
                    occurred_at=self._clock(),
                )
            raise
        try:
            raw_counts = delete_all_owner_data(session, owner_id=owner_id)
            counts = OwnerDataCounts.model_validate(raw_counts)
            records_affected = sum(raw_counts.values())
            result = OwnerDataDeletion(
                status=(
                    "deleted" if records_affected else "already_deleted"
                ),
                deletion_request_id=deletion_request_id,
                records_affected=records_affected,
                counts=counts,
            )
            session.commit()
        except Exception as exc:
            self._rollback(session)
            if audit_enabled:
                self._emit_deletion(
                    request_id=deletion_request_id,
                    phase="execute",
                    operation=AuditOperation.DELETION_EXECUTE,
                    decision=AuditDecision.FAILED,
                    reason=AuditReason.PROVIDER_FAILED,
                    principal=principal,
                    owner_id=owner_id,
                    records_affected=None,
                    occurred_at=self._clock(),
                )
            raise OwnerDataStorageError("Owner data storage unavailable.") from exc
        finally:
            self._close(session)

        if audit_enabled:
            self._emit_deletion(
                request_id=deletion_request_id,
                phase="execute",
                operation=AuditOperation.DELETION_EXECUTE,
                decision=(
                    AuditDecision.SUCCEEDED
                    if result.status == "deleted"
                    else AuditDecision.SKIPPED
                ),
                reason=(
                    AuditReason.COMPLETED
                    if result.status == "deleted"
                    else AuditReason.ALREADY_DELETED
                ),
                principal=principal,
                owner_id=owner_id,
                records_affected=result.records_affected,
                occurred_at=self._clock(),
            )
        return result

    def _emit_memory(
        self,
        *,
        operation: AuditOperation,
        memory: OwnerMemoryRecord,
        principal: AuthenticatedPrincipal,
        owner_id: str,
    ) -> None:
        try:
            record = GovernanceAuditFactory(clock=self._clock).memory_decision(
                operation=operation,
                decision=AuditDecision.SUCCEEDED,
                reason=AuditReason.COMPLETED,
                memory_id=memory.memory_id,
                memory_kind=MemoryKind(memory.kind),
                memory_scope=MemoryScope(memory.scope),
                principal=principal,
                owner_id=owner_id,
                thread_id=memory.thread_id,
                records_affected=1,
            )
            self._audit_emitter.emit(record)
        except Exception:
            pass

    def _emit_missing_memory(
        self,
        *,
        operation: AuditOperation,
        memory_id: str,
        principal: AuthenticatedPrincipal,
        owner_id: str,
    ) -> None:
        try:
            record = GovernanceAuditFactory(clock=self._clock).memory_decision(
                operation=operation,
                decision=AuditDecision.NOT_FOUND,
                reason=AuditReason.NOT_FOUND,
                memory_id=memory_id,
                memory_kind=None,
                memory_scope=None,
                principal=principal,
                owner_id=owner_id,
                records_affected=0,
            )
            self._audit_emitter.emit(record)
        except Exception:
            pass

    def _emit_deletion(
        self,
        *,
        request_id: UUID,
        phase: str,
        operation: AuditOperation,
        decision: AuditDecision,
        reason: AuditReason,
        principal: AuthenticatedPrincipal,
        owner_id: str,
        records_affected: int | None,
        occurred_at: datetime,
    ) -> None:
        try:
            record = _deletion_factory(
                request_id=request_id,
                phase=phase,
                decision=decision,
                occurred_at=occurred_at,
            ).deletion_decision(
                operation=operation,
                decision=decision,
                reason=reason,
                deletion_request_id=str(request_id),
                deletion_target=AuditDeletionTarget.USER_DATA,
                principal=principal,
                owner_id=owner_id,
                records_affected=records_affected,
            )
            self._audit_emitter.emit(record)
        except Exception:
            pass

    def _open_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise OwnerDataStorageError("Owner data storage unavailable.") from exc

    @staticmethod
    def _rollback(session: Session) -> None:
        try:
            session.rollback()
        except Exception:
            pass

    @staticmethod
    def _close(session: Session) -> None:
        try:
            session.close()
        except Exception:
            pass


__all__ = [
    "OwnerDataCounts",
    "OwnerDataDeletion",
    "OwnerDataService",
    "OwnerDataSnapshot",
    "OwnerDataStorageError",
    "OwnerMemoryCorrection",
    "OwnerMemoryDeletion",
    "OwnerMemoryRecord",
]
