"""Phase 4A Order endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.routes._helpers import order_service_error_response
from app.core.logging import log_event
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.schemas.orders import (
    CancelOrderResponse,
    CreateOrderRequest,
    CreateOrderResponse,
    OrderErrorResponse,
    OrderListResponse,
    OrderView,
)
from app.security import IdentityBoundary
from app.services.orders import (
    OrderServiceError,
    cancel_order,
    create_order,
    get_user_order,
    list_user_orders,
)


router = APIRouter()
ORDER_ERROR_RESPONSES = {
    404: {"model": OrderErrorResponse},
    409: {"model": OrderErrorResponse},
    410: {"model": OrderErrorResponse},
    503: {"model": OrderErrorResponse},
}
ORDER_422_RESPONSE = {
    "description": "Request validation or typed request-domain error.",
    "content": {
        "application/json": {
            "schema": {
                "oneOf": [
                    {"$ref": "#/components/schemas/HTTPValidationError"},
                    {"$ref": "#/components/schemas/OrderErrorResponse"},
                ]
            }
        }
    },
}


@router.post(
    "/orders",
    response_model=CreateOrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**ORDER_ERROR_RESPONSES, 422: ORDER_422_RESPONSE},
)
async def create_order_endpoint(
    request: CreateOrderRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> CreateOrderResponse | Response:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    log_event("order.create.started", action="create", status="started")
    try:
        result = create_order(
            session,
            user_id=identity.effective_user_id or "",
            idempotency_key=idempotency_key,
            request=request,
            settings=get_settings(),
        )
        session.commit()
        log_event(
            "order.create.succeeded",
            order_id=result.order.order_id,
            action="create",
            status="pending_payment",
        )
        return result
    except OrderServiceError as exc:
        session.rollback()
        log_event(
            "order.create.failed",
            action="create",
            status=exc.status_code,
            error_code=exc.code,
        )
        return order_service_error_response(exc)
    except Exception as exc:
        session.rollback()
        log_event(
            "order.create.failed",
            action="create",
            status=500,
            error_code="unexpected_order_error",
            error_class=type(exc).__name__,
            error_message="Unexpected Order service failure.",
        )
        raise


@router.get("/orders", response_model=OrderListResponse, responses={422: ORDER_422_RESPONSE})
async def list_orders_endpoint(
    user_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> OrderListResponse | Response:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    try:
        return list_user_orders(
            session,
            user_id=identity.effective_user_id or "",
            limit=limit,
            cursor=cursor,
        )
    except OrderServiceError as exc:
        return order_service_error_response(exc)


@router.post(
    "/orders/{order_id}/cancel",
    response_model=CancelOrderResponse,
    responses=ORDER_ERROR_RESPONSES,
)
async def cancel_order_endpoint(
    order_id: UUID,
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> CancelOrderResponse | Response:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    log_event(
        "order.cancel.started",
        order_id=order_id,
        action="cancel",
        status="started",
    )
    try:
        result = cancel_order(
            session,
            user_id=identity.effective_user_id or "",
            order_id=order_id,
        )
        session.commit()
        log_event(
            "order.cancel.succeeded",
            order_id=order_id,
            action="cancel",
            status=result.order.status,
        )
        return result
    except OrderServiceError as exc:
        session.rollback()
        log_event(
            "order.cancel.failed",
            order_id=order_id,
            action="cancel",
            status=exc.status_code,
            error_code=exc.code,
        )
        return order_service_error_response(exc)
    except Exception as exc:
        session.rollback()
        log_event(
            "order.cancel.failed",
            order_id=order_id,
            action="cancel",
            status=500,
            error_code="unexpected_order_error",
            error_class=type(exc).__name__,
            error_message="Unexpected Order service failure.",
        )
        raise


@router.get(
    "/orders/{order_id}",
    response_model=OrderView,
    responses={404: {"model": OrderErrorResponse}},
)
async def get_order_endpoint(
    order_id: UUID,
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> OrderView | Response:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    try:
        return get_user_order(
            session,
            user_id=identity.effective_user_id or "",
            order_id=order_id,
        )
    except OrderServiceError as exc:
        return order_service_error_response(exc)
