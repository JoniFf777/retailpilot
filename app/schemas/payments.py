"""Public contracts for Phase 5A Mock Payment Attempts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from app.schemas.orders import OrderView
from app.schemas.recommendation import Money


PaymentAttemptStatus = Literal[
    "processing",
    "unknown",
    "provider_succeeded",
    "failed",
    "succeeded",
]


class PaymentAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["mock"] = "mock"
    payment_method_ref: StrictStr = Field(min_length=1, max_length=128)


class PaymentAttemptView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: UUID
    order_id: UUID
    provider: Literal["mock"]
    status: PaymentAttemptStatus
    amount: Money
    failure_code: StrictStr | None = None
    provider_result_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class PaymentAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_attempt: PaymentAttemptView
    order: OrderView
    idempotent_replay: StrictBool = False


class PaymentAttemptListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PaymentAttemptView]


PaymentErrorCode = Literal[
    "idempotency_key_invalid",
    "idempotency_conflict",
    "order_not_found",
    "order_not_payable",
    "order_already_paid",
    "payment_in_progress",
    "payment_declined",
    "payment_provider_unavailable",
    "payment_finalization_pending",
]


class PaymentErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: StrictStr | None = None


class PaymentErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: PaymentErrorCode
    message: StrictStr
    details: PaymentErrorDetails = Field(default_factory=PaymentErrorDetails)
    idempotent_replay: StrictBool = False
