"""Best-effort production emission for closed governance audit records."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import StrEnum
import logging
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.repositories.governance_audit import (
    GovernanceAuditConflictError,
    append_governance_audit_record,
)
from app.runtime.contracts import ActionRiskClass, RunContext, RunResult
from app.security.audit import (
    AuditDecision,
    AuditOperation,
    AuditReason,
    GovernanceAuditFactory,
    GovernanceAuditRecord,
)

from .monitoring import (
    GovernanceAuditEmissionMonitor,
    governance_audit_monitor,
)


_GOVERNANCE_EVENT_NAMESPACE = UUID("c9c51e28-b5f2-4ce1-875d-8b0ee8e7458d")
logger = logging.getLogger(__name__)


class GovernanceAuditEmissionStatus(StrEnum):
    PERSISTED = "persisted"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"
    FAILED = "failed"


class GovernanceAuditEmissionReason(StrEnum):
    COMPLETED = "completed"
    ALREADY_EXISTS = "already_exists"
    DISABLED = "disabled"
    NO_RECORDS = "no_records"
    STORAGE_UNAVAILABLE = "storage_unavailable"


class GovernanceAuditEmissionResult(BaseModel):
    """Sanitized audit outcome; storage exceptions and identifiers never escape."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    status: GovernanceAuditEmissionStatus
    reason: GovernanceAuditEmissionReason
    requested_records: int = Field(ge=0)
    persisted_records: int = Field(ge=0)
    duplicate_records: int = Field(ge=0)


