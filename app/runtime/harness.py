"""Thin V4.1 harness around existing ShopMind V3 execution paths."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import perf_counter
from typing import TYPE_CHECKING, Any, Callable, Iterator

from sqlalchemy.orm import Session

from app.core.chat_errors import (
    public_error,
    public_error_for_result,
    sanitize_public_debug,
)
from app.db.session import SessionLocal
from app.repositories.runtime_conversations import (
    append_conversation_message,
    get_or_create_conversation_thread,
)
from app.repositories.runtime_runs import (
    append_agent_run_event,
    claim_idempotency_record,
    create_agent_run,
    finalize_agent_run,
    get_agent_run,
    get_idempotency_record,
    RuntimeIdempotencyPersistenceError,
    save_idempotency_record,
)

from .adapters import (
    AgentAdapterError,
    AgentTransportError,
    DelegationBudgetError,
    DelegationTimeBudgetError,
    DelegationUsageBudgetError,
)
from .contracts import (
    AgentEvent,
    ContextSlice,
    ErrorSource,
    EventVisibility,
    RunContext,
    RunError,
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    ToolCallRecord,
    ToolCallStatus,
    ToolSideEffectClass,
    aggregate_run_usage,
)
from .context import RuntimeContextManager
from .tool_gateway import ToolGatewayExecutionError


if TYPE_CHECKING:
    from app.governance import GovernanceAuditEmitter
    from .service_monitoring import RuntimeServiceMonitor


LegacyExecutor = Callable[[RunContext], dict[str, Any]]
CancellationCheck = Callable[[], bool]
EventSink = Callable[[AgentEvent], None]


class _EventList(list[AgentEvent]):
    """List-compatible event collector that can mirror events to a stream."""

    def __init__(self, sink: EventSink | None = None) -> None:
        super().__init__()
        self._sink = sink
        self._lock = RLock()

    def append(self, event: AgentEvent) -> None:
        with self._lock:
            super().append(event)
            self._publish(event)

    def emit(
        self,
        *,
        event_type: str,
        visibility: EventVisibility,
        trace_id: str,
        payload: dict[str, Any],
        agent_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> AgentEvent:
        """Allocate and publish one event sequence atomically."""

        with self._lock:
            event = AgentEvent(
                sequence=len(self) + 1,
                event_type=event_type,
                agent_name=agent_name,
                trace_id=trace_id,
                visibility=visibility,
                payload=payload,
                tool_call_id=tool_call_id,
            )
            super().append(event)
            self._publish(event)
            return event

    def _publish(self, event: AgentEvent) -> None:
        if self._sink is not None:
            try:
                self._sink(event)
            except Exception:
                # A disconnected stream must not change the Agent result.
                pass


class RuntimeExecutionError(Exception):
    """Structured control/error signal understood by the runtime Harness."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        source: ErrorSource = ErrorSource.AGENT,
        retriable: bool = False,
        details: dict[str, Any] | None = None,
        usage: RunUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source
        self.retriable = retriable
        self.details = details or {}
        self.usage = None if usage is None else usage.model_copy(deep=True)


TOOL_SIDE_EFFECT_OVERRIDES: dict[str, ToolSideEffectClass] = {
    "prepare_add_to_cart": ToolSideEffectClass.SENSITIVE_WRITE,
    "confirm_add_to_cart": ToolSideEffectClass.SENSITIVE_WRITE,
    "cancel_pending_action": ToolSideEffectClass.SENSITIVE_WRITE,
}

DEFAULT_THREAD_RETENTION_DAYS = 30
DEFAULT_RUN_RETENTION_DAYS = 30
DEFAULT_IDEMPOTENCY_RETENTION_DAYS = 7
TERMINAL_IDEMPOTENCY_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.CONFIRMATION_REQUIRED,
    RunStatus.CANCELLED,
    RunStatus.FAILED,
}


def _status_from_legacy(value: Any) -> RunStatus:
    normalized = str(value or "completed")
    try:
        return RunStatus(normalized)
    except ValueError:
        return RunStatus.FAILED


def _tool_side_effect_class(tool_name: str) -> ToolSideEffectClass:
    if tool_name in TOOL_SIDE_EFFECT_OVERRIDES:
        return TOOL_SIDE_EFFECT_OVERRIDES[tool_name]
    lowered = tool_name.lower()
    if lowered.startswith(("search_", "get_", "list_", "read_", "retrieve_")):
        return ToolSideEffectClass.READ
    return ToolSideEffectClass.NONE


def run_result_to_legacy_response(
    result: RunResult,
    *,
    include_debug: bool = False,
) -> dict[str, Any]:
    error_code = (
        result.error.code
        if result.error is not None
        else result.metadata.get("runtime_error_code")
    )
    public_failure = public_error_for_result(
        status=result.status,
        code=error_code,
        retry_state=result.metadata.get("retry_state", "terminal"),
        authoritative_run_id=result.metadata.get("authoritative_run_id"),
    )
    response = {
        "answer": public_failure.message if public_failure else result.answer,
        "status": result.status,
        "tool_calls": result.tool_calls,
        "pending_action_id": result.pending_action_id,
        "run_id": result.run_id,
        "trace_id": result.trace_id,
        "retry_state": public_failure.retry_state if public_failure else result.metadata.get("retry_state", "terminal"),
        "runtime_error_code": public_failure.code if public_failure else error_code,
        "authoritative_run_id": (
            public_failure.authoritative_run_id
            if public_failure
            else result.metadata.get("authoritative_run_id")
        ),
    }
    if "recommendation" in result.output_data:
        response["recommendation"] = result.output_data["recommendation"]
    if include_debug and result.debug is not None:
        safe_debug = sanitize_public_debug(result.debug)
        if safe_debug:
            response["debug"] = safe_debug
    return response


