"""Deterministic fault-injection and process-restart trajectory evaluation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from agents.shopmind_multi_agent.planning import ValidatedProviderPlanner
from app.db.base import Base
from app.db.models import PendingAction, UserPreference
from app.repositories.cart import (
    confirm_save_preference,
    prepare_save_preference,
    resolve_pending_action,
)
from app.runtime import (
    AgentExecutionPlan,
    AgentPlanStep,
    AgentResult,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTaskStatus,
    AgentTransportError,
    AgentTransportFailureCode,
    BoundedPlanExecutor,
    PersistedRunTrajectory,
    RunOperation,
    RunRequest,
    RunResult,
    RunUsage,
    RuntimeTrajectoryRecorder,
    RuntimeTrajectoryReplayer,
    ShopMindRuntimeHarness,
    ToolCapability,
    ToolGateway,
    ToolSideEffectClass,
)


PRIVATE_MARKER = "private-fault-detail-must-not-be-recorded"


class FaultSurface(StrEnum):
    PROVIDER = "provider"
    TOOL = "tool"
    TRANSPORT = "transport"
    CONTROL = "control"
    IDEMPOTENCY = "idempotency"
    ACTION = "action"


class ResilienceScenario(BaseModel):
    """Closed server-owned fault scenario contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    fault_surface: FaultSurface
    expected_status: str
    expected_events: tuple[str, ...]
    expected_invocations: int = Field(ge=0)


RESILIENCE_SCENARIOS: tuple[ResilienceScenario, ...] = (
    ResilienceScenario(
        scenario_id="provider_fallback",
        fault_surface=FaultSurface.PROVIDER,
        expected_status="completed",
        expected_events=("provider.fallback",),
        expected_invocations=1,
    ),
    ResilienceScenario(
        scenario_id="tool_failure",
        fault_surface=FaultSurface.TOOL,
        expected_status="failed",
        expected_events=("tool.call.failed", "run.failed"),
        expected_invocations=1,
    ),
    ResilienceScenario(
        scenario_id="transport_retry_success",
        fault_surface=FaultSurface.TRANSPORT,
        expected_status="completed",
        expected_events=(
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.retry.scheduled",
            "plan.step.retry.started",
            "plan.step.attempt.started",
            "plan.step.attempt.completed",
            "plan.step.retry.succeeded",
        ),
        expected_invocations=2,
    ),
    ResilienceScenario(
        scenario_id="transport_retry_cancelled",
        fault_surface=FaultSurface.CONTROL,
        expected_status="cancelled",
        expected_events=(
            "plan.step.attempt.started",
            "plan.step.attempt.failed",
            "plan.step.retry.scheduled",
            "plan.step.retry.cancelled",
        ),
        expected_invocations=1,
    ),
    ResilienceScenario(
        scenario_id="idempotency_restart_replay",
        fault_surface=FaultSurface.IDEMPOTENCY,
        expected_status="completed",
        expected_events=("run.started", "run.completed"),
        expected_invocations=1,
    ),
    ResilienceScenario(
        scenario_id="action_restart_resume",
        fault_surface=FaultSurface.ACTION,
        expected_status="completed",
        expected_events=("action.resumed", "action.confirmed"),
        expected_invocations=1,
    ),
)


class _ToolArguments(BaseModel):
    query: str = Field(min_length=1)


class _FailingTool:
    name = "get_fault_probe"
    args_schema = _ToolArguments

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, arguments: dict[str, str]) -> str:
        del arguments
        self.calls += 1
        raise RuntimeError(PRIVATE_MARKER)


@dataclass
class _Stores:
    writer_factory: Callable[[], Session]
    reader_factory: Callable[[], Session]
    writer_engine: Any
    reader_engine: Any

    def close(self) -> None:
        self.writer_engine.dispose()
        self.reader_engine.dispose()


@dataclass
class _Observation:
    result: RunResult
    recorded: PersistedRunTrajectory
    replay_matches: bool
    replay_fingerprints_match: bool
    invocations: int
    specific_invariant: bool


