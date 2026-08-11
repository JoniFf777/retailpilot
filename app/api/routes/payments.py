"""Phase 5A Mock Payment Attempt endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.routes._helpers import payment_service_error_response
from app.core.logging import log_event
from app.db.session import get_db_session
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.payments.providers import (
    MockPaymentProvider,
    PaymentProvider,
    ProviderOutcome,
)
from app.schemas.payments import (
    PaymentAttemptListResponse,
    PaymentAttemptRequest,
    PaymentAttemptResponse,
    PaymentErrorResponse,
)
from app.security import IdentityBoundary
from app.services.payments import (
    PaymentServiceError,
    claim_payment_attempt,
    finalize_payment,
    list_user_payment_attempts,
    payment_response,
    persist_provider_outcome,
    resolve_provider_outcome,
)


router = APIRouter()

# The Mock Provider is process-scoped so its provider idempotency operation
# table survives the separate HTTP requests that claim and reconcile one
# PaymentAttempt. Tests may replace this object through monkeypatching while
# FastAPI dependency overrides remain available for other provider tests.
_default_payment_provider = MockPaymentProvider()


def get_payment_provider() -> PaymentProvider:
    """Return the server-owned process-scoped Mock Provider."""

    return _default_payment_provider


PAYMENT_ERROR_RESPONSES = {
    402: {"model": PaymentErrorResponse},
    404: {"model": PaymentErrorResponse},
    409: {"model": PaymentErrorResponse},
    503: {"model": PaymentErrorResponse},
}
PAYMENT_422_RESPONSE = {
    "description": "Request validation or typed payment-domain error.",
    "content": {
        "application/json": {
            "schema": {
                "oneOf": [
                    {"$ref": "#/components/schemas/HTTPValidationError"},
                    {"$ref": "#/components/schemas/PaymentErrorResponse"},
                ]
            }
        }
    },
}


def _payment_status_response(
    response: PaymentAttemptResponse, *, status_code: int
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )


def _provider_unavailable_outcome() -> ProviderOutcome:
    return ProviderOutcome(
        status="unknown",
        provider_payment_id=None,
        failure_code="payment_provider_unavailable",
        result_at=datetime.now(timezone.utc),
    )


@router.post(
    "/orders/{order_id}/payments",
    response_model=PaymentAttemptResponse,
    responses={
        **PAYMENT_ERROR_RESPONSES,
        202: {"model": PaymentAttemptResponse},
        422: PAYMENT_422_RESPONSE,
    },
)
async def create_payment_endpoint(
    order_id: UUID,
    request: PaymentAttemptRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    session: Session = Depends(get_db_session),
) -> PaymentAttemptResponse | Response:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    effective_user_id = identity.effective_user_id or ""
    claim = None
    log_event(
        "payment.claim.started",
        order_id=order_id,
        action="claim",
        status="started",
    )
    try:
        claim = claim_payment_attempt(
            session,
            user_id=effective_user_id,
            order_id=order_id,
            idempotency_key=idempotency_key,
            request=request,
        )
        # The claim is committed before any Provider call.
        session.commit()
        log_event(
            "payment.claimed",
            order_id=claim.order_id,
            payment_attempt_id=claim.attempt_id,
            action=claim.action,
            status="replayed" if claim.idempotent_replay else "processing",
        )

        if claim.action == "replay_failed":
            raise PaymentServiceError(
                "payment_declined",
                "The Payment Provider declined the payment.",
                status_code=402,
                details={"reason": claim.failure_code or "payment_declined"},
                idempotent_replay=True,
            )
        if claim.action == "replay_succeeded":
            return payment_response(
                session,
                user_id=effective_user_id,
                order_id=order_id,
                attempt_id=claim.attempt_id,
                idempotent_replay=True,
            )
        if claim.action == "finalize":
            finalize_payment(
                session,
                user_id=effective_user_id,
                order_id=order_id,
                attempt_id=claim.attempt_id,
            )
            session.commit()
            log_event(
                "payment.finalization.succeeded",
                order_id=claim.order_id,
                payment_attempt_id=claim.attempt_id,
                action="finalize",
                status="replayed",
            )
            return payment_response(
                session,
                user_id=effective_user_id,
                order_id=order_id,
                attempt_id=claim.attempt_id,
                idempotent_replay=True,
            )

        try:
            outcome = resolve_provider_outcome(
                payment_provider,
                claim=claim,
                request=request,
            )
        except Exception:
            outcome = _provider_unavailable_outcome()

        if outcome.status == "not_found":
            outcome = ProviderOutcome(
                status="unknown",
                provider_payment_id=None,
                failure_code="provider_not_found",
                result_at=datetime.now(timezone.utc),
            )
        persist_provider_outcome(
            session,
            attempt_id=claim.attempt_id,
            outcome=outcome,
        )
        # Provider result persistence is committed before local finalization.
        session.commit()
        log_event(
            "payment.provider_outcome",
            order_id=claim.order_id,
            payment_attempt_id=claim.attempt_id,
            action=claim.action,
            status=outcome.status,
        )

        if outcome.status == "declined":
            raise PaymentServiceError(
                "payment_declined",
                "The Payment Provider declined the payment.",
                status_code=402,
                details={"reason": outcome.failure_code or "payment_declined"},
                idempotent_replay=claim.idempotent_replay,
            )
        if outcome.status == "unknown":
            response = payment_response(
                session,
                user_id=effective_user_id,
                order_id=order_id,
                attempt_id=claim.attempt_id,
                idempotent_replay=claim.idempotent_replay,
            )
            if outcome.failure_code == "payment_provider_unavailable":
                raise PaymentServiceError(
                    "payment_provider_unavailable",
                    "The Payment Provider is temporarily unavailable.",
                    status_code=503,
                    idempotent_replay=claim.idempotent_replay,
                )
            return _payment_status_response(response, status_code=202)

        finalize_payment(
            session,
            user_id=effective_user_id,
            order_id=order_id,
            attempt_id=claim.attempt_id,
        )
        session.commit()
        log_event(
            "payment.finalization.succeeded",
            order_id=claim.order_id,
            payment_attempt_id=claim.attempt_id,
            action="finalize",
            status="succeeded",
        )
        return payment_response(
            session,
            user_id=effective_user_id,
            order_id=order_id,
            attempt_id=claim.attempt_id,
            idempotent_replay=claim.idempotent_replay,
        )
    except PaymentServiceError as exc:
        session.rollback()
        if exc.code == "payment_finalization_pending":
            log_event(
                "payment.finalization.pending_or_failed",
                order_id=claim.order_id if claim is not None else order_id,
                payment_attempt_id=claim.attempt_id if claim is not None else None,
                action="finalize",
                status=exc.status_code,
                error_code=exc.code,
            )
        return payment_service_error_response(exc)
    except Exception as exc:
        session.rollback()
        log_event(
            "payment.finalization.pending_or_failed",
            order_id=claim.order_id if claim is not None else order_id,
            payment_attempt_id=claim.attempt_id if claim is not None else None,
            action="payment",
            status=500,
            error_code="unexpected_payment_error",
            error_class=type(exc).__name__,
            error_message="Unexpected Payment service failure.",
        )
        raise


@router.get(
    "/orders/{order_id}/payments",
    response_model=PaymentAttemptListResponse,
    responses={
        404: {"model": PaymentErrorResponse},
        422: {
            "description": "Request validation.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
                }
            },
        },
    },
)
async def list_payments_endpoint(
    order_id: UUID,
    user_id: str | None = Query(default=None),
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    session: Session = Depends(get_db_session),
) -> PaymentAttemptListResponse | Response:
    identity = bind_request_user(identity_boundary, user_id, require_user=True)
    try:
        return PaymentAttemptListResponse(
            items=list_user_payment_attempts(
                session,
                user_id=identity.effective_user_id or "",
                order_id=order_id,
            )
        )
    except PaymentServiceError as exc:
        return payment_service_error_response(exc)


__all__ = ["get_payment_provider", "router"]
