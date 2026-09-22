"""Owner-scoped task workbench API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes._helpers import service_error_response
from app.catalog.models import CatalogSku
from app.db.session import get_db_session
from app.core.settings import get_settings
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.repositories.shopmind_cart import upsert_cart_item
from app.security import AuditRequestOperation, IdentityBoundary
from app.schemas.shopping_tasks import ShoppingTaskActionRequest, ShoppingTaskCommandRequest, ShoppingTaskConfirmRequest, ShoppingTaskCreateRequest, ShoppingTaskInputRequest
from app.shopping_tasks.actions import (
    ShoppingTaskActionError,
    confirm_task_action as confirm_task_action_service,
)
from app.shopping_tasks.models import ShoppingTaskAction, ShoppingTaskArtifact, ShoppingTaskCommand, ShoppingTaskEvent, ShoppingTaskStep
from app.shopping_tasks.model_gateway import plan_with_gateway
from app.shopping_tasks.repository import CommandConflict, append_event, create_task, find_command, get_task, list_tasks, refresh_task_status, revise_task_plan, snapshot


router = APIRouter(prefix="/shopping-tasks", tags=["shopping-tasks"])


def _body_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _identity(boundary: IdentityBoundary, user_id: str | None):
    return bind_request_user(boundary, user_id, require_user=True, request_operation=AuditRequestOperation.CHAT)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Shopping task not found")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_shopping_task(
    body: ShoppingTaskCreateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key required")
    settings = getattr(request.app.state, "runtime_settings", None) or get_settings()
    if not settings.shopmind_shopping_tasks_enabled:
        raise HTTPException(status_code=404, detail="Shopping tasks are disabled")
    identity = _identity(identity_boundary, body.user_id)
    try:
        plan_builder = None
        if settings.shopmind_shopping_task_mode == "agent":
            plan_builder = lambda goal: plan_with_gateway(
                goal,
                settings=settings,
                owner_id=identity.effective_user_id or "",
            )
        task = create_task(session, owner_id=identity.effective_user_id or "", request=body.to_contract(), idempotency_key=idempotency_key, mode=settings.shopmind_shopping_task_mode, plan_builder=plan_builder)
        session.commit()
        return {"task_id": str(task.id), "status": task.status, "version": task.version, "mode": task.mode, "accepted": True}
    except CommandConflict as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("")
async def list_shopping_tasks(
    user_id: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    identity = _identity(identity_boundary, user_id)
    rows = list_tasks(session, owner_id=identity.effective_user_id or "", limit=limit, offset=offset)
    return {"items": [{"task_id": str(row.id), "kind": row.kind, "status": row.status, "mode": row.mode, "version": row.version, "created_at": row.created_at} for row in rows], "limit": limit, "offset": offset}


@router.get("/{task_id}")
async def get_shopping_task(task_id: UUID, user_id: str | None = Query(default=None), identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session)) -> dict[str, Any]:
    identity = _identity(identity_boundary, user_id)
    value = snapshot(session, owner_id=identity.effective_user_id or "", task_id=task_id)
    if value is None:
        raise _not_found()
    return value.model_dump(mode="json")


@router.post("/{task_id}/inputs")
async def add_task_inputs(task_id: UUID, body: ShoppingTaskInputRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session)) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key required")
    identity = _identity(identity_boundary, body.user_id)
    task = get_task(session, owner_id=identity.effective_user_id or "", task_id=task_id, for_update=True)
    if task is None:
        raise _not_found()
    if task.version != body.expected_version:
        raise HTTPException(status_code=409, detail="task_version_conflict")
    if task.status in {"succeeded", "failed", "cancelled", "expired"}:
        raise HTTPException(status_code=409, detail="terminal_task_requires_new_parent_task")
    command_body = body.model_dump(mode="json")
    try:
        replay = find_command(session, owner_id=identity.effective_user_id or "", operation=f"task:{task_id}:inputs", idempotency_key=idempotency_key, body=command_body)
        if replay is not None:
            return replay.result_json or {"task_id": str(task_id), "status": task.status, "version": task.version}
        goal = dict(task.goal_json)
        facts = list(goal.get("facts") or [])
        facts.extend(item.model_dump(mode="json") for item in body.facts)
        if body.feedback:
            facts.append({"key": "user_feedback", "value": body.feedback, "source_ref": {"source": "user_reported", "source_id": f"task:{task_id}:feedback", "verified": False}})
            if task.kind == "compatibility_diagnosis":
                state = dict(goal.get("diagnosis_state") or {"round": 0, "answered_check_ids": [], "ruled_out": [], "observations": []})
                feedback_check = str(body.feedback.get("check_id") or "check-cable-and-power")
                if feedback_check in set(state.get("answered_check_ids") or []):
                    raise HTTPException(status_code=409, detail="diagnostic_question_already_answered")
                state["round"] = int(state.get("round", 0)) + 1
                state["answered_check_ids"] = [*(state.get("answered_check_ids") or []), feedback_check]
                state["observations"] = [*(state.get("observations") or []), {"check_id": feedback_check, "observation": str(body.feedback.get("observation") or ""), "source": "user_reported"}]
                goal["diagnosis_state"] = state
        goal["facts"] = facts
        # The initial plan may have been parked for missing facts. Recompute
        # only its explicit clarification slots before creating the revision;
        # otherwise a supplied budget/device remains permanently waiting.
        fact_keys = {str(item.get("key")) for item in facts if isinstance(item, dict)}
        if task.kind == "bundle_selection":
            goal["open_questions"] = [] if {"budget", "total_budget"}.intersection(fact_keys) else ["total_budget"]
        elif task.kind == "compatibility_diagnosis":
            goal["open_questions"] = [key for key in ("device", "symptom") if key not in fact_keys]
        goal["version"] = int(goal.get("version", 1)) + 1
        task.goal_json = goal
        task.goal_version += 1
        task.version += 1
        plan = revise_task_plan(session, task=task, reason="user_inputs")
        for artifact in session.scalars(select(ShoppingTaskArtifact).where(ShoppingTaskArtifact.task_id == task.id, ShoppingTaskArtifact.superseded.is_(False))).all():
            artifact.superseded = True
            artifact.verification_status = "superseded"
        task.status = "queued"
        # A waiting task must not retain its old scheduler lease after the
        # user has supplied facts; otherwise the next worker cannot reclaim it
        # until the unrelated lease timeout elapses.
        task.lease_token = None
        task.lease_until = None
        task.pending_interaction_json = None
        command = ShoppingTaskCommand(owner_id=identity.effective_user_id or "", task_id=task.id, operation=f"task:{task_id}:inputs", idempotency_key=idempotency_key, request_hash=_body_hash(command_body), result_json={"task_id": str(task_id), "status": task.status, "version": task.version})
        session.add(command)
        append_event(session, task, "task.inputs_received", {"version": task.version, "plan_revision": plan.revision})
        session.commit()
        return command.result_json
    except CommandConflict as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: UUID, body: ShoppingTaskCommandRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session)) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key required")
    identity = _identity(identity_boundary, body.user_id)
    task = get_task(session, owner_id=identity.effective_user_id or "", task_id=task_id, for_update=True)
    if task is None:
        raise _not_found()
    if task.version != body.expected_version:
        raise HTTPException(status_code=409, detail="task_version_conflict")
    command_body = body.model_dump(mode="json")
    try:
        replay = find_command(session, owner_id=identity.effective_user_id or "", operation=f"task:{task_id}:cancel", idempotency_key=idempotency_key, body=command_body)
        if replay is not None:
            return replay.result_json or {}
        task.cancel_requested = True
        task.version += 1
        refresh_task_status(session, task_id=task.id)
        result = {"task_id": str(task.id), "status": task.status, "version": task.version}
        session.add(ShoppingTaskCommand(owner_id=identity.effective_user_id or "", task_id=task.id, operation=f"task:{task_id}:cancel", idempotency_key=idempotency_key, request_hash=_body_hash(command_body), result_json=result))
        session.commit()
        return result
    except CommandConflict as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{task_id}/resume")
async def resume_task(task_id: UUID, body: ShoppingTaskCommandRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session)) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key required")
    identity = _identity(identity_boundary, body.user_id)
    task = get_task(session, owner_id=identity.effective_user_id or "", task_id=task_id, for_update=True)
    if task is None:
        raise _not_found()
    if task.version != body.expected_version:
        raise HTTPException(status_code=409, detail="task_version_conflict")
    if task.status in {"succeeded", "failed", "cancelled", "expired", "waiting_input"}:
        raise HTTPException(status_code=409, detail="task_not_resumable")
    command_body = body.model_dump(mode="json")
    try:
        replay = find_command(session, owner_id=identity.effective_user_id or "", operation=f"task:{task_id}:resume", idempotency_key=idempotency_key, body=command_body)
        if replay is not None:
            return replay.result_json or {}
    except CommandConflict as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if task.lease_until is not None and task.lease_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="task_worker_lease_active")
    task.status = "queued"
    task.lease_token = None
    task.lease_until = None
    task.version += 1
    append_event(session, task, "task.resumed", {"version": task.version})
    result = {"task_id": str(task.id), "status": task.status, "version": task.version}
    session.add(ShoppingTaskCommand(owner_id=identity.effective_user_id or "", task_id=task.id, operation=f"task:{task_id}:resume", idempotency_key=idempotency_key, request_hash=_body_hash(command_body), result_json=result))
    session.commit()
    return result


@router.get("/{task_id}/events")
async def task_events(task_id: UUID, after_sequence: int = Query(default=0, ge=0), user_id: str | None = Query(default=None), identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session)) -> StreamingResponse:
    identity = _identity(identity_boundary, user_id)
    task = get_task(session, owner_id=identity.effective_user_id or "", task_id=task_id)
    if task is None:
        raise _not_found()
    first_sequence = session.scalar(select(ShoppingTaskEvent.sequence).where(ShoppingTaskEvent.task_id == task.id).order_by(ShoppingTaskEvent.sequence.asc()).limit(1))
    if first_sequence is not None and after_sequence < int(first_sequence) - 1:
        raise HTTPException(status_code=410, detail="event_cursor_expired")
    events = list(session.scalars(select(ShoppingTaskEvent).where(ShoppingTaskEvent.task_id == task.id, ShoppingTaskEvent.sequence > after_sequence).order_by(ShoppingTaskEvent.sequence)).all())
    def stream():
        for event in events:
            payload = json.dumps({"type": event.event_type, **event.public_payload_json}, ensure_ascii=False)
            yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/{task_id}/actions")
async def prepare_task_action(task_id: UUID, body: ShoppingTaskActionRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session)) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key required")
    identity = _identity(identity_boundary, body.user_id)
    task = get_task(session, owner_id=identity.effective_user_id or "", task_id=task_id, for_update=True)
    if task is None:
        raise _not_found()
    if task.version != body.expected_version:
        raise HTTPException(status_code=409, detail="task_version_conflict")
    command_body = body.model_dump(mode="json")
    try:
        replay = find_command(session, owner_id=identity.effective_user_id or "", operation=f"task:{task_id}:action", idempotency_key=idempotency_key, body=command_body)
        if replay is not None:
            return replay.result_json or {}
    except CommandConflict as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = task.output_json or {}
    if task.kind == "bundle_selection" and body.action_type != "add_bundle_to_cart" or task.kind == "after_sales_assessment" and body.action_type != "save_after_sales_draft":
        raise HTTPException(status_code=400, detail="action_type_not_allowed")
    if task.status not in {"succeeded", "awaiting_approval"}:
        raise HTTPException(status_code=409, detail="task_result_not_ready")
    if task.kind == "bundle_selection" and (result.get("outcome") != "recommended" or not (result.get("bundle_proposal") or {}).get("options")):
        raise HTTPException(status_code=409, detail="bundle_not_verified")
    if task.kind == "bundle_selection":
        option = (result.get("bundle_proposal") or {}).get("options", [])[0]
        for item in option.get("items") or []:
            sku = session.scalar(select(CatalogSku).where(CatalogSku.id == UUID(item["sku_id"])))
            inventory = sku.inventory if sku is not None else None
            if sku is None or sku.sale_status != "active" or inventory is None or inventory.on_hand_quantity - inventory.reserved_quantity < int(item.get("quantity", 1)) or Decimal(str(sku.money_amount)) != Decimal(str(item["price"])):
                raise HTTPException(status_code=409, detail="catalog_changed_repreview_required")
    artifact = session.scalar(select(ShoppingTaskArtifact).where(ShoppingTaskArtifact.task_id == task.id, ShoppingTaskArtifact.kind == "task_result").order_by(ShoppingTaskArtifact.created_at.desc()))
    if artifact is None:
        raise HTTPException(status_code=409, detail="result_artifact_missing")
    action = session.scalar(select(ShoppingTaskAction).where(ShoppingTaskAction.task_id == task.id, ShoppingTaskAction.status == "pending").order_by(ShoppingTaskAction.action_version.desc()))
    if action is None:
        action = ShoppingTaskAction(task_id=task.id, artifact_id=artifact.id, action_type=body.action_type, goal_version=task.goal_version, plan_revision=task.active_plan_revision, action_version=1, payload_json=result, expires_at=datetime.now(timezone.utc) + timedelta(minutes=15))
        session.add(action)
    task.status = "awaiting_approval"
    task.version += 1
    append_event(session, task, "action.previewed", {"action_type": action.action_type, "action_version": action.action_version})
    result_view = {"action_id": str(action.id), "action_type": action.action_type, "status": action.status, "version": task.version, "expires_at": action.expires_at.isoformat(), "payload": action.payload_json}
    session.add(ShoppingTaskCommand(owner_id=identity.effective_user_id or "", task_id=task.id, operation=f"task:{task_id}:action", idempotency_key=idempotency_key, request_hash=_body_hash(command_body), result_json=result_view))
    session.commit()
    return result_view


@router.post("/{task_id}/actions/{action_id}/confirm")
async def confirm_task_action(task_id: UUID, action_id: UUID, body: ShoppingTaskConfirmRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), identity_boundary: IdentityBoundary = Depends(get_identity_boundary), session: Session = Depends(get_db_session)) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key required")
    identity = _identity(identity_boundary, body.user_id)
    try:
        result = confirm_task_action_service(
            session,
            owner_id=identity.effective_user_id or "",
            task_id=task_id,
            action_id=action_id,
            expected_version=body.expected_version,
            confirmed=body.confirmed,
            idempotency_key=idempotency_key,
        )
        session.commit()
        return result
    except ShoppingTaskActionError as exc:
        if exc.code == "action_expired":
            session.commit()
        else:
            session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