def _make_stores() -> _Stores:
    database_name = f"shopmind-resilience-{uuid4()}"
    database_url = (
        f"sqlite+pysqlite:///file:{database_name}"
        "?mode=memory&cache=shared&uri=true"
    )
    writer_engine = create_engine(database_url)
    Base.metadata.create_all(writer_engine)
    reader_engine = create_engine(database_url)
    return _Stores(
        writer_factory=sessionmaker(bind=writer_engine, expire_on_commit=False),
        reader_factory=sessionmaker(bind=reader_engine, expire_on_commit=False),
        writer_engine=writer_engine,
        reader_engine=reader_engine,
    )


def _observe(
    stores: _Stores,
    result: RunResult,
    *,
    invocations: int,
    specific_invariant: bool,
) -> _Observation:
    recorded = RuntimeTrajectoryRecorder(stores.writer_factory).record(
        run_id=result.run_id,
        user_id=result.user_id,
        runtime_thread_id=result.runtime_thread_id,
    )
    wire_snapshot = recorded.model_dump_json()
    reloaded = PersistedRunTrajectory.model_validate_json(wire_snapshot)
    replay = RuntimeTrajectoryReplayer(stores.reader_factory).replay(reloaded)
    return _Observation(
        result=result,
        recorded=recorded,
        replay_matches=replay.matches,
        replay_fingerprints_match=(
            replay.recorded_fingerprint == replay.observed_fingerprint
        ),
        invocations=invocations,
        specific_invariant=specific_invariant,
    )


def _request(scenario_id: str, *, idempotency_key: str | None = None) -> RunRequest:
    return RunRequest(
        operation=RunOperation.CHAT,
        user_id="resilience-user",
        thread_id=f"resilience-{scenario_id}",
        input_text=PRIVATE_MARKER,
        idempotency_key=idempotency_key,
    )


def _provider_fallback(stores: _Stores) -> _Observation:
    calls = 0
    fallback_reason: str | None = None

    def provider(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        del payload
        calls += 1
        raise RuntimeError(PRIVATE_MARKER)

    planner = ValidatedProviderPlanner(provider, provider_type="fault_injection")

    def executor(context) -> dict[str, Any]:
        nonlocal fallback_reason
        plan = planner.build_plan(
            ["rag_agent"], message=PRIVATE_MARKER, run_id=context.run_id
        )
        fallback_reason = plan.metadata.get("planner_fallback_reason")
        context.emit_event(
            "provider.fallback",
            agent_name="supervisor",
            payload={"reason": fallback_reason, "private_detail": PRIVATE_MARKER},
        )
        return {
            "answer": "deterministic fallback",
            "status": "completed",
            "output_data": {"planner_type": plan.planner_type},
        }

    result = ShopMindRuntimeHarness(stores.writer_factory).run(
        _request("provider_fallback"), executor
    )
    return _observe(
        stores,
        result,
        invocations=calls,
        specific_invariant=(
            fallback_reason == "provider_error_or_invalid_contract"
        ),
    )


def _tool_failure(stores: _Stores) -> _Observation:
    tool = _FailingTool()
    gateway = ToolGateway(
        (
            ToolCapability(
                name=tool.name,
                allowed_agents=frozenset({"preference_agent"}),
                side_effect_class=ToolSideEffectClass.READ,
            ),
        )
    )

    def executor(context) -> dict[str, Any]:
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments={"query": PRIVATE_MARKER},
            context=context,
        )
        raise AssertionError("unreachable")

    result = ShopMindRuntimeHarness(stores.writer_factory).run(
        _request("tool_failure"), executor, raise_on_error=False
    )
    return _observe(
        stores,
        result,
        invocations=tool.calls,
        specific_invariant=(
            result.error is not None
            and result.error.code == "tool.execution_failed"
            and len(result.tool_call_records) == 1
        ),
    )


