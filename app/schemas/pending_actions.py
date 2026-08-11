"""Strict public contracts for structured PendingAction and SKU Cart APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from app.cart.constants import MAX_CART_ITEM_QUANTITY
from app.schemas.cart import CartItemView, CartResponse
from app.schemas.recommendation import AvailabilityView, Money


PendingActionStatus = Literal["pending", "confirmed", "cancelled", "expired", "failed"]
PendingActionType = Literal["add_to_cart", "save_preference"]
RiskClass = Literal["low", "medium", "high"]
ActionErrorCode = Literal[
    "pending_action_not_found",
    "recommendation_not_found",
    "sku_not_in_recommendation",
    "invalid_quantity",
    "invalid_updated_fields",
    "version_conflict",
    "action_resolution_conflict",
    "action_expired",
    "catalog_not_found",
    "catalog_identity_changed",
    "product_inactive",
    "sku_inactive",
    "insufficient_inventory",
    "cart_quantity_limit",
    "unsupported_action_schema",
    "invalid_action_payload",
]


class RecommendationContextView(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_run_id: StrictStr = Field(min_length=1)


class IntegerEditableField(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_type: Literal["integer"] = "integer"
    field: Literal["quantity"]
    label: StrictStr
    current_value: StrictInt = Field(ge=1, le=MAX_CART_ITEM_QUANTITY)
    min_value: StrictInt = Field(default=1, ge=1)
    max_value: StrictInt = Field(default=MAX_CART_ITEM_QUANTITY, ge=1)
    required: StrictBool = True


class EnumEditableField(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_type: Literal["enum"] = "enum"
    field: Literal["preference_type"]
    label: StrictStr
    current_value: StrictStr
    options: list[StrictStr] = Field(min_length=1)
    required: StrictBool = True


class TextEditableField(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_type: Literal["text"] = "text"
    field: Literal["preference_value"]
    label: StrictStr
    current_value: StrictStr
    min_length: StrictInt = Field(default=1, ge=0)
    max_length: StrictInt = Field(default=2000, ge=1)
    required: StrictBool = True


EditableField = Annotated[Union[IntegerEditableField, EnumEditableField, TextEditableField], Field(discriminator="field_type")]


class AddToCartPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["catalog_sku", "legacy_product"]
    sku_id: UUID | None = None
    sku_code: StrictStr | None = None
    legacy_product_id: StrictStr | None = None
    product_id: UUID | None = None
    product_code: StrictStr | None = None
    product_name: StrictStr
    sku_name: StrictStr | None = None
    requested_quantity: StrictInt = Field(ge=1, le=MAX_CART_ITEM_QUANTITY)
    unit_money_snapshot: Money | None = None
    subtotal_money_snapshot: Money | None = None
    availability_snapshot: AvailabilityView | None = None
    preview_text: StrictStr | None = None

    @field_validator("sku_code", "legacy_product_id", "product_code")
    @classmethod
    def non_blank_optional(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("identifier cannot be blank")
        return value


class PendingActionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    pending_action_id: StrictStr
    action_type: PendingActionType
    risk_class: RiskClass
    status: PendingActionStatus
    version: StrictInt = Field(ge=1)
    expires_at: datetime | None
    preview: AddToCartPreview | str | None = None
    editable_fields: list[EditableField] = Field(default_factory=list)
    confirm_label: StrictStr = "Confirm"
    cancel_label: StrictStr = "Cancel"


class AddToCartPendingActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: StrictStr | None = None
    thread_id: StrictStr = Field(min_length=1)
    source_run_id: StrictStr = Field(min_length=1)
    sku_id: UUID
    quantity: StrictInt = Field(default=1, ge=1, le=MAX_CART_ITEM_QUANTITY)


class QuantityEditFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: StrictInt | None = Field(default=None, ge=1, le=MAX_CART_ITEM_QUANTITY)


class PendingActionTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: StrictStr | None = None
    thread_id: StrictStr = Field(min_length=1)
    expected_version: StrictInt = Field(ge=1)
    updated_fields: QuantityEditFields | None = None


class PendingActionCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: StrictStr | None = None
    thread_id: StrictStr = Field(min_length=1)
    expected_version: StrictInt = Field(ge=1)


class PendingActionTransitionResponse(BaseModel):
    pending_action: PendingActionView
    cart_item: CartItemView | None = None
    price_changed: StrictBool = False
    snapshot_money: Money | None = None
    current_money: Money | None = None
    requested_quantity: StrictInt | None = Field(default=None, ge=1, le=MAX_CART_ITEM_QUANTITY)
    cart_quantity: StrictInt | None = Field(default=None, ge=1, le=MAX_CART_ITEM_QUANTITY)
    idempotent_replay: StrictBool = False


class PendingActionErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_quantity: StrictInt | None = Field(default=None, ge=0)
    current_quantity: StrictInt | None = Field(default=None, ge=0)
    max_quantity: StrictInt | None = Field(default=None, ge=1)
    current_version: StrictInt | None = Field(default=None, ge=1)
    action_status: PendingActionStatus | None = None


class ActionErrorResponse(BaseModel):
    code: ActionErrorCode
    message: StrictStr
    details: PendingActionErrorDetails = Field(default_factory=PendingActionErrorDetails)
    idempotent_replay: StrictBool = False


class PendingActionResolutionRecord(BaseModel):
    """Versioned internal terminal record used for deterministic replay."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["shopmind.pending_action.resolution.v1"]
    transition: Literal["confirm", "cancel", "expire"]
    request_hash: StrictStr | None
    http_status: StrictInt = Field(ge=200, le=599)
    response_kind: Literal["success", "error"]
    pending_action: PendingActionView
    cart_item: CartItemView | None = None
    price_changed: StrictBool = False
    snapshot_money: Money | None = None
    current_money: Money | None = None
    requested_quantity: StrictInt | None = Field(default=None, ge=1, le=MAX_CART_ITEM_QUANTITY)
    cart_quantity: StrictInt | None = Field(default=None, ge=1, le=MAX_CART_ITEM_QUANTITY)
    error: ActionErrorResponse | None = None
    resolved_at: datetime
