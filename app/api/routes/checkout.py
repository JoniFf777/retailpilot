"""Checkout Preview endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.routes._helpers import checkout_service_error_response
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.schemas.checkout import CheckoutErrorResponse, CheckoutPreview, CheckoutPreviewRequest
from app.security import IdentityBoundary
from app.services.checkout import CheckoutServiceError, preview_checkout


router = APIRouter()


@router.post(
    "/checkout/preview",
    response_model=CheckoutPreview,
    responses={503: {"model": CheckoutErrorResponse}},
)
async def create_checkout_preview(
    request: CheckoutPreviewRequest,
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> CheckoutPreview | Response:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    try:
        return preview_checkout(
            session,
            user_id=identity.effective_user_id or "",
            settings=get_settings(),
        )
    except CheckoutServiceError as exc:
        return checkout_service_error_response(exc)
    except Exception:
        session.rollback()
        raise
