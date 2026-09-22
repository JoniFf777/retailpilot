"""Owner-scoped persistence and fencing primitives for task workers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .contracts import (
    DEFAULT_RESULT_RETENTION_DAYS,
    DEFAULT_TASK_TTL_HOURS,
    Artifact,
    GoalSpec,
    PlanProposal,
    ShoppingTaskRequest,
    StepResult,
    TaskSnapshot,
    canonical_fingerprint,
)
from .models import (
    ShoppingTask,
    ShoppingTaskAction,
    ShoppingTaskArtifact,
    ShoppingTaskAttempt,
    ShoppingTaskCommand,
    ShoppingTaskEvent,
    ShoppingTaskPlan,
    ShoppingTaskStep,
)
from .planner import assert_valid_plan, build_goal, offline_plan
from .budget import (
    BudgetExceeded,
    record_usage,
    reserve_plan_repair,
    reserve_step_attempt,
)
from .repair import revise_plan_locally


class CommandConflict(ValueError):
    """An idempotency key was reused with different input."""


class VersionConflict(ValueError):
    """The caller attempted to mutate an old interaction version."""


class LeaseConflict(ValueError):
    """A worker no longer owns the task or step lease."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _hash_body(body: Any) -> str:
    return sha256(
        json.dumps(body, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def find_command(
    session: Session, *, owner_id: str, operation: str, idempotency_key: str, body: Any
) -> ShoppingTaskCommand | None:
    row = session.scalar(
        select(ShoppingTaskCommand).where(
            ShoppingTaskCommand.owner_id == owner_id,
            ShoppingTaskCommand.operation == operation,
            ShoppingTaskCommand.idempotency_key == idempotency_key,
        )
    )
    if row is not None and row.request_hash != _hash_body(body):
        raise CommandConflict("idempotency_key_conflict")
    return row


def create_task(
    session: Session,
    *,
    owner_id: str,
    request: ShoppingTaskRequest,
    idempotency_key: str,
    mode: str = "offline",
    plan_builder=None,
    now: datetime | None = None,
) -> ShoppingTask:
    body = request.model_dump(mode="json")
    existing = find_command(
        session,
        owner_id=owner_id,
        operation="create_task",
        idempotency_key=idempotency_key,
        body=body,
    )
    if existing is not None and existing.task_id is not None:
        return session.get(ShoppingTask, existing.task_id)
    if mode not in {"offline", "agent"}:
        raise ValueError("mode_is_server_owned")
    now = now or _now()
    goal = build_goal(request)
    plan = plan_builder(goal) if plan_builder is not None else offline_plan(goal)
    assert_valid_plan(plan, goal=goal)
    task_id = uuid4()
    task = ShoppingTask(
        id=task_id,
        owner_id=owner_id,
        kind=request.kind,
        thread_id=request.thread_id,
        status="queued",
        mode=mode,
        goal_json=goal.model_dump(mode="json"),
        budget_json={
            "step_attempts": 0,
            "model_attempts": 1 if mode == "agent" else 0,
            "interaction_rounds": 0,
            "plan_repairs": 0,
            "unknown_usage": 0,
            "max_step_attempts": 36,
            "max_model_attempts": 24,
            "max_plan_repairs": 2,
            "max_interaction_rounds": 5,
        },
        expires_at=now + timedelta(hours=DEFAULT_TASK_TTL_HOURS),
        retention_until=now + timedelta(days=DEFAULT_RESULT_RETENTION_DAYS),
    )
    session.add(task)
    session.flush()
    session.add(
        ShoppingTaskPlan(
            task_id=task.id,
            revision=plan.revision,
            plan_json=plan.model_dump(mode="json"),
            fingerprint=plan.fingerprint,
            reason=plan.reason,
        )
    )
    for item in plan.steps:
        session.add(
            ShoppingTaskStep(
                task_id=task.id,
                plan_revision=plan.revision,
                step_key=item.key,
                capability=item.capability,
                role=item.role,
                dependencies_json=item.depends_on,
                input_refs_json=item.input_refs,
                output_kind=item.output_kind,
            )
        )
    command = ShoppingTaskCommand(
        owner_id=owner_id,
        task_id=task.id,
        operation="create_task",
        idempotency_key=idempotency_key,
        request_hash=_hash_body(body),
        result_json={"task_id": str(task.id)},
    )
    session.add(command)
    session.flush()
    append_event(
        session, task, "task.created", {"status": task.status, "mode": task.mode}
    )
    return task


def get_task(
    session: Session, *, owner_id: str, task_id: UUID, for_update: bool = False
) -> ShoppingTask | None:
    statement = select(ShoppingTask).where(
        ShoppingTask.id == task_id,
        ShoppingTask.owner_id == owner_id,
        ShoppingTask.deleted_at.is_(None),
    )
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def list_tasks(
    session: Session, *, owner_id: str, limit: int = 50, offset: int = 0
) -> list[ShoppingTask]:
    return list(
        session.scalars(
            select(ShoppingTask)
            .where(ShoppingTask.owner_id == owner_id, ShoppingTask.deleted_at.is_(None))
            .order_by(ShoppingTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )


def get_plan(session: Session, task_id: UUID, revision: int) -> PlanProposal:
    row = session.scalar(
        select(ShoppingTaskPlan).where(
            ShoppingTaskPlan.task_id == task_id, ShoppingTaskPlan.revision == revision
        )
    )
    if row is None:
        raise LookupError("task_plan_not_found")
    return PlanProposal.model_validate(row.plan_json)


def revise_task_plan(
    session: Session, *, task: ShoppingTask, reason: str
) -> PlanProposal:
    """Persist a new immutable plan revision for an accepted user change."""
    goal = GoalSpec.model_validate(task.goal_json)
    previous = get_plan(session, task.id, task.active_plan_revision)
    proposed = offline_plan(goal).model_copy(
        update={"revision": previous.revision + 1, "reason": reason, "fingerprint": ""}
    )
    proposed = PlanProposal.model_validate(proposed.model_dump())
    assert_valid_plan(proposed, goal=goal)
    for step in session.scalars(
        select(ShoppingTaskStep).where(
            ShoppingTaskStep.task_id == task.id,
            ShoppingTaskStep.plan_revision == task.active_plan_revision,
        )
    ).all():
        step.status = "superseded"
        step.lease_token = None
        step.lease_until = None
    session.add(
        ShoppingTaskPlan(
            task_id=task.id,
            revision=proposed.revision,
            plan_json=proposed.model_dump(mode="json"),
            fingerprint=proposed.fingerprint,
            reason=reason,
            parent_revision=previous.revision,
        )
    )
    for item in proposed.steps:
        session.add(
            ShoppingTaskStep(
                task_id=task.id,
                plan_revision=proposed.revision,
                step_key=item.key,
                capability=item.capability,
                role=item.role,
                dependencies_json=item.depends_on,
                input_refs_json=item.input_refs,
                output_kind=item.output_kind,
            )
        )
    task.active_plan_revision = proposed.revision
    return proposed


def repair_task_plan(
    session: Session,
    *,
    task: ShoppingTask,
    report: dict[str, Any],
) -> PlanProposal | None:
    """Create one bounded local repair revision when verification is actionable.

    Only affected steps and their descendants are re-run. Completed independent
    steps keep their typed output and artifact reference in the new revision.
    """

    issues = list(report.get("issues") or [])
    affected: set[str] = set()
    capability_by_repair = {
        "retrieve_evidence": "retrieve_evidence",
        "replace_component": "solve_bundle",
    }
    current_plan = get_plan(session, task.id, task.active_plan_revision)
    current_step_keys = {step.key for step in current_plan.steps}
    for issue in issues:
        affected.update(
            str(value)
            for value in issue.get("affected_steps") or []
            if str(value) in current_step_keys
        )
        for repair in issue.get("allowed_repairs") or []:
            capability = capability_by_repair.get(str(repair))
            if capability:
                affected.update(
                    step.key
                    for step in current_plan.steps
                    if step.capability == capability
                )
    if not affected:
        return None

    progress = str(report.get("progress_fingerprint") or "")
    prior_reports = [
        step.output_json.get("verification_report")
        for step in task.steps
        if step.capability == "verify_result"
        and isinstance(step.output_json, dict)
        and isinstance(step.output_json.get("verification_report"), dict)
    ]
    if (
        progress
        and sum(item.get("progress_fingerprint") == progress for item in prior_reports)
        > 1
    ):
        return None

    repair_count = reserve_plan_repair(task)
    revision = revise_plan_locally(
        current_plan,
        affected_steps=affected,
        repair_count=repair_count - 1,
    )
    proposal = PlanProposal.model_validate(
        revision.proposal.model_copy(update={"fingerprint": ""}).model_dump()
    )
    assert_valid_plan(proposal, goal=GoalSpec.model_validate(task.goal_json))

    current_steps = list(
        session.scalars(
            select(ShoppingTaskStep).where(
                ShoppingTaskStep.task_id == task.id,
                ShoppingTaskStep.plan_revision == task.active_plan_revision,
            )
        ).all()
    )
    by_key = {step.step_key: step for step in current_steps}
    session.add(
        ShoppingTaskPlan(
            task_id=task.id,
            revision=proposal.revision,
            plan_json=proposal.model_dump(mode="json"),
            fingerprint=proposal.fingerprint,
            reason=revision.repair_reason or "verification_directed_repair",
            parent_revision=current_plan.revision,
        )
    )
    invalidated = set(revision.invalidated_steps)
    for item in proposal.steps:
        previous = by_key.get(item.key)
        reusable = (
            item.key not in invalidated
            and previous is not None
            and previous.status == "completed"
        )
        session.add(
            ShoppingTaskStep(
                task_id=task.id,
                plan_revision=proposal.revision,
                step_key=item.key,
                capability=item.capability,
                role=item.role,
                dependencies_json=item.depends_on,
                input_refs_json=item.input_refs,
                output_kind=item.output_kind,
                status="completed" if reusable else "pending",
                output_json=previous.output_json if reusable else None,
                input_fingerprint=previous.input_fingerprint if reusable else None,
                output_artifact_id=previous.output_artifact_id if reusable else None,
                completed_at=previous.completed_at if reusable else None,
            )
        )
    for previous in current_steps:
        previous.status = "superseded"
        previous.lease_token = None
        previous.lease_until = None
        if previous.step_key in invalidated and previous.output_artifact_id:
            artifact = session.get(ShoppingTaskArtifact, previous.output_artifact_id)
            if artifact is not None:
                artifact.superseded = True
                artifact.verification_status = "superseded"
    task.active_plan_revision = proposal.revision
    task.status = "queued"
    task.lease_token = None
    task.lease_until = None
    append_event(
        session,
        task,
        "plan.revised",
        {
            "revision": proposal.revision,
            "invalidated_steps": sorted(invalidated),
            "reason": "verification_directed_repair",
        },
    )
    return proposal


def append_event(
    session: Session, task: ShoppingTask, event_type: str, payload: dict[str, Any]
) -> ShoppingTaskEvent:
    # The task row is already locked by control transitions. Locking here also
    # makes the per-task public sequence monotonic across concurrent workers.
    if session.get(ShoppingTask, task.id) is not task:
        task = session.scalar(
            select(ShoppingTask).where(ShoppingTask.id == task.id).with_for_update()
        )
    last = (
        session.scalar(
            select(ShoppingTaskEvent.sequence)
            .where(ShoppingTaskEvent.task_id == task.id)
            .order_by(ShoppingTaskEvent.sequence.desc())
            .limit(1)
        )
        or 0
    )
    event = ShoppingTaskEvent(
        task_id=task.id,
        sequence=int(last) + 1,
        event_type=event_type,
        public_payload_json=payload,
    )
    session.add(event)
    session.flush()
    return event


def claim_task(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> tuple[ShoppingTask, str] | None:
    now = now or _now()
    statement = (
        select(ShoppingTask)
        .where(
            ShoppingTask.status.in_(("queued", "running")),
            ShoppingTask.cancel_requested.is_(False),
            ShoppingTask.deleted_at.is_(None),
            ShoppingTask.expires_at > now,
            (ShoppingTask.lease_until.is_(None) | (ShoppingTask.lease_until < now)),
        )
        .order_by(ShoppingTask.created_at, ShoppingTask.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = session.scalar(statement)
    if task is None:
        return None
    task.status = "running"
    task.scheduler_epoch += 1
    task.lease_token = uuid4().hex
    task.lease_until = now + timedelta(seconds=lease_seconds)
    expired_steps = list(
        session.scalars(
            select(ShoppingTaskStep)
            .where(
                ShoppingTaskStep.task_id == task.id,
                ShoppingTaskStep.plan_revision == task.active_plan_revision,
                ShoppingTaskStep.status == "running",
                ShoppingTaskStep.lease_until < now,
            )
            .with_for_update()
        ).all()
    )
    for step in expired_steps:
        step.status = "pending"
        step.lease_token = None
        step.lease_until = None
        attempt = session.scalar(
            select(ShoppingTaskAttempt)
            .where(
                ShoppingTaskAttempt.step_id == step.id,
                ShoppingTaskAttempt.status == "running",
            )
            .order_by(ShoppingTaskAttempt.attempt_no.desc())
            .limit(1)
            .with_for_update()
        )
        if attempt is not None:
            attempt.status = "failed"
            attempt.error_code = "step_lease_expired"
            attempt.finished_at = now
            attempt.usage_json = {"usage_unknown": True}
        ledger = dict(task.budget_json or {})
        task.budget_json = {
            **ledger,
            "unknown_usage": int(ledger.get("unknown_usage", 0)) + 1,
        }
    session.flush()
    append_event(
        session,
        task,
        "task.claimed",
        {"worker_id": worker_id, "epoch": task.scheduler_epoch},
    )
    return task, task.lease_token


def renew_task_lease(
    session: Session,
    *,
    task_id: UUID,
    lease_token: str,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> bool:
    task = session.scalar(
        select(ShoppingTask).where(ShoppingTask.id == task_id).with_for_update()
    )
    now = now or _now()
    if (
        task is None
        or task.lease_token != lease_token
        or task.status not in {"running", "queued"}
        or _aware(task.expires_at) <= now
    ):
        return False
    task.lease_until = now + timedelta(seconds=lease_seconds)
    session.flush()
    return True


def renew_task_step_leases(
    session: Session,
    *,
    task_id: UUID,
    step_id: UUID,
    task_lease_token: str,
    step_lease_token: str,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> bool:
    now = now or _now()
    task = session.scalar(
        select(ShoppingTask).where(ShoppingTask.id == task_id).with_for_update()
    )
    step = session.scalar(
        select(ShoppingTaskStep).where(ShoppingTaskStep.id == step_id).with_for_update()
    )
    if (
        task is None
        or step is None
        or task.lease_token != task_lease_token
        or step.lease_token != step_lease_token
        or task.status != "running"
        or step.status != "running"
        or task.cancel_requested
        or _aware(task.expires_at) <= now
    ):
        return False
    renewed_until = now + timedelta(seconds=lease_seconds)
    task.lease_until = renewed_until
    step.lease_until = renewed_until
    session.flush()
    return True


def claim_ready_step(
    session: Session,
    *,
    task: ShoppingTask,
    lease_token: str,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> tuple[ShoppingTaskStep, ShoppingTaskAttempt] | None:
    now = now or _now()
    if (
        task.lease_token != lease_token
        or task.lease_until is None
        or _aware(task.lease_until) <= now
    ):
        raise LeaseConflict("task_lease_expired")
    steps = list(
        session.scalars(
            select(ShoppingTaskStep)
            .where(
                ShoppingTaskStep.task_id == task.id,
                ShoppingTaskStep.plan_revision == task.active_plan_revision,
            )
            .order_by(ShoppingTaskStep.step_key)
            .with_for_update()
        ).all()
    )
    completed = {step.step_key for step in steps if step.status == "completed"}
    for step in steps:
        if step.status != "pending" or any(
            dep not in completed for dep in (step.dependencies_json or [])
        ):
            continue
        reserve_step_attempt(task)
        step.status = "running"
        step.attempt_count += 1
        step.lease_token = uuid4().hex
        step.lease_until = now + timedelta(seconds=lease_seconds)
        attempt = ShoppingTaskAttempt(
            task_id=task.id,
            step_id=step.id,
            attempt_no=step.attempt_count,
            usage_json={},
        )
        session.add(attempt)
        session.flush()
        return step, attempt
    return None


def claim_ready_steps(
    session: Session,
    *,
    task: ShoppingTask,
    lease_token: str,
    max_steps: int = 3,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> list[tuple[ShoppingTaskStep, ShoppingTaskAttempt]]:
    """Claim a bounded ready frontier for independent read-only branches."""
    now = now or _now()
    if max_steps < 1 or max_steps > 3:
        raise ValueError("max_steps must be between 1 and 3")
    if (
        task.lease_token != lease_token
        or task.lease_until is None
        or _aware(task.lease_until) <= now
    ):
        raise LeaseConflict("task_lease_expired")
    steps = list(
        session.scalars(
            select(ShoppingTaskStep)
            .where(
                ShoppingTaskStep.task_id == task.id,
                ShoppingTaskStep.plan_revision == task.active_plan_revision,
            )
            .order_by(ShoppingTaskStep.step_key)
            .with_for_update(skip_locked=True)
        ).all()
    )
    completed = {step.step_key for step in steps if step.status == "completed"}
    claimed: list[tuple[ShoppingTaskStep, ShoppingTaskAttempt]] = []
    for step in steps:
        if (
            len(claimed) >= max_steps
            or step.status != "pending"
            or any(dep not in completed for dep in (step.dependencies_json or []))
        ):
            continue
        reserve_step_attempt(task)
        step.status = "running"
        step.attempt_count += 1
        step.lease_token = uuid4().hex
        step.lease_until = now + timedelta(seconds=lease_seconds)
        attempt = ShoppingTaskAttempt(
            task_id=task.id,
            step_id=step.id,
            attempt_no=step.attempt_count,
            usage_json={},
        )
        session.add(attempt)
        session.flush()
        claimed.append((step, attempt))
    return claimed


def save_step_result(
    session: Session,
    *,
    task: ShoppingTask,
    step: ShoppingTaskStep,
    attempt: ShoppingTaskAttempt,
    lease_token: str,
    result: StepResult,
    source_refs: list[dict[str, Any]] | None = None,
) -> ShoppingTaskArtifact:
    current = session.scalar(
        select(ShoppingTask).where(ShoppingTask.id == task.id).with_for_update()
    )
    if (
        current is None
        or current.status in {"cancelled", "expired", "succeeded", "failed"}
        or current.lease_token is None
    ):
        raise LeaseConflict("task_terminal_or_deleted")
    if (
        step.lease_token != lease_token
        or step.lease_until is None
        or _aware(step.lease_until) <= _now()
        or result.plan_revision != current.active_plan_revision
    ):
        raise LeaseConflict("step_lease_fenced")
    artifact = ShoppingTaskArtifact(
        task_id=current.id,
        plan_revision=result.plan_revision,
        kind=result.output_kind,
        branch=result.step_key,
        payload_json=result.output,
        input_fingerprint=result.input_fingerprint,
        source_refs_json=source_refs or [],
        evidence_versions_json=result.evidence_versions,
        verification_status="pending",
    )
    session.add(artifact)
    session.flush()
    step.output_json = result.output
    step.output_artifact_id = artifact.id
    step.input_fingerprint = result.input_fingerprint
    step.status = (
        "completed" if result.status in {"completed", "waiting_input"} else "failed"
    )
    step.error_code = result.error_code
    step.lease_token = None
    step.lease_until = None
    step.completed_at = _now()
    attempt.status = result.status
    attempt.usage_json = result.usage
    record_usage(current, result.usage)
    attempt.error_code = result.error_code
    attempt.finished_at = _now()
    append_event(
        session,
        current,
        (
            "step.completed"
            if step.status == "completed"
            else (
                "step.waiting_input"
                if result.status == "waiting_input"
                else "step.failed"
            )
        ),
        {"step_key": step.step_key, "status": step.status},
    )
    if result.status == "waiting_input":
        current.status = "waiting_input"
        current.pending_interaction_json = result.output
        append_event(
            session, current, "task.waiting_input", {"step_key": step.step_key}
        )
    return artifact


def refresh_task_status(session: Session, *, task_id: UUID) -> ShoppingTask:
    task = session.scalar(
        select(ShoppingTask).where(ShoppingTask.id == task_id).with_for_update()
    )
    if task is None:
        raise LookupError("task_not_found")
    now = _now()
    if _aware(task.expires_at) <= now and task.status not in {
        "succeeded",
        "failed",
        "cancelled",
        "expired",
    }:
        task.status = "expired"
        task.lease_token = None
        task.lease_until = None
        for action in session.scalars(
            select(ShoppingTaskAction).where(
                ShoppingTaskAction.task_id == task.id,
                ShoppingTaskAction.status == "pending",
            )
        ).all():
            action.status = "expired"
        append_event(session, task, "task.expired", {})
        return task
    if task.cancel_requested and task.status not in {
        "succeeded",
        "failed",
        "cancelled",
        "expired",
    }:
        task.status = "cancelled"
        task.lease_token = None
        task.lease_until = None
        for action in session.scalars(
            select(ShoppingTaskAction).where(
                ShoppingTaskAction.task_id == task.id,
                ShoppingTaskAction.status == "pending",
            )
        ).all():
            action.status = "cancelled"
        append_event(session, task, "task.cancelled", {})
        return task
    steps = list(
        session.scalars(
            select(ShoppingTaskStep).where(
                ShoppingTaskStep.task_id == task.id,
                ShoppingTaskStep.plan_revision == task.active_plan_revision,
            )
        ).all()
    )
    if (
        task.status != "waiting_input"
        and steps
        and all(step.status in {"completed", "skipped"} for step in steps)
    ):
        task.status = "succeeded"
        task.lease_token = None
        task.lease_until = None
        append_event(session, task, "task.succeeded", {})
    return task


def snapshot(session: Session, *, owner_id: str, task_id: UUID) -> TaskSnapshot | None:
    task = get_task(session, owner_id=owner_id, task_id=task_id)
    if task is None:
        return None
    plan = None
    plan_row = session.scalar(
        select(ShoppingTaskPlan).where(
            ShoppingTaskPlan.task_id == task.id,
            ShoppingTaskPlan.revision == task.active_plan_revision,
        )
    )
    if plan_row is not None:
        plan = PlanProposal.model_validate(plan_row.plan_json)
    last_sequence = (
        session.scalar(
            select(ShoppingTaskEvent.sequence)
            .where(ShoppingTaskEvent.task_id == task.id)
            .order_by(ShoppingTaskEvent.sequence.desc())
            .limit(1)
        )
        or 0
    )
    return TaskSnapshot(
        task_id=task.id,
        owner_id=task.owner_id,
        kind=task.kind,
        status=task.status,
        mode=task.mode,
        version=task.version,
        goal=GoalSpec.model_validate(task.goal_json),
        plan=plan,
        steps=[
            {
                "key": step.step_key,
                "plan_revision": step.plan_revision,
                "capability": step.capability,
                "role": step.role,
                "status": step.status,
                "attempt_count": step.attempt_count,
                "output_artifact_id": (
                    str(step.output_artifact_id) if step.output_artifact_id else None
                ),
                "has_lease": step.lease_token is not None,
                "lease_until": (
                    step.lease_until.isoformat() if step.lease_until else None
                ),
            }
            for step in task.steps
        ],
        artifacts=[
            {
                "id": str(item.id),
                "kind": item.kind,
                "branch": item.branch,
                "status": item.verification_status,
                "payload": item.payload_json,
            }
            for item in task.artifacts
        ],
        output=task.output_json,
        pending_interaction=task.pending_interaction_json,
        last_sequence=int(last_sequence),
    )


__all__ = [
    "CommandConflict",
    "LeaseConflict",
    "VersionConflict",
    "append_event",
    "claim_ready_step",
    "claim_ready_steps",
    "claim_task",
    "create_task",
    "find_command",
    "get_plan",
    "get_task",
    "list_tasks",
    "refresh_task_status",
    "renew_task_lease",
    "renew_task_step_leases",
    "repair_task_plan",
    "save_step_result",
    "snapshot",
]