def _retry_observation(stores: _Stores, *, cancel_before_retry: bool) -> _Observation:
    calls = 0
    policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )

    def executor(context) -> dict[str, Any]:
        nonlocal calls
        step = AgentPlanStep(
            step_id="rag-step",
            recipient="rag_agent",
            intent="document_retrieval",
            retry_policy=policy,
        )

        def handler(current_step: AgentPlanStep) -> AgentResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise AgentTransportError(
                    AgentTransportFailureCode.UNAVAILABLE,
                    retriable=True,
                    usage=RunUsage(total_tokens=2, step_count=1),
                )
            return AgentResult(
                task_id=current_step.step_id,
                status=AgentTaskStatus.COMPLETED,
                usage=RunUsage(total_tokens=3, step_count=1),
            )

        def observe_attempt(event) -> None:
            context.emit_event(
                f"plan.step.{event.lifecycle}",
                agent_name=event.recipient,
                payload=event.model_dump(mode="json"),
            )

        plan_result = BoundedPlanExecutor().execute(
            AgentExecutionPlan(run_id=context.run_id, steps=[step]),
            handler,
            cancellation_check=(lambda: calls >= 1) if cancel_before_retry else None,
            attempt_observer=observe_attempt,
        )
        return {
            "answer": "",
            "status": "cancelled" if cancel_before_retry else "completed",
            "delegated_usage": [plan_result.usage.model_dump(mode="json")],
            "output_data": {"plan_status": plan_result.status},
        }

    scenario_id = (
        "transport_retry_cancelled" if cancel_before_retry else "transport_retry_success"
    )
    result = ShopMindRuntimeHarness(stores.writer_factory).run(
        _request(scenario_id), executor
    )
    return _observe(
        stores,
        result,
        invocations=calls,
        specific_invariant=(
            (calls == 1 and result.status == "cancelled")
            if cancel_before_retry
            else (calls == 2 and result.usage.step_count == 2)
        ),
    )


def _idempotency_restart(stores: _Stores) -> _Observation:
    calls = 0
    request = _request(
        "idempotency_restart_replay", idempotency_key="resilience-restart-key"
    )

    def first_executor(context) -> dict[str, Any]:
        nonlocal calls
        del context
        calls += 1
        return {"answer": "stable", "status": "completed"}

    first = ShopMindRuntimeHarness(stores.writer_factory).run(request, first_executor)

    def forbidden_executor(context) -> dict[str, Any]:
        nonlocal calls
        del context
        calls += 1
        raise AssertionError("idempotency replay executed the handler")

    replayed = ShopMindRuntimeHarness(stores.reader_factory).run(
        request, forbidden_executor
    )
    return _observe(
        stores,
        first,
        invocations=calls,
        specific_invariant=(
            replayed.metadata.get("idempotency_replayed") is True
            and replayed.run_id == first.run_id
        ),
    )


def _action_restart(stores: _Stores) -> _Observation:
    session = stores.writer_factory()
    try:
        prepared = prepare_save_preference(
            session,
            user_id="resilience-user",
            preference_type="style",
            preference_value=PRIVATE_MARKER,
            thread_id="resilience-action-thread",
        )
        action_id = prepared["pending_action_id"]
        session.commit()
    finally:
        session.close()
    calls = 0

    def executor(context) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        operation_session = stores.reader_factory()
        try:
            resolved = resolve_pending_action(
                operation_session,
                action_id,
                "resilience-user",
                "resilience-action-thread",
            )
            if resolved["status"] == "resolved":
                context.emit_event(
                    "action.resumed",
                    payload={"action_id": action_id, "action_type": "save_preference"},
                )
            confirmed = confirm_save_preference(
                operation_session,
                action_id,
                "resilience-user",
                "resilience-action-thread",
            )
            operation_session.commit()
        finally:
            operation_session.close()
        if confirmed["status"] == "confirmed":
            context.emit_event(
                "action.confirmed",
                payload={"action_id": action_id, "action_type": "save_preference"},
            )
        return {
            "answer": "confirmed",
            "status": "completed",
            "pending_action_id": action_id,
        }

    request = RunRequest(
        operation=RunOperation.CONFIRM_PENDING_ACTION,
        user_id="resilience-user",
        thread_id="resilience-action-thread",
        input_data={"pending_action_id": action_id, "confirmed": True},
    )
    result = ShopMindRuntimeHarness(stores.reader_factory).run(request, executor)
    session = stores.reader_factory()
    try:
        action_status = session.get(PendingAction, action_id).status
        preferences = session.scalars(
            select(UserPreference).where(UserPreference.user_id == "resilience-user")
        ).all()
    finally:
        session.close()
    return _observe(
        stores,
        result,
        invocations=calls,
        specific_invariant=(
            action_status == "confirmed"
            and len(preferences) == 1
            and result.pending_action_id == action_id
        ),
    )


