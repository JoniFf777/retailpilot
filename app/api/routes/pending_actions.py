"""Dedicated structured PendingAction endpoints for Catalog SKU add-to-cart."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.routes._helpers import service_error_response
from app.db.session import get_db_session
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.schemas.pending_actions import (
    AddToCartPendingActionRequest,
    ActionErrorResponse,
    PendingActionCancelRequest,
    PendingActionTransitionRequest,
    PendingActionTransitionResponse,
    PendingActionView,
)
from app.security import AuditRequestOperation, IdentityBoundary
from app.services.pending_actions import (
    PendingActionServiceError,
    cancel_pending_action,
    confirm_add_to_cart,
    create_add_to_cart_pending_action,
    get_pending_action_view,
)


router = APIRouter()
ACTION_ERROR_RESPONSES = {
    404: {"model": ActionErrorResponse},
    409: {"model": ActionErrorResponse},
    410: {"model": ActionErrorResponse},
}


@router.post(
    "/pending-actions/add-to-cart",
    response_model=PendingActionView,
    status_code=status.HTTP_201_CREATED,
    responses=ACTION_ERROR_RESPONSES,
)
async def create_pending_action(
    request: AddToCartPendingActionRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
):
    identity = bind_request_user(
        identity_boundary,
        request.user_id,
        require_user=True,
        request_operation=AuditRequestOperation.CONFIRM_PENDING_ACTION,
    )
    try:
        view = create_add_to_cart_pending_action(
            session,
            user_id=identity.effective_user_id or "",
            thread_id=request.thread_id,
            source_run_id=request.source_run_id,
            sku_id=request.sku_id,
            quantity=request.quantity,
        )
        session.commit()
        return view
    except PendingActionServiceError as exc:
        session.rollback()
        return service_error_response(exc)
    except Exception:
        session.rollback()
        raise


@router.get(
    "/pending-actions/{pending_action_id}",
    response_model=PendingActionView,
    responses=ACTION_ERROR_RESPONSES,
)
async def read_pending_action(
    pending_action_id: str,
    thread_id: str = Query(..., min_length=1),
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
):
    identity = bind_request_user(
        identity_boundary,
        user_id,
        require_user=True,
        request_operation=AuditRequestOperation.CONFIRM_PENDING_ACTION,
    )
    try:
        view = get_pending_action_view(
            session,
            pending_action_id=pending_action_id,
            user_id=identity.effective_user_id or "",
            thread_id=thread_id,
        )
        session.commit()
        return view
    except PendingActionServiceError as exc:
        session.rollback()
        return service_error_response(exc)


@router.post(
    "/pending-actions/{pending_action_id}/confirm",
    response_model=PendingActionTransitionResponse,
    responses=ACTION_ERROR_RESPONSES,
)
async def confirm_pending_action_endpoint(
    pending_action_id: str,
    request: PendingActionTransitionRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
):
    identity = bind_request_user(
        identity_boundary,
        request.user_id,
        require_user=True,
        request_operation=AuditRequestOperation.CONFIRM_PENDING_ACTION,
    )
    try:
        result = confirm_add_to_cart(
            session,
            pending_action_id=pending_action_id,
            user_id=identity.effective_user_id or "",
            thread_id=request.thread_id,
            expected_version=request.expected_version,
            updated_fields=request.updated_fields,
        )
        session.commit()
        return result
    except PendingActionServiceError as exc:
        if exc.persisted_terminal:
            session.commit()
        else:
            session.rollback()
        return service_error_response(exc)
    except Exception:
        session.rollback()
        raise


@router.post(
    "/pending-actions/{pending_action_id}/cancel",
    response_model=PendingActionTransitionResponse,
    responses=ACTION_ERROR_RESPONSES,
)
async def cancel_pending_action_endpoint(
    pending_action_id: str,
    request: PendingActionCancelRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
):
    identity = bind_request_user(
        identity_boundary,
        request.user_id,
        require_user=True,
        request_operation=AuditRequestOperation.CONFIRM_PENDING_ACTION,
    )
    try:
        result = cancel_pending_action(
            session,
            pending_action_id=pending_action_id,
            user_id=identity.effective_user_id or "",
            thread_id=request.thread_id,
            expected_version=request.expected_version,
        )
        session.commit()
        return result
    except PendingActionServiceError as exc:
        if exc.persisted_terminal:
            session.commit()
        else:
            session.rollback()
        return service_error_response(exc)
    except Exception:
        session.rollback()
        raise
