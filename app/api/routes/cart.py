"""Direct SKU Cart management endpoints for Phase 3A."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.routes._helpers import cart_service_error_response
from app.db.session import get_db_session
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.schemas.cart import (
    CartErrorResponse,
    CartMutationResponse,
    CartResponse,
    UpdateCartItemRequest,
)
from app.security import IdentityBoundary
from app.services.cart import (
    CartServiceError,
    clear_user_cart,
    delete_cart_item_by_id,
    get_cart,
    update_cart_item,
)


router = APIRouter()
CART_ERROR_RESPONSES = {
    404: {"model": CartErrorResponse},
    409: {"model": CartErrorResponse},
}


@router.get("/cart", response_model=CartResponse)
async def read_cart(
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> CartResponse:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    return get_cart(session, user_id=identity.effective_user_id or "")


@router.patch(
    "/cart/items/{cart_item_id}",
    response_model=CartMutationResponse,
    responses=CART_ERROR_RESPONSES,
)
async def patch_cart_item(
    cart_item_id: UUID,
    request: UpdateCartItemRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> CartMutationResponse | Response:
    identity = bind_request_user(identity_boundary, None, require_user=True)
    try:
        result = update_cart_item(
            session,
            user_id=identity.effective_user_id or "",
            cart_item_id=cart_item_id,
            expected_version=request.expected_version,
            quantity=request.quantity,
        )
        session.commit()
        return result
    except CartServiceError as exc:
        session.rollback()
        return cart_service_error_response(exc)
    except Exception:
        session.rollback()
        raise


@router.delete(
    "/cart/items/{cart_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_cart_item(
    cart_item_id: UUID,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> Response:
    identity = bind_request_user(identity_boundary, None, require_user=True)
    try:
        delete_cart_item_by_id(
            session,
            user_id=identity.effective_user_id or "",
            cart_item_id=cart_item_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/cart", status_code=status.HTTP_204_NO_CONTENT)
async def remove_all_cart_items(
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> Response:
    identity = bind_request_user(identity_boundary, None, require_user=True)
    try:
        clear_user_cart(session, user_id=identity.effective_user_id or "")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
