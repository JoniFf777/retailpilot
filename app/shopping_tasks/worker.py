"""Short-transaction task worker.

The worker claims facts in PostgreSQL, performs read-only work outside the
claim transaction, and commits results only with lease fencing.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Order, OrderItem, Product
from app.db.session import SessionLocal
from app.core.settings import get_settings
from app.repositories.catalog import list_active_skus

from .after_sales import OrderFactEnvelope, PolicyRule, assess_after_sales
from .bundle import solve_bundle
from .compatibility import CompatibilityRule
from .contracts import (
    Fact,
    GoalSpec,
    SourceRef,
    StepResult,
    VerificationReport,
    canonical_fingerprint,
)
from .diagnosis import DiagnosticCheck
from .evidence import TaskQuerySpec, retrieve_task_evidence
from .models import (
    CatalogCompatibilityRule,
    ShoppingPolicyRule,
    ShoppingTask,
    ShoppingTaskAttempt,
    ShoppingTaskStep,
    ShoppingTaskWorkerHeartbeat,
)
from .model_gateway import review_with_gateway
from .reviewer import merge_reviewer_supplement
from .budget import BudgetExceeded, reserve_model_attempt
from .repository import (
    LeaseConflict,
    append_event,
    claim_ready_steps,
    claim_task,
    refresh_task_status,
    repair_task_plan,
    renew_task_step_leases,
    save_step_result,
)
from .verifier import verify_task_output


_TASK_FIXTURES = (
    Path(__file__).resolve().parents[2] / "data" / "shopping_task_fixtures.json"
)


def _json_candidate(item: Any) -> dict[str, Any]:
    return {
        "product_id": str(item.product_id),
        "product_code": item.product_code,
        "sku_id": str(item.sku_id),
        "sku_code": item.sku_code,
        "sku_name": item.sku_name,
        "money_amount": str(item.money_amount),
        "currency": item.currency,
        "product_attributes": item.product_attributes,
        "variant_attributes": item.variant_attributes,
        "available_quantity": item.available_quantity,
    }


def _outputs(task: ShoppingTask) -> dict[str, dict[str, Any]]:
    return {
        step.step_key: step.output_json or {}
        for step in task.steps
        if step.output_json is not None
    }


def _fact(goal: dict[str, Any], key: str) -> Any:
    return (goal.get("hard_constraints") or {}).get(
        key, (goal.get("soft_requirements") or {}).get(key)
    )


def execute_step(
    session: Session, task: ShoppingTask, step: ShoppingTaskStep
) -> StepResult:
    goal = task.goal_json
    outputs = _outputs(task)
    payload: dict[str, Any] = {}
    if step.capability == "extract_goal":
        payload = {"goal": goal}
    elif step.capability == "catalog_candidates":
        candidates: dict[str, list[dict[str, Any]]] = {}
        for slot in ("laptop", "monitor", "dock"):
            try:
                candidates[slot] = [
                    _json_candidate(item)
                    for item in list_active_skus(session, category_code=slot)
                ]
            except Exception:
                candidates[slot] = []
        payload = {"candidates": candidates, "candidate_limit_per_slot": 5}
    elif step.capability == "lookup_compatibility":
        rules = []
        for row in session.scalars(
            select(CatalogCompatibilityRule).where(
                CatalogCompatibilityRule.active.is_(True)
            )
        ).all():
            rules.append(
                {
                    "left_sku": row.left_sku_code,
                    "right_sku": row.right_sku_code,
                    "state": row.state,
                    "reason": row.reason,
                    "rule_version": row.rule_version,
                    "source_ref": row.source_ref_json,
                }
            )
        payload = {"rules": rules}
    elif step.capability == "solve_bundle":
        rules = [
            CompatibilityRule.model_validate(rule)
            for rule in outputs.get("lookup_compatibility", {}).get("rules", [])
        ]
        payload = {
            "bundle_proposal": solve_bundle(
                outputs.get("catalog_candidates", {}).get("candidates", {}),
                rules,
                budget=_fact(goal, "budget") or _fact(goal, "total_budget"),
                currency=str(_fact(goal, "currency") or "CNY").upper(),
                locked=goal.get("locked_selections") or {},
                excluded_skus=goal.get("excluded_skus") or [],
            ).model_dump(mode="json")
        }
    elif step.capability == "retrieve_evidence":
        # The shared retrieval pipeline is used here; only the public citation
        # projection is retained in the task artifact.
        spec = TaskQuerySpec(
            original_question=goal.get("goal_text", ""),
            evidence_type=(
                "store_policy"
                if task.kind == "after_sales_assessment"
                else "compatibility"
            ),
            category_code="laptop" if task.kind == "bundle_selection" else None,
            limit=6,
        )
        payload = retrieve_task_evidence(spec, session_factory=SessionLocal).model_dump(
            mode="json"
        )
    elif step.capability == "suggest_diagnostic_check":
        refs = [
            SourceRef(source="evidence", source_id=str(item.get("id")))
            for item in outputs.get("retrieve_evidence", {}).get("citations", [])
            if item.get("id")
        ]
        fixture_checks = json.loads(_TASK_FIXTURES.read_text(encoding="utf-8")).get(
            "diagnostic_checks", []
        )
        state = goal.get("diagnosis_state") or {}
        answered = set(state.get("answered_check_ids") or [])
        if int(state.get("round", 0)) >= 5:
            payload = {
                "unresolved": True,
                "reason": "达到最多五轮人工反馈上限，建议人工检查设备和线缆。",
                "answered_check_ids": sorted(answered),
            }
        else:
            check = next(
                (item for item in fixture_checks if item["check_id"] not in answered),
                None,
            ) or {
                "check_id": "check-cable-and-power",
                "question": "设备重新连接后是否仍无画面或供电？",
                "safe_instruction": "请只观察指示灯、画面和供电状态；不要拆机或远程控制设备。",
                "source_id": "diagnosis-safe-baseline",
            }
            payload = {
                "diagnostic_check": DiagnosticCheck(
                    check_id=check["check_id"],
                    question=check["question"],
                    safe_instruction=check["safe_instruction"],
                    source_ref=(
                        refs[0]
                        if refs
                        else SourceRef(
                            source="evidence",
                            source_id=check["source_id"],
                            source_version="2026.09.20",
                            verified=True,
                        )
                    ),
                ).model_dump(mode="json")
            }
    elif step.capability == "read_owned_order":
        requested = _fact(goal, "order_id")
        query = (
            select(Order)
            .where(Order.customer_id == task.owner_id)
            .order_by(Order.order_date.desc())
        )
        if requested:
            query = query.where(Order.order_id == str(requested))
        order = session.scalar(query)
        if order is None:
            payload = {"order": None, "missing_facts": ["owned_order"]}
        else:
            items = list(
                session.scalars(
                    select(OrderItem).where(OrderItem.order_id == order.order_id)
                ).all()
            )
            payload = {
                "order": OrderFactEnvelope(
                    order_id=order.order_id,
                    owner_id=task.owner_id,
                    order_status=order.status,
                    order_date=order.order_date,
                    delivered_at=None,
                    item_skus=[item.product_id for item in items],
                    facts=[
                        SourceRef(
                            source="order", source_id=order.order_id, verified=True
                        )
                    ],
                ).model_dump(mode="json"),
                "missing_facts": ["delivered_at"],
            }
    elif step.capability == "assess_policy":
        raw_order = outputs.get("read_owned_order", {}).get("order")
        if raw_order is None:
            payload = {
                "assessment": {
                    "outcome": "unknown",
                    "reason": "找不到本人订单。",
                    "missing_facts": ["owned_order"],
                }
            }
        else:
            order = OrderFactEnvelope.model_validate(raw_order)
            row = session.scalar(
                select(ShoppingPolicyRule)
                .where(
                    ShoppingPolicyRule.active.is_(True),
                    ShoppingPolicyRule.policy_type == "return",
                    ShoppingPolicyRule.region == "CN",
                    ShoppingPolicyRule.channel == "online",
                )
                .order_by(ShoppingPolicyRule.valid_from.desc())
            )
            policy = (
                PolicyRule(
                    policy_type=row.policy_type,
                    region=row.region,
                    channel=row.channel,
                    valid_from=row.valid_from.date(),
                    valid_until=row.valid_until.date() if row.valid_until else None,
                    return_window_days=row.return_window_days,
                    requires_unopened=row.requires_unopened,
                    source_ref=SourceRef.model_validate(row.source_ref_json),
                )
                if row
                else None
            )
            payload = {
                "assessment": assess_after_sales(
                    order, policy, today=date.today()
                ).model_dump(mode="json"),
                "order": raw_order,
            }
    elif step.capability == "verify_result":
        merged: dict[str, Any] = {}
        merged.update(outputs.get("solve_bundle", {}))
        merged.update(outputs.get("suggest_diagnostic_check", {}))
        merged.update(outputs.get("assess_policy", {}))
        evidence = outputs.get("retrieve_evidence", {})
        report = verify_task_output(
            task.kind,
            merged,
            evidence_available=evidence.get("status") not in {"unavailable", "timeout"},
        )
        payload = {"verification_report": report.model_dump(mode="json")}
    elif step.capability == "compose_result":
        merged = {}
        merged.update(outputs.get("solve_bundle", {}))
        merged.update(outputs.get("suggest_diagnostic_check", {}))
        merged.update(outputs.get("assess_policy", {}))
        merged["verification_report"] = outputs.get("verify_result", {}).get(
            "verification_report"
        )
        if task.kind == "bundle_selection":
            payload = {
                "outcome": (merged.get("bundle_proposal") or {}).get(
                    "outcome", "unknown"
                ),
                **merged,
            }
        elif task.kind == "after_sales_assessment":
            payload = {
                "outcome": (merged.get("assessment") or {}).get("outcome", "unknown"),
                **merged,
            }
        else:
            payload = {"outcome": "needs_information", **merged}
    else:
        raise ValueError("unsupported_task_capability")
    result_status = (
        "waiting_input"
        if step.capability == "extract_goal" and (goal.get("open_questions") or [])
        else "completed"
    )
    return StepResult(
        task_id=task.id,
        plan_revision=task.active_plan_revision,
        step_key=step.step_key,
        role=step.role,
        status=result_status,
        output_kind=step.output_kind,
        output=(
            payload
            if result_status == "completed"
            else {"waiting_for": goal.get("open_questions"), "goal": goal}
        ),
        input_fingerprint=canonical_fingerprint(
            {
                "goal": goal,
                "step": step.step_key,
                "dependencies": [outputs.get(dep) for dep in step.dependencies_json],
            }
        ),
        usage={"prompt_tokens": None, "completion_tokens": None},
    )


def _execute_claimed_step(
    task_id,
    step_id,
    attempt_id,
    task_token: str,
    step_token: str,
    lease_seconds: int,
) -> None:
    """Execute one branch in its own short-lived session."""
    branch_session = SessionLocal()
    stop_renewal = threading.Event()

    def renew() -> None:
        interval = max(1.0, lease_seconds / 3)
        while not stop_renewal.wait(interval):
            renewal_session = SessionLocal()
            try:
                renewed = renew_task_step_leases(
                    renewal_session,
                    task_id=task_id,
                    step_id=step_id,
                    task_lease_token=task_token,
                    step_lease_token=step_token,
                    lease_seconds=lease_seconds,
                )
                renewal_session.commit()
                if not renewed:
                    return
            except Exception:
                renewal_session.rollback()
                return
            finally:
                renewal_session.close()

    renewal_thread = threading.Thread(
        target=renew,
        name=f"shopping-task-renew-{step_id}",
        daemon=True,
    )
    renewal_thread.start()
    try:
        task = branch_session.get(ShoppingTask, task_id)
        step = branch_session.get(ShoppingTaskStep, step_id)
        attempt = branch_session.get(ShoppingTaskAttempt, attempt_id)
        if task is None or step is None or attempt is None:
            raise LeaseConflict("claimed_step_missing")
        result = execute_step(branch_session, task, step)
        if (
            step.capability == "verify_result"
            and task.mode == "agent"
            and isinstance(result.output.get("verification_report"), dict)
        ):
            deterministic = VerificationReport.model_validate(
                result.output["verification_report"]
            )
            reserve_model_attempt(task)
            branch_session.commit()
            supplement = review_with_gateway(
                GoalSpec.model_validate(task.goal_json),
                deterministic,
                _outputs(task),
                settings=get_settings(),
                owner_id=task.owner_id,
                idempotency_scope=(
                    f"{task.id}:{task.active_plan_revision}:{step.step_key}:"
                    f"{step.attempt_count}"
                ),
            )
            merged = merge_reviewer_supplement(deterministic, supplement)
            result = result.model_copy(
                update={
                    "output": {"verification_report": merged.model_dump(mode="json")}
                }
            )
            # Lease renewal happens in an independent session while the model
            # call is in flight. Expire the identity map before fencing the
            # result so we observe the renewed deadlines rather than the
            # pre-call copies.
            branch_session.expire_all()
            task = branch_session.get(ShoppingTask, task_id)
            step = branch_session.get(ShoppingTaskStep, step_id)
            attempt = branch_session.get(ShoppingTaskAttempt, attempt_id)
            if task is None or step is None or attempt is None:
                raise LeaseConflict("reviewed_step_missing")
        save_step_result(
            branch_session,
            task=task,
            step=step,
            attempt=attempt,
            lease_token=step_token,
            result=result,
        )
        branch_session.commit()
    finally:
        stop_renewal.set()
        renewal_thread.join(timeout=max(1.0, lease_seconds / 3 + 1))
        branch_session.close()


def run_worker_once(
    session: Session, *, worker_id: str | None = None, lease_seconds: int = 30
) -> bool:
    worker_id = worker_id or uuid4().hex
    now = datetime.now(timezone.utc)
    heartbeat = session.get(ShoppingTaskWorkerHeartbeat, worker_id)
    if heartbeat is None:
        heartbeat = ShoppingTaskWorkerHeartbeat(
            worker_id=worker_id,
            started_at=now,
            last_seen_at=now,
        )
        session.add(heartbeat)
    else:
        heartbeat.last_seen_at = now
    session.commit()
    claimed = claim_task(session, worker_id=worker_id, lease_seconds=lease_seconds)
    if claimed is None:
        session.commit()
        return False
    task, task_token = claimed
    session.commit()
    task = session.get(ShoppingTask, task.id)
    try:
        claimed_steps = claim_ready_steps(
            session,
            task=task,
            lease_token=task_token,
            max_steps=3,
            lease_seconds=lease_seconds,
        )
        if not claimed_steps:
            refresh_task_status(session, task_id=task.id)
            task.lease_token = None
            task.lease_until = None
            session.commit()
            return True
        claimed = [
            (step.id, attempt.id, step.lease_token or "")
            for step, attempt in claimed_steps
        ]
        session.commit()
        # Branch I/O is outside the claim transaction and can run concurrently;
        # each branch commits through its own session with step fencing.
        with ThreadPoolExecutor(
            max_workers=len(claimed), thread_name_prefix="shopmind-task-step"
        ) as executor:
            futures = [
                executor.submit(
                    _execute_claimed_step,
                    task.id,
                    step_id,
                    attempt_id,
                    task_token,
                    step_token,
                    lease_seconds,
                )
                for step_id, attempt_id, step_token in claimed
            ]
            for future in as_completed(futures):
                future.result()
        session.expire_all()
        task = session.get(ShoppingTask, task.id)
        verify_step = session.scalar(
            select(ShoppingTaskStep).where(
                ShoppingTaskStep.task_id == task.id,
                ShoppingTaskStep.plan_revision == task.active_plan_revision,
                ShoppingTaskStep.capability == "verify_result",
                ShoppingTaskStep.status == "completed",
            )
        )
        if verify_step is not None and isinstance(verify_step.output_json, dict):
            report = verify_step.output_json.get("verification_report")
            if isinstance(report, dict) and report.get("status") == "repairable":
                try:
                    repaired = repair_task_plan(session, task=task, report=report)
                except BudgetExceeded:
                    repaired = None
                if repaired is not None:
                    session.commit()
                    return True
            if isinstance(report, dict) and report.get("status") == "needs_input":
                task.status = "waiting_input"
                task.pending_interaction_json = {
                    "verification_issues": report.get("issues") or []
                }
                task.lease_token = None
                task.lease_until = None
                append_event(
                    session,
                    task,
                    "task.waiting_input",
                    {"step_key": verify_step.step_key},
                )
                session.commit()
                return True
            if isinstance(report, dict) and report.get("status") == "rejected":
                task.status = "failed"
                task.lease_token = None
                task.lease_until = None
                append_event(
                    session, task, "task.failed", {"code": "verification_rejected"}
                )
                session.commit()
                return True
        task = refresh_task_status(session, task_id=task.id)
        if task.status == "running":
            # A worker turn is short-lived; release the scheduler lease so the
            # next ready frontier can be claimed immediately by this or another
            # worker. Step leases continue to fence each branch independently.
            task.lease_token = None
            task.lease_until = None
        if task.status == "succeeded":
            task.output_json = outputs = _outputs(task)
            task.output_json = outputs.get("compose_result") or task.output_json
        session.commit()
        return True
    except LeaseConflict:
        session.rollback()
        return True
    except Exception as exc:
        session.rollback()
        task = session.get(ShoppingTask, task.id)
        if task is not None and task.status not in {
            "cancelled",
            "expired",
            "succeeded",
        }:
            task.status = "failed"
            task.lease_token = None
            task.lease_until = None
            append_event(session, task, "task.failed", {"code": type(exc).__name__})
            session.commit()
        return True


__all__ = ["execute_step", "run_worker_once"]
