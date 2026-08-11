"""Small shared response helpers for new structured service endpoints."""

from fastapi.responses import JSONResponse

from app.schemas.pending_actions import ActionErrorResponse
from app.schemas.cart import CartErrorResponse
from app.schemas.checkout import CheckoutErrorResponse
from app.schemas.orders import OrderErrorResponse
from app.schemas.payments import PaymentErrorResponse
from app.services.checkout import CheckoutServiceError
from app.services.cart import CartServiceError
from app.services.orders import OrderServiceError
from app.services.payments import PaymentServiceError
from app.services.pending_actions import PendingActionServiceError


def service_error_response(error: PendingActionServiceError) -> JSONResponse:
    response = ActionErrorResponse(
        code=error.code,
        message=error.message,
        details=error.details,
        idempotent_replay=error.idempotent_replay,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=response.model_dump(mode="json"),
    )


def cart_service_error_response(error: CartServiceError) -> JSONResponse:
    response = CartErrorResponse(
        code=error.code,
        message=error.message,
        details=error.details,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=response.model_dump(mode="json"),
    )


def checkout_service_error_response(error: CheckoutServiceError) -> JSONResponse:
    response = CheckoutErrorResponse(
        code=error.code,
        message=error.message,
        details=error.details,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=response.model_dump(mode="json"),
    )


def order_service_error_response(error: OrderServiceError) -> JSONResponse:
    response = OrderErrorResponse(
        code=error.code,
        message=error.message,
        details=error.details,
        idempotent_replay=error.idempotent_replay,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=response.model_dump(mode="json"),
    )


def payment_service_error_response(error: PaymentServiceError) -> JSONResponse:
    response = PaymentErrorResponse(
        code=error.code,
        message=error.message,
        details=error.details,
        idempotent_replay=error.idempotent_replay,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=response.model_dump(mode="json"),
    )
