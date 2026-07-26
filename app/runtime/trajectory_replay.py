"""Normalized, owner-scoped record/replay over persisted runtime trajectories."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.repositories.runtime_runs import get_agent_run, list_agent_run_events

from .contracts import EventVisibility, RunStatus, RunUsage


class TrajectoryReplayError(ValueError):
    """Raised when a persisted trajectory cannot be read safely."""


SAFE_EVENT_PAYLOAD_FIELDS = frozenset(
    {
        "action_id",
        "action_type",
        "attempt",
        "budget_field",
        "budget_reason",
        "capability",
        "error_code",
        "failure_code",
        "lifecycle",
        "max_attempts",
        "max_retries",
        "mode",
        "next_attempt",
        "operation",
        "phase",
        "plan_id",
        "reason",
        "recipient",
        "retriable",
        "side_effect_class",
        "status",
        "step_id",
        "tool_name",
    }
)

TERMINAL_EVENTS: Mapping[RunStatus, frozenset[str]] = {
    RunStatus.COMPLETED: frozenset({"run.completed"}),
    RunStatus.CONFIRMATION_REQUIRED: frozenset({"run.completed"}),
    RunStatus.CANCELLED: frozenset({"run.cancelled"}),
    RunStatus.FAILED: frozenset({"run.failed", "run.timed_out"}),
}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_event_classification(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in sorted(SAFE_EVENT_PAYLOAD_FIELDS.intersection(payload))
        if isinstance(payload[key], (str, int, float, bool)) or payload[key] is None
    }


class RecordedTrajectoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1)
    agent_name: str | None = None
    visibility: EventVisibility
    trace_id: str
    tool_call_id: str | None = None
    classification: dict[str, Any] = Field(default_factory=dict)
    payload_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PersistedRunTrajectory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    schema_version: Literal["shopmind.runtime-trajectory.v1"] = (
        "shopmind.runtime-trajectory.v1"
    )
    run_id: str = Field(min_length=1)
    runtime_thread_id: str = Field(min_length=1)
    user_id: str | None = None
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    status: RunStatus
    idempotency_key: str | None = None
    pending_action_id: str | None = None
    error_code: str | None = None
    error_source: str | None = None
    error_retriable: bool | None = None
    usage: RunUsage = Field(default_factory=RunUsage)
    event_count: int = Field(ge=1)
    events: tuple[RecordedTrajectoryEvent, ...]
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    debug_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_records_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_trajectory(self) -> "PersistedRunTrajectory":
        if self.event_count != len(self.events):
            raise ValueError("Trajectory event count does not match its events.")
        if [event.sequence for event in self.events] != list(
            range(1, self.event_count + 1)
        ):
            raise ValueError("Trajectory events must have a contiguous sequence.")
        if self.events[0].event_type != "run.started":
            raise ValueError("Trajectory must begin with run.started.")
        if any(event.trace_id != self.trace_id for event in self.events):
            raise ValueError("Trajectory event trace identity does not match its run.")
        allowed_terminal_events = TERMINAL_EVENTS.get(RunStatus(self.status))
        if allowed_terminal_events is None:
            raise ValueError("Trajectory requires a terminal run status.")
        if self.events[-1].event_type not in allowed_terminal_events:
            raise ValueError("Trajectory terminal event does not match its run status.")
        if self.error_code is None and (
            self.error_source is not None or self.error_retriable is not None
        ):
            raise ValueError("Trajectory error metadata requires an error code.")
        return self


class TrajectoryReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.runtime-trajectory-replay.v1"] = (
        "shopmind.runtime-trajectory-replay.v1"
    )
    matches: bool
    differences: tuple[str, ...] = ()
    recorded_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed: PersistedRunTrajectory


SessionFactory = Callable[[], Session]


class RuntimeTrajectoryRecorder:
    """Record one terminal persisted run without exposing raw input/output."""

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def record(
        self,
        *,
        run_id: str,
        user_id: str | None,
        runtime_thread_id: str,
    ) -> PersistedRunTrajectory:
        session = self._session_factory()
        try:
            run = get_agent_run(session, run_id=run_id)
            if run is None:
                raise TrajectoryReplayError("Persisted trajectory is unavailable.")
            if run["user_id"] != user_id or run["thread_id"] != runtime_thread_id:
                raise TrajectoryReplayError("Persisted trajectory scope is invalid.")
            if run["status"] == RunStatus.STARTED:
                raise TrajectoryReplayError("Persisted trajectory is not terminal.")
            events = list_agent_run_events(session, run_id=run_id)
        finally:
            session.close()

        recorded_events: list[RecordedTrajectoryEvent] = []
        for event in events:
            if (
                event["run_id"] != run_id
                or event["thread_id"] != runtime_thread_id
                or event["user_id"] != user_id
                or event["trace_id"] != run["trace_id"]
            ):
                raise TrajectoryReplayError(
                    "Persisted trajectory event identity is invalid."
                )
            payload = event["payload_json"]
            try:
                recorded_events.append(
                    RecordedTrajectoryEvent(
                        sequence=event["sequence"],
                        event_type=event["event_type"],
                        agent_name=event["agent_name"],
                        visibility=event["visibility"],
                        trace_id=event["trace_id"],
                        tool_call_id=event["tool_call_id"],
                        classification=_safe_event_classification(payload),
                        payload_fingerprint=_canonical_hash(payload),
                    )
                )
            except Exception as exc:
                raise TrajectoryReplayError(
                    "Persisted trajectory event contract is invalid."
                ) from exc

        error = run.get("error_json") or {}
        try:
            return PersistedRunTrajectory(
                run_id=run["run_id"],
                runtime_thread_id=run["thread_id"],
                user_id=run["user_id"],
                request_id=run["request_id"],
                trace_id=run["trace_id"],
                operation=run["operation"],
                mode=run["mode"],
                status=run["status"],
                idempotency_key=run["idempotency_key"],
                pending_action_id=run["pending_action_id"],
                error_code=error.get("code"),
                error_source=error.get("source"),
                error_retriable=(
                    error.get("retriable")
                    if error.get("code") is not None
                    else None
                ),
                usage=RunUsage.model_validate(run.get("usage_json") or {}),
                event_count=len(recorded_events),
                events=tuple(recorded_events),
                request_fingerprint=_canonical_hash(run.get("request_json") or {}),
                result_fingerprint=_canonical_hash(run.get("result_json") or {}),
                output_fingerprint=_canonical_hash(run.get("output_text")),
                debug_fingerprint=_canonical_hash(run.get("debug_json")),
                tool_records_fingerprint=_canonical_hash(
                    run.get("tool_call_records_json") or []
                ),
            )
        except Exception as exc:
            raise TrajectoryReplayError(
                "Persisted trajectory contract is invalid."
            ) from exc


def trajectory_fingerprint(trajectory: PersistedRunTrajectory) -> str:
    return _canonical_hash(trajectory.model_dump(mode="json"))


class RuntimeTrajectoryReplayer:
    """Reload and compare a recorded trajectory through a fresh store instance."""

    _COMPARISON_FIELDS = (
        "schema_version",
        "run_id",
        "runtime_thread_id",
        "user_id",
        "request_id",
        "trace_id",
        "operation",
        "mode",
        "status",
        "idempotency_key",
        "pending_action_id",
        "error_code",
        "error_source",
        "error_retriable",
        "usage",
        "event_count",
        "events",
        "request_fingerprint",
        "result_fingerprint",
        "output_fingerprint",
        "debug_fingerprint",
        "tool_records_fingerprint",
    )

    def __init__(self, session_factory: SessionFactory):
        self._recorder = RuntimeTrajectoryRecorder(session_factory)

    def replay(self, recorded: PersistedRunTrajectory) -> TrajectoryReplayResult:
        observed = self._recorder.record(
            run_id=recorded.run_id,
            user_id=recorded.user_id,
            runtime_thread_id=recorded.runtime_thread_id,
        )
        differences = tuple(
            field_name
            for field_name in self._COMPARISON_FIELDS
            if getattr(recorded, field_name) != getattr(observed, field_name)
        )
        return TrajectoryReplayResult(
            matches=not differences,
            differences=differences,
            recorded_fingerprint=trajectory_fingerprint(recorded),
            observed_fingerprint=trajectory_fingerprint(observed),
            observed=observed,
        )


__all__ = [
    "PersistedRunTrajectory",
    "RecordedTrajectoryEvent",
    "RuntimeTrajectoryRecorder",
    "RuntimeTrajectoryReplayer",
    "SAFE_EVENT_PAYLOAD_FIELDS",
    "TrajectoryReplayError",
    "TrajectoryReplayResult",
    "trajectory_fingerprint",
]
