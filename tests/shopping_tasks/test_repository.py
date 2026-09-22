from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.shopping_tasks.contracts import ShoppingTaskRequest, StepResult
from app.shopping_tasks.models import (
    ShoppingTask,
    ShoppingTaskArtifact,
    ShoppingTaskAttempt,
    ShoppingTaskCommand,
    ShoppingTaskEvent,
    ShoppingTaskPlan,
    ShoppingTaskStep,
)
from app.shopping_tasks.repository import (
    LeaseConflict,
    claim_ready_step,
    claim_ready_steps,
    claim_task,
    create_task,
    repair_task_plan,
    save_step_result,
    snapshot,
)


def session_factory():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        ShoppingTask.__table__,
        ShoppingTaskPlan.__table__,
        ShoppingTaskStep.__table__,
        ShoppingTaskAttempt.__table__,
        ShoppingTaskArtifact.__table__,
        ShoppingTaskEvent.__table__,
        ShoppingTaskCommand.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    return sessionmaker(bind=engine)


def test_create_is_owner_scoped_and_idempotent() -> None:
    Session = session_factory()
    session = Session()
    request = ShoppingTaskRequest(
        kind="compatibility_diagnosis", goal_text="连接无画面"
    )
    first = create_task(session, owner_id="u-1", request=request, idempotency_key="k-1")
    session.commit()
    replay = create_task(
        session, owner_id="u-1", request=request, idempotency_key="k-1"
    )
    assert replay.id == first.id
    assert snapshot(session, owner_id="u-2", task_id=first.id) is None


def test_expired_step_lease_cannot_publish_late_result() -> None:
    Session = session_factory()
    session = Session()
    task = create_task(
        session,
        owner_id="u-1",
        request=ShoppingTaskRequest(
            kind="compatibility_diagnosis", goal_text="连接无画面"
        ),
        idempotency_key="k-1",
    )
    session.commit()
    claimed = claim_task(
        session, worker_id="worker-a", lease_seconds=1, now=datetime.now(timezone.utc)
    )
    assert claimed is not None
    task, task_token = claimed
    step, attempt = claim_ready_step(
        session,
        task=task,
        lease_token=task_token,
        lease_seconds=1,
        now=datetime.now(timezone.utc),
    )
    session.commit()
    step.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    result = StepResult(
        task_id=task.id,
        plan_revision=task.active_plan_revision,
        step_key=step.step_key,
        role=step.role,
        status="completed",
        output_kind=step.output_kind,
        output={},
        input_fingerprint="f",
    )
    try:
        save_step_result(
            session,
            task=task,
            step=step,
            attempt=attempt,
            lease_token=step.lease_token or "",
            result=result,
        )
    except LeaseConflict:
        session.rollback()
    else:
        raise AssertionError("expired lease was allowed to publish")


def test_snapshot_exposes_lease_state_without_leaking_the_lease_token() -> None:
    Session = session_factory()
    session = Session()
    task = create_task(
        session,
        owner_id="u-lease",
        request=ShoppingTaskRequest(
            kind="compatibility_diagnosis", goal_text="连接无画面"
        ),
        idempotency_key="k-lease",
    )
    session.commit()
    claimed = claim_task(
        session, worker_id="worker-a", lease_seconds=30, now=datetime.now(timezone.utc)
    )
    assert claimed is not None
    task, task_token = claimed
    step, _attempt = claim_ready_step(
        session,
        task=task,
        lease_token=task_token,
        lease_seconds=30,
        now=datetime.now(timezone.utc),
    )
    session.commit()

    result = snapshot(session, owner_id="u-lease", task_id=task.id)
    assert result is not None
    by_key = {item.key: item for item in result.steps}

    claimed_step = by_key[step.step_key]
    assert claimed_step.plan_revision == 1
    assert claimed_step.has_lease is True
    assert claimed_step.lease_until == step.lease_until

    unclaimed = [item for item in result.steps if item.key != step.step_key]
    assert unclaimed, "expected at least one step the frontier did not claim"
    assert all(
        item.has_lease is False and item.lease_until is None for item in unclaimed
    )

    # `lease_token` is a fencing credential; TaskStepView doesn't declare it at all
    # (and, being extra="forbid", would have rejected construction if repository.py
    # ever tried to include it) — this is an explicit regression check on top of that.
    assert not any(hasattr(item, "lease_token") for item in result.steps)
    assert "lease_token" not in result.model_dump_json()


def test_ready_frontier_is_bounded_to_three_independent_steps() -> None:
    Session = session_factory()
    session = Session()
    task = create_task(
        session,
        owner_id="u-1",
        request=ShoppingTaskRequest(kind="bundle_selection", goal_text="办公组合"),
        idempotency_key="k-frontier",
    )
    session.commit()
    claimed = claim_task(session, worker_id="worker-a", lease_seconds=30)
    assert claimed is not None
    task, token = claimed
    session.commit()
    root, attempt = claim_ready_step(
        session, task=task, lease_token=token, lease_seconds=30
    )
    root.status = "completed"
    root.lease_token = None
    root.lease_until = None
    session.commit()
    task = session.get(ShoppingTask, task.id)
    frontier = claim_ready_steps(
        session, task=task, lease_token=token, max_steps=3, lease_seconds=30
    )
    assert 1 <= len(frontier) <= 3
    assert len({step.step_key for step, _attempt in frontier}) == len(frontier)


def test_verification_repair_reuses_independent_steps_and_invalidates_descendants() -> (
    None
):
    Session = session_factory()
    session = Session()
    task = create_task(
        session,
        owner_id="u-repair",
        request=ShoppingTaskRequest(
            kind="bundle_selection",
            goal_text="预算 6000 元三件套",
        ),
        idempotency_key="repair-create",
    )
    session.commit()
    current_steps = list(
        session.query(ShoppingTaskStep)
        .filter(
            ShoppingTaskStep.task_id == task.id,
            ShoppingTaskStep.plan_revision == 1,
        )
        .all()
    )
    for step in current_steps:
        step.status = "completed"
        step.output_json = {"step": step.step_key}
    session.commit()

    proposal = repair_task_plan(
        session,
        task=task,
        report={
            "status": "repairable",
            "progress_fingerprint": "progress-1",
            "issues": [
                {
                    "code": "evidence_unavailable",
                    "allowed_repairs": ["retrieve_evidence"],
                }
            ],
        },
    )
    assert proposal is not None and proposal.revision == 2
    session.flush()
    revised = {
        step.step_key: step
        for step in session.query(ShoppingTaskStep)
        .filter(
            ShoppingTaskStep.task_id == task.id,
            ShoppingTaskStep.plan_revision == 2,
        )
        .all()
    }
    assert revised["extract_goal"].status == "completed"
    assert revised["catalog_candidates"].status == "completed"
    assert revised["retrieve_evidence"].status == "pending"
    assert revised["verify_result"].status == "pending"
    assert revised["compose_result"].status == "pending"
    assert task.budget_json["plan_repairs"] == 1