SCENARIO_RUNNERS: dict[str, Callable[[_Stores], _Observation]] = {
    "provider_fallback": _provider_fallback,
    "tool_failure": _tool_failure,
    "transport_retry_success": lambda stores: _retry_observation(
        stores, cancel_before_retry=False
    ),
    "transport_retry_cancelled": lambda stores: _retry_observation(
        stores, cancel_before_retry=True
    ),
    "idempotency_restart_replay": _idempotency_restart,
    "action_restart_resume": _action_restart,
}


def replay_resilience_scenario(scenario: ResilienceScenario) -> dict[str, Any]:
    stores = _make_stores()
    try:
        observation = SCENARIO_RUNNERS[scenario.scenario_id](stores)
        event_types = tuple(event.event_type for event in observation.recorded.events)
        expected_cursor = 0
        for event_type in event_types:
            if (
                expected_cursor < len(scenario.expected_events)
                and event_type == scenario.expected_events[expected_cursor]
            ):
                expected_cursor += 1
        serialized = observation.recorded.model_dump_json()
        checks = {
            "status": observation.result.status == scenario.expected_status,
            "event_subsequence": expected_cursor == len(scenario.expected_events),
            "event_sequence": [event.sequence for event in observation.recorded.events]
            == list(range(1, observation.recorded.event_count + 1)),
            "terminal_event": event_types[-1]
            in {"run.completed", "run.cancelled", "run.failed", "run.timed_out"},
            "replay_matches": observation.replay_matches,
            "replay_fingerprints": observation.replay_fingerprints_match,
            "run_identity": observation.recorded.run_id == observation.result.run_id,
            "thread_identity": observation.recorded.runtime_thread_id
            == observation.result.runtime_thread_id,
            "trace_identity": observation.recorded.trace_id
            == observation.result.trace_id,
            "private_marker_sanitized": PRIVATE_MARKER not in serialized,
            "invocation_count": observation.invocations
            == scenario.expected_invocations,
            "scenario_invariant": observation.specific_invariant,
        }
        failures = [check_id for check_id, passed in checks.items() if not passed]
        return {
            "scenario_id": scenario.scenario_id,
            "fault_surface": scenario.fault_surface,
            "passed": not failures,
            "checks_passed": sum(checks.values()),
            "total_checks": len(checks),
            "failures": failures,
            "outcome": {
                "status": observation.result.status,
                "event_types": event_types,
                "invocations": observation.invocations,
                "replay_matches": observation.replay_matches,
            },
        }
    finally:
        stores.close()


def evaluate_resilience_replay(
    scenarios: Sequence[ResilienceScenario] = RESILIENCE_SCENARIOS,
) -> dict[str, Any]:
    results = [replay_resilience_scenario(scenario) for scenario in scenarios]
    failures = [
        {
            "scenario_id": result["scenario_id"],
            "fault_surface": result["fault_surface"],
            "failed_checks": result["failures"],
        }
        for result in results
        if not result["passed"]
    ]
    total_checks = sum(result["total_checks"] for result in results)
    passed_checks = sum(result["checks_passed"] for result in results)
    passed_cases = sum(result["passed"] for result in results)
    return {
        "schema_version": "shopmind.resilience-replay-eval.v1",
        "evaluation": "deterministic_resilience_process_restart_replay",
        "total_cases": len(results),
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(results) if results else 1.0,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "check_pass_rate": passed_checks / total_checks if total_checks else 1.0,
        "failures": failures,
        "results": results,
    }


def format_resilience_replay_summary(summary: dict[str, Any]) -> str:
    return "\n".join(
        (
            "# ShopMind V6 Resilience and Restart Replay",
            "",
            f"- cases: {summary['passed_cases']}/{summary['total_cases']}",
            f"- checks: {summary['passed_checks']}/{summary['total_checks']}",
            f"- failures: {len(summary['failures'])}",
        )
    )


__all__ = [
    "FaultSurface",
    "RESILIENCE_SCENARIOS",
    "ResilienceScenario",
    "evaluate_resilience_replay",
    "format_resilience_replay_summary",
    "replay_resilience_scenario",
]
