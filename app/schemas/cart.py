"""Public contracts for direct ShopMind Cart management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.cart.constants import MAX_CART_ITEM_QUANTITY
from app.schemas.recommendation import AvailabilityView, Money


CartWarningCode = Literal[
    "mixed_currency",
    "product_inactive",
    "sku_inactive",
    "out_of_stock",
    "insufficient_inventory",
    "inventory_missing",
]

CartErrorCode = Literal[
    "cart_item_not_found",
    "cart_version_conflict",
    "invalid_quantity",
    "cart_quantity_limit",
    "insufficient_inventory",
    "product_inactive",
    "sku_inactive",
    "catalog_not_found",
    "inventory_missing",
]


class CartWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: CartWarningCode
    cart_item_id: UUID | None = None
    sku_id: UUID | None = None
    message: StrictStr


class CartItemView(BaseModel):
    model_config = ConfigDict(frozen=True)

    cart_item_id: UUID
    sku_id: UUID
    sku_code: StrictStr
    product_id: UUID
    product_code: StrictStr
    product_name: StrictStr
    sku_name: StrictStr
    quantity: StrictInt = Field(ge=1, le=MAX_CART_ITEM_QUANTITY)
    unit_money: Money
    subtotal_money: Money
    product_sale_status: Literal["draft", "active", "inactive"]
    sku_sale_status: Literal["draft", "active", "inactive"]
    effective_sale_status: Literal["draft", "active", "inactive"]
    availability: AvailabilityView
    created_at: datetime
    updated_at: datetime
    version: StrictInt = Field(ge=1)


class CartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CartItemView] = Field(default_factory=list)
    item_count: StrictInt = Field(default=0, ge=0)
    total_quantity: StrictInt = Field(default=0, ge=0)
    subtotal: Money | None = None
    currency: StrictStr | None = None
    warnings: list[CartWarning] = Field(default_factory=list)


class UpdateCartItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: StrictInt = Field(ge=1)
    # Values above the Cart limit stay in the typed domain-error path so
    # clients receive ``cart_quantity_limit`` rather than an unstructured 422.
    quantity: StrictInt = Field(ge=1)


class CartMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: CartItemView
    cart: CartResponse


class CartErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_quantity: StrictInt | None = Field(default=None, ge=0)
    current_quantity: StrictInt | None = Field(default=None, ge=0)
    requested_quantity: StrictInt | None = Field(default=None, ge=1)
    max_quantity: StrictInt | None = Field(default=None, ge=1)
    current_version: StrictInt | None = Field(default=None, ge=1)


class CartErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CartErrorCode
    message: StrictStr
    details: CartErrorDetails = Field(default_factory=CartErrorDetails)
