"""Public Checkout Preview contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from app.schemas.recommendation import AvailabilityView, Money


CheckoutWarningCode = Literal[
    "cart_empty",
    "mixed_currency",
    "product_inactive",
    "sku_inactive",
    "inventory_missing",
    "out_of_stock",
    "insufficient_inventory",
]


class CheckoutPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckoutWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: CheckoutWarningCode
    cart_item_id: UUID | None = None
    sku_id: UUID | None = None
    message: StrictStr


class CheckoutPreviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cart_item_id: UUID
    sku_id: UUID
    product_name: StrictStr
    sku_name: StrictStr
    quantity: StrictInt = Field(ge=1, le=20)
    unit_money: Money
    subtotal_money: Money
    availability: AvailabilityView
    version: StrictInt = Field(ge=1)


class CheckoutPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CheckoutPreviewItem] = Field(default_factory=list)
    item_count: StrictInt = Field(default=0, ge=0)
    total_quantity: StrictInt = Field(default=0, ge=0)
    subtotal: Money | None = None
    currency: StrictStr | None = None
    warnings: list[CheckoutWarning] = Field(default_factory=list)
    can_create_order: StrictBool
    checkout_token: StrictStr | None = None
    expires_at: datetime | None = None
    revalidation_required: StrictBool = True


class CheckoutErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_quantity: StrictInt | None = Field(default=None, ge=0)
    requested_quantity: StrictInt | None = Field(default=None, ge=1)


CheckoutErrorCode = Literal["checkout_unavailable"]


class CheckoutErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CheckoutErrorCode
    message: StrictStr
    details: CheckoutErrorDetails = Field(default_factory=CheckoutErrorDetails)