class GovernanceAuditEmitter:
    """Commit an audit batch independently without changing business outcomes."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | None,
        *,
        monitor: GovernanceAuditEmissionMonitor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._monitor = monitor or governance_audit_monitor

    def emit(
        self,
        record: GovernanceAuditRecord,
    ) -> GovernanceAuditEmissionResult:
        return self.emit_many([record])

    def emit_many(
        self,
        records: Iterable[GovernanceAuditRecord],
    ) -> GovernanceAuditEmissionResult:
        batch = list(records)
        requested = len(batch)
        if not batch:
            return self._finish(
                GovernanceAuditEmissionResult(
                    status=GovernanceAuditEmissionStatus.SKIPPED,
                    reason=GovernanceAuditEmissionReason.NO_RECORDS,
                    requested_records=0,
                    persisted_records=0,
                    duplicate_records=0,
                )
            )
        if self._session_factory is None:
            return self._finish(
                GovernanceAuditEmissionResult(
                    status=GovernanceAuditEmissionStatus.SKIPPED,
                    reason=GovernanceAuditEmissionReason.DISABLED,
                    requested_records=requested,
                    persisted_records=0,
                    duplicate_records=0,
                )
            )

        session: Session | None = None
        persisted = 0
        duplicates = 0
        try:
            session = self._session_factory()
            for record in batch:
                try:
                    append_governance_audit_record(session, record=record)
                    persisted += 1
                except GovernanceAuditConflictError:
                    duplicates += 1
            session.commit()
        except Exception:
            if session is not None:
                try:
                    session.rollback()
                except Exception:
                    pass
            return self._finish(
                GovernanceAuditEmissionResult(
                    status=GovernanceAuditEmissionStatus.FAILED,
                    reason=GovernanceAuditEmissionReason.STORAGE_UNAVAILABLE,
                    requested_records=requested,
                    persisted_records=0,
                    duplicate_records=0,
                )
            )
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

        if persisted:
            return self._finish(
                GovernanceAuditEmissionResult(
                    status=GovernanceAuditEmissionStatus.PERSISTED,
                    reason=GovernanceAuditEmissionReason.COMPLETED,
                    requested_records=requested,
                    persisted_records=persisted,
                    duplicate_records=duplicates,
                )
            )
        return self._finish(
            GovernanceAuditEmissionResult(
                status=GovernanceAuditEmissionStatus.DUPLICATE,
                reason=GovernanceAuditEmissionReason.ALREADY_EXISTS,
                requested_records=requested,
                persisted_records=0,
                duplicate_records=duplicates,
            )
        )

    def _finish(
        self,
        result: GovernanceAuditEmissionResult,
    ) -> GovernanceAuditEmissionResult:
        observation = None
        try:
            observation = self._monitor.observe(result)
        except Exception:
            logger.warning(
                "Governance audit monitoring unavailable: "
                "event=governance_audit_monitoring_unavailable"
            )

        if result.status == GovernanceAuditEmissionStatus.FAILED:
            logger.warning(
                "Governance audit emission failed: "
                "event=governance_audit_emission_failed "
                "reason=%s records=%d consecutive_failures=%s",
                result.reason,
                result.requested_records,
                (
                    observation.consecutive_failures
                    if observation is not None
                    else "unknown"
                ),
            )
            if observation is not None and observation.alert_activated:
                logger.error(
                    "Governance audit emission alert: "
                    "event=governance_audit_emission_alert "
                    "state=active reason=%s consecutive_failures=%d "
                    "threshold=%d",
                    result.reason,
                    observation.consecutive_failures,
                    observation.alert_failure_threshold,
                )
        elif observation is not None and observation.alert_recovered:
            logger.info(
                "Governance audit emission alert: "
                "event=governance_audit_emission_alert "
                "state=recovered consecutive_failures=0 threshold=%d",
                observation.alert_failure_threshold,
            )
        return result


def _event_factory(source: str, occurred_at) -> GovernanceAuditFactory:
    audit_id = uuid5(_GOVERNANCE_EVENT_NAMESPACE, source)
    return GovernanceAuditFactory(
        clock=lambda: occurred_at,
        audit_id_factory=lambda: audit_id,
    )


def _runtime_thread_id(context: RunContext, result: RunResult) -> str | None:
    if result.client_thread_id:
        return result.client_thread_id
    raw_thread_id = context.request.input_data.get("thread_id")
    if isinstance(raw_thread_id, str) and raw_thread_id.strip():
        return raw_thread_id
    return None


def _action_failure_classification(
    reason: object,
) -> tuple[AuditDecision, AuditReason]:
    if reason in {
        "unresolved_or_scope_denied",
        "invalid_edit",
        "unregistered_action",
    }:
        return AuditDecision.DENIED, (
            AuditReason.POLICY_DENIED
            if reason == "unresolved_or_scope_denied"
            else AuditReason.VALIDATION_FAILED
        )
    return AuditDecision.FAILED, AuditReason.PROVIDER_FAILED


def project_runtime_governance_records(
    context: RunContext,
    result: RunResult,
) -> list[GovernanceAuditRecord]:
    """Project only typed tool/action facts; arbitrary event payloads are ignored."""

    records: list[GovernanceAuditRecord] = []
    owner_id = result.user_id
    thread_id = _runtime_thread_id(context, result)

    for tool_record in result.tool_call_records:
        try:
            records.append(
                _event_factory(
                    (
                        f"tool\0{result.run_id}\0{tool_record.tool_call_id}"
                        f"\0{tool_record.status}"
                    ),
                    result.completed_at,
                ).tool_decision(
                    record=tool_record,
                    principal=None,
                    owner_id=owner_id,
                    thread_id=thread_id,
                    run_id=result.run_id,
                )
            )
        except Exception:
            continue

    context_slice = context.context_slice
    if context_slice is not None:
        for item in context_slice.items:
            if item.provenance.get("source") == "current_request":
                continue
            try:
                records.append(
                    _event_factory(
                        (
                            f"memory\0{result.run_id}\0{item.memory_id}"
                            f"\0{item.kind}\0{item.scope}"
                        ),
                        result.completed_at,
                    ).memory_decision(
                        operation=AuditOperation.MEMORY_INSPECT,
                        decision=AuditDecision.SUCCEEDED,
                        reason=AuditReason.OWNER_MATCHED,
                        memory_id=item.memory_id,
                        memory_kind=item.kind,
                        memory_scope=item.scope,
                        principal=None,
                        owner_id=owner_id,
                        thread_id=item.thread_id or thread_id,
                        run_id=result.run_id,
                        records_affected=1,
                    )
                )
            except Exception:
                continue

    for event in result.events:
        payload = event.payload
        action_id = payload.get("action_id")
        if (
            not isinstance(action_id, str)
            or not action_id.strip()
            or owner_id is None
        ):
            continue
        action_type = payload.get("action_type")
        if not isinstance(action_type, str) or not action_type.strip():
            action_type = "pending_action"

        operation: AuditOperation
        decision: AuditDecision
        reason: AuditReason
        if event.event_type == "action.prepared":
            operation = AuditOperation.ACTION_PREPARE
            decision = AuditDecision.SUCCEEDED
            reason = AuditReason.COMPLETED
        elif event.event_type == "action.resumed":
            operation = AuditOperation.ACTION_RESUME
            decision = AuditDecision.SUCCEEDED
            reason = AuditReason.OWNER_MATCHED
        elif event.event_type == "action.confirmed":
            operation = AuditOperation.ACTION_CONFIRM
            decision = AuditDecision.SUCCEEDED
            reason = AuditReason.COMPLETED
        elif event.event_type == "action.cancelled":
            operation = AuditOperation.ACTION_CANCEL
            decision = AuditDecision.SUCCEEDED
            reason = AuditReason.CANCELLED
        elif event.event_type == "action.expired":
            operation = AuditOperation.ACTION_EXPIRE
            decision = AuditDecision.SUCCEEDED
            reason = AuditReason.EXPIRED
        elif event.event_type == "action.failed":
            operation = (
                AuditOperation.ACTION_CONFIRM
                if context.request.input_data.get("confirmed", True)
                else AuditOperation.ACTION_CANCEL
            )
            decision, reason = _action_failure_classification(payload.get("reason"))
        else:
            continue

        risk_class = None
        raw_risk_class = payload.get("risk_class")
        if raw_risk_class is not None:
            try:
                risk_class = ActionRiskClass(raw_risk_class)
            except ValueError:
                risk_class = None
        try:
            records.append(
                _event_factory(
                    (
                        f"action\0{result.run_id}\0{event.sequence}"
                        f"\0{operation.value}\0{action_id}"
                    ),
                    event.timestamp,
                ).action_decision(
                    operation=operation,
                    decision=decision,
                    reason=reason,
                    action_type=action_type,
                    action_id=action_id,
                    principal=None,
                    owner_id=owner_id,
                    thread_id=thread_id,
                    run_id=result.run_id,
                    risk_class=risk_class,
                )
            )
        except Exception:
            continue

    return records
