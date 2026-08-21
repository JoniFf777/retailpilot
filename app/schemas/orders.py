"""Public Order API contracts; internal idempotency and owner facts stay private."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from app.schemas.recommendation import Money


OrderStatus = Literal["pending_payment", "cancelled", "paid", "expired"]


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkout_token: StrictStr = Field(min_length=1, max_length=65_536)


class OrderItemView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: UUID
    sku_id: UUID
    product_code: StrictStr
    product_name: StrictStr
    sku_code: StrictStr
    sku_name: StrictStr
    unit_money: Money
    quantity: StrictInt = Field(ge=1, le=20)
    subtotal_money: Money


class OrderView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    order_id: UUID
    status: OrderStatus
    currency: StrictStr
    subtotal: Money
    total: Money
    items: list[OrderItemView]
    version: StrictInt = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class CreateOrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: OrderView
    idempotent_replay: StrictBool


class CancelOrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: OrderView
    idempotent_replay: StrictBool


class OrderListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderView]
    next_cursor: StrictStr | None = None


OrderErrorCode = Literal[
    "checkout_invalid",
    "checkout_expired",
    "checkout_unavailable",
    "cart_changed",
    "mixed_currency",
    "product_inactive",
    "sku_inactive",
    "inventory_missing",
    "insufficient_inventory",
    "price_changed",
    "idempotency_conflict",
    "order_not_found",
    "reservation_inconsistent",
    "order_not_cancellable",
    "payment_in_progress",
    "payment_state_inconsistent",
    "order_expired",
    "idempotency_key_invalid",
    "cursor_invalid",
]


class OrderErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_quantity: StrictInt | None = Field(default=None, ge=0)
    requested_quantity: StrictInt | None = Field(default=None, ge=1)
    reservation_count: StrictInt | None = Field(default=None, ge=0)
    reason: StrictStr | None = None


class OrderErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: OrderErrorCode
    message: StrictStr
    details: OrderErrorDetails = Field(default_factory=OrderErrorDetails)
    idempotent_replay: StrictBool = False