class ShopMindRuntimeHarness:
    """Wrap legacy execution with V4.1 runtime contracts and best-effort persistence."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | None = SessionLocal,
        *,
        context_manager: RuntimeContextManager | None = None,
        governance_audit_emitter: "GovernanceAuditEmitter | None" = None,
        service_monitor: "RuntimeServiceMonitor | None" = None,
    ):
        from app.governance import GovernanceAuditEmitter
        from .service_monitoring import runtime_service_monitor

        self._session_factory = session_factory
        self._context_manager = context_manager or RuntimeContextManager(session_factory)
        self._governance_audit_emitter = (
            governance_audit_emitter
            if governance_audit_emitter is not None
            else GovernanceAuditEmitter(session_factory)
        )
        self._service_monitor = service_monitor or runtime_service_monitor

    def run(
        self,
        request: RunRequest,
        executor: LegacyExecutor,
        *,
        parent_run_id: str | None = None,
        raise_on_error: bool = True,
        cancellation_check: CancellationCheck | None = None,
        event_sink: EventSink | None = None,
    ) -> RunResult:
        """Run once and observe only closed service-level facts."""

        started = perf_counter()
        try:
            result = self._run(
                request,
                executor,
                parent_run_id=parent_run_id,
                raise_on_error=raise_on_error,
                cancellation_check=cancellation_check,
                event_sink=event_sink,
            )
        except Exception:
            try:
                self._service_monitor.observe_failure(
                    operation=request.operation,
                    duration_ms=max(0.0, (perf_counter() - started) * 1000),
                )
            except Exception:
                pass
            raise
        try:
            self._service_monitor.observe(
                result,
                operation=request.operation,
                duration_ms=max(0.0, (perf_counter() - started) * 1000),
                replayed=bool(
                    result.metadata.get("idempotency_replayed", False)
                ),
            )
        except Exception:
            pass
        return result

    def _run(
        self,
        request: RunRequest,
        executor: LegacyExecutor,
        *,
        parent_run_id: str | None = None,
        raise_on_error: bool = True,
        cancellation_check: CancellationCheck | None = None,
        event_sink: EventSink | None = None,
    ) -> RunResult:
        context = RunContext(
            request=request,
            policy=request.policy,
            budget=request.budget,
            parent_run_id=parent_run_id,
        )
        context.bind_cancellation_check(cancellation_check)
        replay_result = self._resolve_idempotency(context)
        if replay_result is not None:
            replay_event = self._build_event(
                sequence=1,
                event_type=(
                    "run.replayed"
                    if replay_result.error is None
                    else "run.rejected"
                ),
                visibility=EventVisibility.CLIENT,
                trace_id=replay_result.trace_id,
                payload={
                    "idempotency_key": request.idempotency_key,
                    "original_run_id": replay_result.run_id,
                    "replayed": replay_result.error is None,
                },
            )
            replay_result.events = [replay_event]
            if event_sink is not None:
                event_sink(replay_event)
            return replay_result

        events = _EventList(event_sink)
        context.bind_event_emitter(
            lambda **event: events.emit(trace_id=context.trace_id, **event)
        )
        events.append(
            self._build_event(
                sequence=1,
                event_type="run.started",
                visibility=EventVisibility.CLIENT,
                trace_id=context.trace_id,
                payload={
                    "operation": request.operation,
                    "mode": request.mode,
                },
            )
        )
        start_result = self._persist_start(context, events[0])
        if start_result is not None:
            recovery_event = self._build_event(
                sequence=1,
                event_type="run.replayed" if start_result.error is None else "run.rejected",
                visibility=EventVisibility.CLIENT,
                trace_id=start_result.trace_id,
                payload={
                    "idempotency_key": request.idempotency_key,
                    "original_run_id": start_result.run_id,
                    "retry_state": start_result.metadata.get("retry_state"),
                },
            )
            start_result.events = [recovery_event]
            if event_sink is not None:
                event_sink(recovery_event)
            return start_result
        self._load_context(context, events)

        attempt = 0
        failed_attempt_usages: list[RunUsage] = []
        while True:
            control_error = self._check_controls(context, cancellation_check)
            if control_error is not None:
                result = self._build_control_result(context, events, control_error)
                return self._persist_or_fail_closed(context, result)

            try:
                raw_result = executor(context)
                self._validate_public_output(raw_result)
            except Exception as exc:
                runtime_error = self._as_runtime_error(exc)
                if runtime_error.usage is not None:
                    failed_attempt_usages.append(runtime_error.usage)
                if attempt < max(0, context.policy.max_retries) and runtime_error.retriable:
                    attempt += 1
                    events.append(
                        self._build_event(
                            sequence=len(events) + 1,
                            event_type="run.retrying",
                            visibility=EventVisibility.INTERNAL,
                            trace_id=context.trace_id,
                            payload={
                                "attempt": attempt,
                                "max_retries": context.policy.max_retries,
                                "error_code": runtime_error.code,
                            },
                        )
                    )
                    continue

                result = self._build_exception_result(
                    context,
                    events,
                    exc,
                    runtime_error=runtime_error,
                    usage=(
                        aggregate_run_usage(failed_attempt_usages)
                        if failed_attempt_usages
                        else None
                    ),
                )
                persisted_result = self._persist_or_fail_closed(context, result)
                if persisted_result is not result:
                    return persisted_result
                if raise_on_error:
                    raise
                return result

            accounted_raw_result = raw_result
            if failed_attempt_usages:
                raw_success_usages = raw_result.get("delegated_usage", [])
                if not isinstance(raw_success_usages, list):
                    raw_success_usages = []
                accounted_raw_result = {
                    **raw_result,
                    "delegated_usage": [
                        usage.model_dump(mode="python")
                        for usage in failed_attempt_usages
                    ]
                    + raw_success_usages,
                }

            control_error = self._check_controls(context, cancellation_check)
            if control_error is None:
                control_error = self._check_result_budgets(
                    context,
                    accounted_raw_result,
                )
            if control_error is not None:
                result = self._build_control_result(
                    context,
                    events,
                    control_error,
                    raw_result=accounted_raw_result,
                )
                return self._persist_or_fail_closed(context, result)

            result = self._build_success_result(context, events, raw_result)
            if failed_attempt_usages:
                result.usage = aggregate_run_usage(
                    [*failed_attempt_usages, result.usage]
                )
            result.metadata["attempts"] = attempt + 1
            return self._persist_or_fail_closed(context, result)

    def _resolve_idempotency(self, context: RunContext) -> RunResult | None:
        key = context.request.idempotency_key
        if not key:
            return None

        with self._open_session() as session:
            if session is None:
                return None
            record = get_idempotency_record(
                session,
                user_id=context.user_id,
                operation=context.request.operation,
                idempotency_key=key,
            )

            if record is None or self._idempotency_record_expired(record, context.started_at):
                return None
            if record["request_hash"] != self._request_hash(context.request):
                return self._idempotency_error_result(
                    context,
                    code="runtime.idempotency_key_conflict",
                    message="Idempotency key was already used for a different request.",
                    retriable=False,
                    authoritative_run_id=record.get("run_id"),
                )
            if record["status"] == RunStatus.STARTED:
                return self._idempotency_error_result(
                    context,
                    code="runtime.idempotency_in_progress",
                    message="An equivalent request is already in progress.",
                    retriable=True,
                    retry_state="in_progress",
                    authoritative_run_id=record.get("run_id"),
                )

            try:
                status = RunStatus(record["status"])
            except ValueError:
                return self._idempotency_error_result(
                    context,
                    code="runtime.idempotency_record_invalid",
                    message="The stored idempotency record is invalid.",
                    retriable=False,
                )
            if status not in TERMINAL_IDEMPOTENCY_STATUSES or not record["run_id"]:
                return self._idempotency_error_result(
                    context,
                    code="runtime.idempotency_result_unavailable",
                    message="The stored idempotency result is unavailable.",
                    retriable=True,
                )

            run = get_agent_run(session, run_id=record["run_id"])
            if run is None:
                return self._idempotency_error_result(
                    context,
                    code="runtime.idempotency_result_unavailable",
                    message="The stored idempotency result is unavailable.",
                    retriable=True,
                )
            return self._run_result_from_persisted_run(run)

    @staticmethod
    def _idempotency_record_expired(record: dict[str, Any], now: datetime) -> bool:
        expires_at = record.get("expires_at")
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= now

    def _idempotency_error_result(
        self,
        context: RunContext,
        *,
        code: str,
        message: str,
        retriable: bool,
        retry_state: str = "terminal",
        authoritative_run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> RunResult:
        return RunResult(
            run_id=authoritative_run_id or context.run_id,
            runtime_thread_id=context.runtime_thread_id,
            trace_id=context.trace_id,
            request_id=context.request.request_id,
            user_id=context.user_id,
            client_thread_id=context.client_thread_id,
            status=RunStatus.FAILED,
            error=RunError(
                code=code,
                message=message,
                source=ErrorSource.VALIDATION,
                retriable=retriable,
                details=details or {},
            ),
            metadata={
                "idempotency_rejected": True,
                "retry_state": retry_state,
                "runtime_error_code": code,
                "authoritative_run_id": authoritative_run_id,
            },
        )

    def _run_result_from_persisted_run(self, run: dict[str, Any]) -> RunResult:
        status = RunStatus(run["status"])
        error_json = run.get("error_json")
        return RunResult(
            run_id=run["run_id"],
            runtime_thread_id=run["thread_id"],
            trace_id=run["trace_id"],
            request_id=run["request_id"],
            user_id=run["user_id"],
            client_thread_id=run["request_json"].get("thread_id"),
            status=status,
            answer=run.get("output_text") or "",
            output_data=run.get("result_json") or {},
            tool_calls=[
                record["tool_name"]
                for record in run.get("tool_call_records_json") or []
                if record.get("tool_name")
            ],
            tool_call_records=[
                ToolCallRecord.model_validate(record)
                for record in run.get("tool_call_records_json") or []
            ],
            pending_action_id=run.get("pending_action_id"),
            usage=RunUsage.model_validate(run.get("usage_json") or {}),
            error=None if error_json is None else RunError.model_validate(error_json),
            debug=run.get("debug_json"),
            completed_at=run.get("completed_at") or run["updated_at"],
            metadata={
                **(run.get("metadata") or {}),
                "idempotency_replayed": True,
                "retry_state": "terminal",
            },
        )

    def _load_context(self, context: RunContext, events: list[AgentEvent]) -> None:
        try:
            context.context_slice = self._context_manager.build(context)
        except Exception as exc:
            context.context_slice = ContextSlice(
                token_budget=context.budget.max_prompt_tokens,
                metadata={"fallback": True, "error_type": exc.__class__.__name__},
            )
            events.append(
                self._build_event(
                    sequence=len(events) + 1,
                    event_type="memory.load.failed",
                    visibility=EventVisibility.INTERNAL,
                    trace_id=context.trace_id,
                    payload={"error_type": exc.__class__.__name__},
                )
            )
            events.append(
                self._build_event(
                    sequence=len(events) + 1,
                    event_type="context.built",
                    visibility=EventVisibility.INTERNAL,
                    trace_id=context.trace_id,
                    payload={"fallback": True, "item_count": 0},
                )
            )
            return

        context_slice = context.context_slice
        events.append(
            self._build_event(
                sequence=len(events) + 1,
                event_type="memory.loaded",
                visibility=EventVisibility.INTERNAL,
                trace_id=context.trace_id,
                payload={
                    "item_count": len(context_slice.items),
                    "omitted_count": context_slice.omitted_count,
                },
            )
        )
        events.append(
            self._build_event(
                sequence=len(events) + 1,
                event_type="context.built",
                visibility=EventVisibility.INTERNAL,
                trace_id=context.trace_id,
                payload={
                    "estimated_tokens": context_slice.estimated_tokens,
                    "token_budget": context_slice.token_budget,
                },
            )
        )

    def _check_controls(
        self,
        context: RunContext,
        cancellation_check: CancellationCheck | None,
    ) -> RuntimeExecutionError | None:
        if context.refresh_cancellation():
            return RuntimeExecutionError(
                "runtime.cancelled",
                "run cancellation was requested",
                source=ErrorSource.CANCELLATION,
                details={"run_id": context.run_id},
            )

        now = datetime.now(timezone.utc)
        deadline = context.request.deadline_at or context.budget.deadline_at
        if deadline is not None and self._as_utc(deadline) <= now:
            return RuntimeExecutionError(
                "runtime.deadline_exceeded",
                "run deadline has been exceeded",
                source=ErrorSource.TIMEOUT,
                details={"deadline_at": self._as_utc(deadline).isoformat()},
            )
        if context.budget.max_duration_ms is not None:
            elapsed_ms = (now - self._as_utc(context.started_at)).total_seconds() * 1000
            if elapsed_ms >= context.budget.max_duration_ms:
                return RuntimeExecutionError(
                    "runtime.duration_budget_exceeded",
                    "run duration budget has been exceeded",
                    source=ErrorSource.TIMEOUT,
                    details={"max_duration_ms": context.budget.max_duration_ms},
                )
        return None

    def _check_result_budgets(
        self,
        context: RunContext,
        raw_result: dict[str, Any],
    ) -> RuntimeExecutionError | None:
        debug = raw_result.get("debug")
        agent_steps = debug.get("agent_steps", []) if isinstance(debug, dict) else []
        tool_calls = raw_result.get("tool_calls", [])
        if (
            context.budget.max_steps is not None
            and isinstance(agent_steps, list)
            and len(agent_steps) > context.budget.max_steps
        ):
            return RuntimeExecutionError(
                "runtime.step_budget_exceeded",
                "run step budget has been exceeded",
                source=ErrorSource.AGENT,
                details={"max_steps": context.budget.max_steps, "actual_steps": len(agent_steps)},
            )
        if (
            context.budget.max_tool_calls is not None
            and isinstance(tool_calls, list)
            and len(tool_calls) > context.budget.max_tool_calls
        ):
            return RuntimeExecutionError(
                "runtime.tool_call_budget_exceeded",
                "run tool-call budget has been exceeded",
                source=ErrorSource.TOOL,
                details={
                    "max_tool_calls": context.budget.max_tool_calls,
                    "actual_tool_calls": len(tool_calls),
                },
            )
        usage = self._delegated_usage(raw_result)
        for budget_field, usage_field in (
            ("max_prompt_tokens", "input_tokens"),
            ("max_completion_tokens", "output_tokens"),
            ("max_total_tokens", "total_tokens"),
            ("max_cost_usd", "cost_usd"),
        ):
            limit = getattr(context.budget, budget_field)
            if limit is None:
                continue
            actual = getattr(usage, usage_field)
            if (
                budget_field == "max_total_tokens"
                and actual is None
                and usage.input_tokens is not None
                and usage.output_tokens is not None
            ):
                actual = usage.input_tokens + usage.output_tokens
            if actual is None:
                return RuntimeExecutionError(
                    "runtime.usage_budget_unavailable",
                    "run usage was unavailable for a configured budget",
                    source=ErrorSource.AGENT,
                    details={"budget_field": budget_field},
                )
            if actual > limit:
                return RuntimeExecutionError(
                    "runtime.usage_budget_exceeded",
                    "run usage budget has been exceeded",
                    source=ErrorSource.AGENT,
                    details={"budget_field": budget_field},
                )
        return None

    @staticmethod
    def _delegated_usage(raw_result: dict[str, Any]) -> RunUsage:
        raw_usages = raw_result.get("delegated_usage")
        if not isinstance(raw_usages, list):
            return RunUsage()

        usages: list[RunUsage] = []
        for raw_usage in raw_usages:
            try:
                usages.append(RunUsage.model_validate(raw_usage))
            except (TypeError, ValueError):
                continue

        return aggregate_run_usage(usages)

    def _as_runtime_error(self, exc: Exception) -> RuntimeExecutionError:
        if isinstance(exc, RuntimeExecutionError):
            return exc
        if isinstance(exc, ToolGatewayExecutionError):
            record = exc.tool_call_record
            error_code = str(
                record.result_metadata.get("error_code", "tool.execution_failed")
            )
            source = ErrorSource.TOOL
            if error_code in {
                "tool.deadline_exceeded",
                "tool.run_duration_budget_exceeded",
            }:
                source = ErrorSource.TIMEOUT
            if error_code == "tool.cancelled":
                source = ErrorSource.CANCELLATION
            return RuntimeExecutionError(
                error_code,
                "tool execution failed",
                source=source,
                details={
                    "tool_name": record.tool_name,
                    "tool_call_id": record.tool_call_id,
                },
            )
        typed_code = getattr(exc, "code", None)
        if typed_code:
            projection = public_error(typed_code)
            return RuntimeExecutionError(
                projection.code,
                projection.message,
                source=ErrorSource.VALIDATION,
                details={"exception_type": exc.__class__.__name__},
            )
        if isinstance(exc, AgentTransportError):
            return RuntimeExecutionError(
                exc.error_code,
                exc.safe_message,
                source=exc.source,
                retriable=exc.retriable,
                details={"exception_type": exc.__class__.__name__},
                usage=exc.usage,
            )
        if isinstance(exc, DelegationTimeBudgetError):
            return RuntimeExecutionError(
                exc.error_code,
                "Agent delegation time budget was exceeded.",
                source=ErrorSource.TIMEOUT,
                details={
                    "budget_field": exc.budget_field,
                    "phase": exc.phase,
                    "exception_type": exc.__class__.__name__,
                },
            )
        if isinstance(exc, DelegationUsageBudgetError):
            return RuntimeExecutionError(
                exc.error_code,
                "Agent delegation usage budget could not be satisfied.",
                source=ErrorSource.AGENT,
                details={
                    "budget_field": exc.budget_field,
                    "reason": exc.reason,
                    "exception_type": exc.__class__.__name__,
                },
            )
        if isinstance(exc, DelegationBudgetError):
            return RuntimeExecutionError(
                "plan.step_budget_exceeded",
                "Agent delegation budget was exceeded.",
                source=ErrorSource.AGENT,
                details={"exception_type": exc.__class__.__name__},
            )
        if isinstance(exc, AgentAdapterError):
            return RuntimeExecutionError(
                "agent.adapter_contract_failed",
                "Agent adapter contract validation failed.",
                source=ErrorSource.AGENT,
                details={"exception_type": exc.__class__.__name__},
            )
        return RuntimeExecutionError(
            "runtime.executor_exception",
            "Runtime execution failed.",
            source=ErrorSource.AGENT,
            retriable=bool(getattr(exc, "retriable", False)),
            details={"exception_type": exc.__class__.__name__},
        )

    def _build_control_result(
        self,
        context: RunContext,
        events: list[AgentEvent],
        runtime_error: RuntimeExecutionError,
        raw_result: dict[str, Any] | None = None,
    ) -> RunResult:
        status = (
            RunStatus.CANCELLED
            if runtime_error.source == ErrorSource.CANCELLATION
            else RunStatus.FAILED
        )
        event_type = "run.cancelled"
        if status != RunStatus.CANCELLED:
            event_type = (
                "run.timed_out"
                if runtime_error.source == ErrorSource.TIMEOUT
                else "run.failed"
            )
        tool_call_records = self._tool_call_records_from_context(context)
        for record in tool_call_records:
            self._append_tool_call_event(events, context.trace_id, record)

        error = RunError(
            code=runtime_error.code,
            message=runtime_error.message,
            source=runtime_error.source,
            retriable=runtime_error.retriable,
            event_sequence=len(events) + 1,
            details=runtime_error.details,
        )
        events.append(
            self._build_event(
                sequence=len(events) + 1,
                event_type=event_type,
                visibility=EventVisibility.CLIENT,
                trace_id=context.trace_id,
                payload={"error_code": error.code},
            )
        )
        usage = self._delegated_usage(raw_result or {})
        if raw_result is not None:
            debug = raw_result.get("debug")
            agent_steps = (
                debug.get("agent_steps", []) if isinstance(debug, dict) else []
            )
            if isinstance(agent_steps, list):
                usage.step_count = max(usage.step_count, len(agent_steps))
        usage.tool_call_count = max(
            usage.tool_call_count,
            len(tool_call_records),
        )
        return RunResult(
            run_id=context.run_id,
            runtime_thread_id=context.runtime_thread_id,
            trace_id=context.trace_id,
            request_id=context.request.request_id,
            user_id=context.user_id,
            client_thread_id=context.client_thread_id,
            status=status,
            tool_calls=[record.tool_name for record in tool_call_records],
            tool_call_records=tool_call_records,
            events=events,
            usage=usage,
            error=error,
            metadata={
                "legacy_bridge": True,
                "control_terminated": True,
                **self._context_metadata(context),
            },
        )

    def _build_success_result(
        self,
        context: RunContext,
        events: list[AgentEvent],
        raw_result: dict[str, Any],
    ) -> RunResult:
        debug = raw_result.get("debug") if isinstance(raw_result.get("debug"), dict) else None
        status = _status_from_legacy(raw_result.get("status"))
        tool_calls = [str(tool_name) for tool_name in raw_result.get("tool_calls", [])]
        agent_steps = []
        if debug is not None and isinstance(debug.get("agent_steps"), list):
            agent_steps = [step for step in debug["agent_steps"] if isinstance(step, dict)]

        next_sequence = len(events) + 1
        for step in agent_steps:
            events.append(
                self._build_event(
                    sequence=next_sequence,
                    event_type="agent.step",
                    agent_name=step.get("node"),
                    visibility=EventVisibility.INTERNAL,
                    trace_id=context.trace_id,
                    payload=step,
                )
            )
            next_sequence += 1

        if status == RunStatus.CONFIRMATION_REQUIRED:
            events.append(
                self._build_event(
                    sequence=next_sequence,
                    event_type="action.required",
                    visibility=EventVisibility.CLIENT,
                    trace_id=context.trace_id,
                    payload={"pending_action_id": raw_result.get("pending_action_id")},
                )
            )
            next_sequence += 1

        tool_status = (
            ToolCallStatus.FAILED if status == RunStatus.FAILED else ToolCallStatus.COMPLETED
        )
        tool_call_records = self._tool_call_records_from_result(
            raw_result,
            tool_calls=tool_calls,
            status=tool_status,
        )
        for record in tool_call_records:
            self._append_tool_call_event(events, context.trace_id, record)

        final_event_type = {
            RunStatus.CANCELLED: "run.cancelled",
            RunStatus.FAILED: "run.failed",
        }.get(status, "run.completed")
        events.append(
            self._build_event(
                sequence=len(events) + 1,
                event_type=final_event_type,
                visibility=EventVisibility.CLIENT,
                trace_id=context.trace_id,
                payload={"status": status},
            )
        )
        output_data = {
            key: value
            for key, value in raw_result.items()
            if key
            not in {
                "answer",
                "status",
                "tool_calls",
                "tool_call_records",
                "pending_action_id",
                "debug",
                "delegated_usage",
                "raw_result",
                "recommendation_diagnostics",
                "catalog_candidates",
                "structured_constraints",
                "recommendation_result",
                "top_k_product_evidence",
                "policy_evidence",
            }
        }
        error = None
        public_failure = None
        if status == RunStatus.FAILED:
            public_failure = public_error_for_result(
                status=status,
                code=raw_result.get("runtime_error_code") or "runtime.failed_result",
                retry_state=str(raw_result.get("retry_state") or "terminal"),
                authoritative_run_id=raw_result.get("authoritative_run_id"),
            )
            error = RunError(
                code=public_failure.code,
                message=public_failure.message,
                source=ErrorSource.AGENT,
                retriable=False,
                event_sequence=events[-1].sequence,
            )

        usage = self._delegated_usage(raw_result)
        usage.tool_call_count = max(usage.tool_call_count, len(tool_call_records))
        usage.step_count = max(usage.step_count, len(agent_steps))
        return RunResult(
            run_id=context.run_id,
            runtime_thread_id=context.runtime_thread_id,
            trace_id=context.trace_id,
            request_id=context.request.request_id,
            user_id=context.user_id,
            client_thread_id=context.client_thread_id,
            status=status,
            answer=(
                public_failure.message
                if public_failure is not None
                else str(raw_result.get("answer", ""))
            ),
            output_data=output_data,
            tool_calls=tool_calls,
            tool_call_records=tool_call_records,
            pending_action_id=raw_result.get("pending_action_id"),
            events=events,
            usage=usage,
            error=error,
            debug=debug,
            metadata={
                "legacy_bridge": True,
                **self._context_metadata(context),
                **(
                    {
                        "runtime_error_code": public_failure.code,
                        "retry_state": public_failure.retry_state,
                        "authoritative_run_id": public_failure.authoritative_run_id,
                    }
                    if public_failure is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _tool_call_records_from_result(
        raw_result: dict[str, Any],
        *,
        tool_calls: list[str],
        status: ToolCallStatus,
    ) -> list[ToolCallRecord]:
        raw_records = raw_result.get("tool_call_records")
        if isinstance(raw_records, list):
            records: list[ToolCallRecord] = []
            for raw_record in raw_records:
                try:
                    records.append(ToolCallRecord.model_validate(raw_record))
                except Exception:
                    records = []
                    break
            if records:
                return records

        return [
            ToolCallRecord(
                tool_name=tool_name,
                caller="legacy_v3_bridge",
                capability=tool_name,
                status=status,
                side_effect_class=_tool_side_effect_class(tool_name),
            )
            for tool_name in tool_calls
        ]

    @staticmethod
    def _tool_call_records_from_context(context: RunContext) -> list[ToolCallRecord]:
        raw_records = context.metadata_snapshot().get("tool_call_records", [])
        if not isinstance(raw_records, list):
            return []
        records: list[ToolCallRecord] = []
        for raw_record in raw_records:
            try:
                records.append(ToolCallRecord.model_validate(raw_record))
            except Exception:
                continue
        return records

    def _append_tool_call_event(
        self,
        events: list[AgentEvent],
        trace_id: str,
        record: ToolCallRecord,
    ) -> None:
        event_type = {
            ToolCallStatus.FAILED: "tool.call.failed",
            ToolCallStatus.SKIPPED: "tool.call.skipped",
        }.get(record.status, "tool.call.completed")
        events.append(
            self._build_event(
                sequence=len(events) + 1,
                event_type=event_type,
                visibility=EventVisibility.AUDIT,
                trace_id=trace_id,
                agent_name=record.caller,
                tool_call_id=record.tool_call_id,
                payload={
                    "tool_name": record.tool_name,
                    "capability": record.capability,
                    "status": record.status,
                    "side_effect_class": record.side_effect_class,
                    "requires_confirmation": record.requires_confirmation,
                    "resource_policy": record.resource_policy.model_dump(mode="json"),
                    "argument_hash": record.argument_hash,
                    "duration_ms": record.duration_ms,
                },
            )
        )

    def _build_exception_result(
        self,
        context: RunContext,
        events: list[AgentEvent],
        exc: Exception,
        *,
        runtime_error: RuntimeExecutionError | None = None,
        usage: RunUsage | None = None,
    ) -> RunResult:
        runtime_error = runtime_error or self._as_runtime_error(exc)
        tool_call_record = self._tool_call_record_from_exception(exc)
        if tool_call_record is not None:
            events.append(
                self._build_event(
                    sequence=len(events) + 1,
                    event_type="tool.call.failed",
                    visibility=EventVisibility.AUDIT,
                    trace_id=context.trace_id,
                    agent_name=tool_call_record.caller,
                    tool_call_id=tool_call_record.tool_call_id,
                    payload={
                        "tool_name": tool_call_record.tool_name,
                        "capability": tool_call_record.capability,
                        "status": tool_call_record.status,
                        "side_effect_class": tool_call_record.side_effect_class,
                        "requires_confirmation": tool_call_record.requires_confirmation,
                        "resource_policy": tool_call_record.resource_policy.model_dump(
                            mode="json"
                        ),
                        "argument_hash": tool_call_record.argument_hash,
                        "duration_ms": tool_call_record.duration_ms,
                    },
                )
            )
        error = RunError(
            code=runtime_error.code,
            message=runtime_error.message,
            source=runtime_error.source,
            retriable=runtime_error.retriable,
            event_sequence=len(events) + 1,
            details=runtime_error.details,
        )
        status = (
            RunStatus.CANCELLED
            if runtime_error.source == ErrorSource.CANCELLATION
            else RunStatus.FAILED
        )
        event_type = "run.cancelled"
        if status != RunStatus.CANCELLED:
            event_type = (
                "run.timed_out"
                if runtime_error.source == ErrorSource.TIMEOUT
                else "run.failed"
            )
        events.append(
            self._build_event(
                sequence=len(events) + 1,
                event_type=event_type,
                visibility=EventVisibility.CLIENT,
                trace_id=context.trace_id,
                payload={"error_code": error.code},
            )
        )
        failure_usage = usage or runtime_error.usage or RunUsage()
        if tool_call_record is not None and failure_usage.tool_call_count < 1:
            failure_usage = failure_usage.model_copy(
                update={"tool_call_count": 1}
            )
        return RunResult(
            run_id=context.run_id,
            runtime_thread_id=context.runtime_thread_id,
            trace_id=context.trace_id,
            request_id=context.request.request_id,
            user_id=context.user_id,
            client_thread_id=context.client_thread_id,
            status=status,
            answer="",
            tool_calls=(
                [tool_call_record.tool_name] if tool_call_record is not None else []
            ),
            tool_call_records=(
                [tool_call_record] if tool_call_record is not None else []
            ),
            events=events,
            usage=failure_usage,
            error=error,
            metadata={"legacy_bridge": True, **self._context_metadata(context)},
        )

    @staticmethod
    def _tool_call_record_from_exception(exc: Exception) -> ToolCallRecord | None:
        raw_record = getattr(exc, "tool_call_record", None)
        if isinstance(raw_record, ToolCallRecord):
            return raw_record
        if raw_record is None:
            return None
        try:
            return ToolCallRecord.model_validate(raw_record)
        except Exception:
            return None

    @staticmethod
    def _context_metadata(context: RunContext) -> dict[str, Any]:
        context_slice = context.context_slice
        if context_slice is None:
            return {"context_item_count": 0}
        return {
            "context_item_count": len(context_slice.items),
            "context_estimated_tokens": context_slice.estimated_tokens,
            "context_omitted_count": context_slice.omitted_count,
        }

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _build_event(
        self,
        *,
        sequence: int,
        event_type: str,
        visibility: EventVisibility,
        trace_id: str,
        payload: dict[str, Any],
        agent_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> AgentEvent:
        return AgentEvent(
            sequence=sequence,
            event_type=event_type,
            agent_name=agent_name,
            trace_id=trace_id,
            visibility=visibility,
            payload=payload,
            tool_call_id=tool_call_id,
        )

    def _claim_record_result(
        self,
        context: RunContext,
        session: Session,
        record: dict[str, Any],
    ) -> RunResult:
        if record["request_hash"] != self._request_hash(context.request):
            return self._idempotency_error_result(
                context,
                code="runtime.idempotency_key_conflict",
                message="Idempotency key was already used for a different request.",
                retriable=False,
                authoritative_run_id=record.get("run_id"),
            )
        if record["status"] == RunStatus.STARTED:
            return self._idempotency_error_result(
                context,
                code="runtime.idempotency_in_progress",
                message="An equivalent request is already in progress.",
                retriable=True,
                retry_state="in_progress",
                authoritative_run_id=record.get("run_id"),
            )
        try:
            status = RunStatus(record["status"])
        except ValueError:
            status = None
        if status in TERMINAL_IDEMPOTENCY_STATUSES and record.get("run_id"):
            run = get_agent_run(session, run_id=record["run_id"])
            if run is not None:
                return self._run_result_from_persisted_run(run)
        return self._idempotency_error_result(
            context,
            code="runtime.idempotency_result_unavailable",
            message="The stored idempotency result is unavailable.",
            retriable=True,
            retry_state="in_progress" if record.get("run_id") else "terminal",
            authoritative_run_id=record.get("run_id"),
        )

    def _persist_start(
        self, context: RunContext, started_event: AgentEvent
    ) -> RunResult | None:
        with self._open_session() as session:
            if session is None:
                return None
            key = context.request.idempotency_key
            try:
                if key:
                    if not context.user_id:
                        return self._idempotency_error_result(
                            context,
                            code="runtime.idempotency_owner_unavailable",
                            message="A stable owner scope is required for Chat retry recovery.",
                            retriable=False,
                        )
                    claim = claim_idempotency_record(
                        session,
                        user_id=context.user_id,
                        operation=context.request.operation,
                        idempotency_key=key,
                        request_hash=self._request_hash(context.request),
                        run_id=context.run_id,
                        now=context.started_at,
                        expires_at=context.started_at
                        + timedelta(days=DEFAULT_IDEMPOTENCY_RETENTION_DAYS),
                        metadata={"request_id": context.request.request_id},
                    )
                    if not claim.claimed:
                        return self._claim_record_result(
                            context, session, claim.record
                        )

                thread_expires_at = context.started_at + timedelta(
                    days=DEFAULT_THREAD_RETENTION_DAYS
                )
                run_expires_at = context.started_at + timedelta(
                    days=DEFAULT_RUN_RETENTION_DAYS
                )
                thread = get_or_create_conversation_thread(
                    session,
                    user_id=context.user_id,
                    client_thread_id=context.client_thread_id,
                    runtime_thread_id=context.runtime_thread_id,
                    metadata={
                        "latest_operation": context.request.operation,
                        "runtime_schema_version": "v4.3",
                    },
                    now=context.started_at,
                    expires_at=thread_expires_at,
                )
                context.runtime_thread_id = thread["thread_id"]
                create_agent_run(
                    session,
                    run_id=context.run_id,
                    thread_id=context.runtime_thread_id,
                    user_id=context.user_id,
                    parent_run_id=context.parent_run_id,
                    operation=context.request.operation,
                    mode=context.request.mode,
                    status=RunStatus.STARTED,
                    request_id=context.request.request_id,
                    trace_id=context.trace_id,
                    idempotency_key=key,
                    input_text=context.request.input_text,
                    request_json=context.request.model_dump(mode="json"),
                    started_at=context.started_at,
                    expires_at=run_expires_at,
                    metadata=context.metadata_snapshot(),
                )
                append_agent_run_event(
                    session,
                    run_id=context.run_id,
                    thread_id=context.runtime_thread_id,
                    user_id=context.user_id,
                    sequence=started_event.sequence,
                    event_type=started_event.event_type,
                    agent_name=started_event.agent_name,
                    visibility=started_event.visibility,
                    payload_json=started_event.payload,
                    trace_id=context.trace_id,
                    tool_call_id=started_event.tool_call_id,
                    created_at=started_event.timestamp,
                )
                if context.request.input_text is not None:
                    append_conversation_message(
                        session,
                        thread_id=context.runtime_thread_id,
                        user_id=context.user_id,
                        run_id=context.run_id,
                        role="user",
                        content_text=context.request.input_text,
                        content_json=context.request.input_data,
                        now=context.started_at,
                        expires_at=thread_expires_at,
                    )
                if key:
                    save_idempotency_record(
                        session,
                        user_id=context.user_id,
                        thread_id=context.runtime_thread_id,
                        run_id=context.run_id,
                        operation=context.request.operation,
                        idempotency_key=key,
                        request_hash=self._request_hash(context.request),
                        status=RunStatus.STARTED,
                        metadata={"request_id": context.request.request_id},
                        now=context.started_at,
                        expires_at=context.started_at
                        + timedelta(days=DEFAULT_IDEMPOTENCY_RETENTION_DAYS),
                    )
                session.commit()
                return None
            except RuntimeIdempotencyPersistenceError as exc:
                session.rollback()
                if key:
                    return self._idempotency_error_result(
                        context,
                        code="runtime.idempotency_persistence_failed",
                        message="Chat retry identity could not be established safely.",
                        retriable=True,
                        retry_state="in_progress",
                        details={"exception_type": type(exc).__name__},
                    )
                raise
            except Exception as exc:
                session.rollback()
                if key:
                    return self._idempotency_error_result(
                        context,
                        code="runtime.idempotency_persistence_failed",
                        message="Chat retry identity could not be persisted safely.",
                        retriable=True,
                        retry_state="in_progress",
                        details={"exception_type": type(exc).__name__},
                    )

    def _persist_finish(self, context: RunContext, result: RunResult) -> None:
        with self._open_session() as session:
            if session is None:
                return
            try:
                thread_expires_at = context.started_at + timedelta(
                    days=DEFAULT_THREAD_RETENTION_DAYS
                )
                idempotency_expires_at = context.started_at + timedelta(
                    days=DEFAULT_IDEMPOTENCY_RETENTION_DAYS
                )
                for event in result.events[1:]:
                    append_agent_run_event(
                        session,
                        run_id=result.run_id,
                        thread_id=result.runtime_thread_id,
                        user_id=result.user_id,
                        sequence=event.sequence,
                        event_type=event.event_type,
                        agent_name=event.agent_name,
                        visibility=event.visibility,
                        payload_json=event.payload,
                        trace_id=result.trace_id,
                        tool_call_id=event.tool_call_id,
                        created_at=event.timestamp,
                    )
                if result.answer:
                    append_conversation_message(
                        session,
                        thread_id=result.runtime_thread_id,
                        user_id=result.user_id,
                        run_id=result.run_id,
                        role="assistant",
                        content_text=result.answer,
                        content_json=result.output_data,
                        now=result.completed_at,
                        expires_at=thread_expires_at,
                    )
                finalize_agent_run(
                    session,
                    run_id=result.run_id,
                    status=result.status,
                    completed_at=result.completed_at,
                    output_text=result.answer,
                    result_json=result.output_data,
                    error_json=(
                        None if result.error is None else result.error.model_dump(mode="json")
                    ),
                    usage_json=result.usage.model_dump(mode="json"),
                    debug_json=result.debug,
                    pending_action_id=result.pending_action_id,
                    tool_call_records_json=[
                        record.model_dump(mode="json") for record in result.tool_call_records
                    ],
                    metadata=result.metadata,
                )
                if context.request.idempotency_key:
                    save_idempotency_record(
                        session,
                        user_id=result.user_id,
                        thread_id=result.runtime_thread_id,
                        run_id=result.run_id,
                        operation=context.request.operation,
                        idempotency_key=context.request.idempotency_key,
                        request_hash=self._request_hash(context.request),
                        status=result.status,
                        response_fingerprint=self._response_fingerprint(result),
                        metadata={"request_id": result.request_id},
                        now=result.completed_at,
                        expires_at=idempotency_expires_at,
                    )
                session.commit()
            except Exception as exc:
                session.rollback()
                if context.request.idempotency_key:
                    raise RuntimeIdempotencyPersistenceError(
                        "Runtime idempotency result could not be persisted safely."
                    ) from exc
        if context.request.metadata.get("governance_audit_enabled") is True:
            try:
                from app.governance import project_runtime_governance_records

                records = project_runtime_governance_records(context, result)
                self._governance_audit_emitter.emit_many(records)
            except Exception:
                # Governance persistence is independent and cannot rewrite an
                # already-computed business/runtime result.
                pass

    def _persist_or_fail_closed(self, context: RunContext, result: RunResult) -> RunResult:
        try:
            self._persist_finish(context, result)
        except RuntimeIdempotencyPersistenceError as exc:
            return self._idempotency_error_result(
                context,
                code="runtime.idempotency_persistence_failed",
                message="Chat retry result could not be persisted safely.",
                retriable=True,
                retry_state="in_progress",
                authoritative_run_id=result.run_id,
                details={"exception_type": type(exc).__name__},
            )
        return result

    def _request_hash(self, request: RunRequest) -> str:
        payload = request.model_dump(
            mode="json",
            exclude={"request_id", "requested_at"},
            exclude_none=True,
        )
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _response_fingerprint(self, result: RunResult) -> str:
        payload = {
            "status": result.status,
            "answer": result.answer,
            "pending_action_id": result.pending_action_id,
            "tool_calls": result.tool_calls,
            "recommendation": result.output_data.get("recommendation"),
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _validate_public_output(raw_result: dict[str, Any]) -> None:
        """Reject a malformed recommendation before the run is completed/persisted."""

        recommendation = raw_result.get("recommendation")
        if recommendation is None:
            return
        try:
            from app.schemas.recommendation import RecommendationResult

            RecommendationResult.model_validate(recommendation)
        except Exception as exc:
            raise RuntimeExecutionError(
                "recommendation.validation_failed",
                "Recommendation result did not satisfy the public contract.",
                source=ErrorSource.AGENT,
                details={"validation_error": exc.__class__.__name__},
            ) from exc

    @contextmanager
    def _open_session(self) -> Iterator[Session | None]:
        if self._session_factory is None:
            yield None
            return

        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()
