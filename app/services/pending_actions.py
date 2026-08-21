"""Transactional structured PendingAction lifecycle for SKU add-to-cart."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cart.constants import MAX_CART_ITEM_QUANTITY
from app.catalog.models import CatalogInventory, CatalogProduct, CatalogSku
from app.db.models import PendingAction, Product
from app.repositories import preferences as preference_repository
from app.repositories.runtime_runs import get_owned_recommendation_run
from app.repositories.catalog import resolve_catalog_identifier
from app.repositories.shopmind_cart import get_cart_item_for_update, get_cart_item_view, upsert_cart_item
from app.schemas.pending_actions import (
    ActionErrorResponse,
    AddToCartPreview,
    CartItemView,
    CartActionOutcome,
    EnumEditableField,
    IntegerEditableField,
    PendingActionErrorDetails,
    PendingActionResolutionRecord,
    PendingActionTransitionResponse,
    PendingActionView,
    SavePreferenceActionPayload,
    TextEditableField,
)
from app.schemas.recommendation import AvailabilityView, Money


PENDING_ACTION_SCHEMA_VERSION = "shopmind.pending_action.add_to_cart.v1"
PREFERENCE_ACTION_SCHEMA_VERSION = "shopmind.pending_action.save_preference.v1"
PREFERENCE_ACTION_OPERATION = "add"
LEGACY_ACTION_SCHEMA_VERSION = "legacy.pending_action.v1"
RESOLUTION_SCHEMA_VERSION = "shopmind.pending_action.resolution.v1"
DEFAULT_PENDING_ACTION_TTL = timedelta(minutes=30)


class PendingActionServiceError(Exception):
    """Stable public error with optional persisted terminal resolution."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        details: dict[str, Any] | PendingActionErrorDetails | None = None,
        persisted_terminal: bool = False,
        resolution_record: PendingActionResolutionRecord | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = (
            details
            if isinstance(details, PendingActionErrorDetails)
            else PendingActionErrorDetails.model_validate(details or {})
        )
        self.persisted_terminal = persisted_terminal
        self.resolution_record = resolution_record

    @property
    def idempotent_replay(self) -> bool:
        return bool(self.resolution_record and self.resolution_record.error and self.resolution_record.error.idempotent_replay)

    @classmethod
    def from_record(cls, record: PendingActionResolutionRecord, *, replay: bool) -> "PendingActionServiceError":
        if record.error is None:
            raise ValueError("resolution record has no error")
        error = record.error.model_copy(update={"idempotent_replay": replay})
        return cls(
            error.code,
            error.message,
            status_code=record.http_status,
            details=error.details,
            persisted_terminal=True,
            resolution_record=record.model_copy(update={"error": error}),
        )


def create_add_to_cart_pending_action(
    session: Session,
    *,
    user_id: str,
    thread_id: str,
    source_run_id: str,
    sku_id: UUID,
    quantity: int,
) -> PendingActionView:
    _validate_quantity(quantity)
    owned = get_owned_recommendation_run(session, run_id=source_run_id, user_id=user_id, thread_id=thread_id)
    if owned is None:
        raise PendingActionServiceError("recommendation_not_found", "Recommendation context was not found.", status_code=404)
    recommendation = owned["recommendation"]
    candidate = next((item for item in recommendation.recommendations if item.sku_id == sku_id), None)
    if candidate is None:
        for item in recommendation.recommendations:
            alternative = next((alt for alt in item.alternative_skus if alt.sku_id == sku_id), None)
            if alternative is not None:
                candidate = type("RecommendationCandidate", (), {"product_id": item.product_id, "sku_id": alternative.sku_id, "product_name": item.product_name, "sku_name": alternative.sku_name})()
                break
    if candidate is None:
        raise PendingActionServiceError("sku_not_in_recommendation", "SKU is not part of the recommendation.", status_code=404)
    product, sku, inventory = _load_catalog(session, sku_id)
    if product is None or sku is None or product.id != candidate.product_id:
        raise PendingActionServiceError("sku_not_in_recommendation", "SKU is not part of the recommendation.", status_code=404)
    _require_sellable(product, sku, inventory)
    available = _available(inventory)
    if quantity > available:
        raise PendingActionServiceError("insufficient_inventory", "Requested quantity is not currently available.", details={"available_quantity": available})
    return _create_catalog_pending_action(
        session,
        user_id=user_id,
        thread_id=thread_id,
        product=product,
        sku=sku,
        inventory=inventory,
        quantity=quantity,
        source_run_id=source_run_id,
        source_recommendation_schema_version=recommendation.schema_version,
    )


def prepare_save_preference_pending_action(
    session: Session,
    *,
    user_id: str,
    thread_id: str | None,
    preference_type: str,
    preference_value: str,
) -> PendingActionView:
    """Prepare an append-only preference action without writing UserPreference."""

    if not user_id.strip():
        raise PendingActionServiceError("invalid_action_payload", "Preference owner is required.")
    if not preference_value.strip():
        raise PendingActionServiceError("invalid_action_payload", "Preference value is required.")
    normalized_type, _was_invalid = preference_repository._normalize_preference_type(
        preference_type
    )
    payload = SavePreferenceActionPayload.model_validate(
        {
            "schema_version": PREFERENCE_ACTION_SCHEMA_VERSION,
            "operation": PREFERENCE_ACTION_OPERATION,
            "preference_type": normalized_type,
            "preference_value": preference_value.strip(),
        }
    )
    now = _now()
    action = PendingAction(
        id=str(uuid4()),
        user_id=user_id.strip(),
        thread_id=thread_id,
        action_type="save_preference",
        payload_json=payload.model_dump(mode="json"),
        risk_class="medium",
        preview_text=f"Save {payload.preference_type} preference: {payload.preference_value}",
        status="pending",
        version=1,
        result_json={},
        metadata_json={
            "schema_version": PREFERENCE_ACTION_SCHEMA_VERSION,
            "operation": PREFERENCE_ACTION_OPERATION,
        },
        expires_at=now + DEFAULT_PENDING_ACTION_TTL,
        created_at=now,
        updated_at=now,
    )
    session.add(action)
    session.flush()
    return pending_action_to_view(session, action)


def prepare_legacy_add_to_cart(
    session: Session,
    *,
    user_id: str,
    thread_id: str | None,
    identifier: str,
    quantity: int,
) -> CartActionOutcome:
    """Resolve legacy intent and prepare only a canonical SKU PendingAction."""

    _validate_quantity(quantity)
    resolution = resolve_catalog_identifier(session, identifier)
    if resolution.status != "resolved" or resolution.sku_id is None:
        code = resolution.code or "catalog_not_found"
        details = PendingActionErrorDetails(
            matched_namespace_count=len(resolution.matched_namespaces),
            target_count=resolution.target_count,
        )
        status = "clarification_required" if code == "sku_ambiguous" else "failed"
        return CartActionOutcome(status=status, code=code, details=details)

    product, sku, inventory = _load_catalog(session, resolution.sku_id)
    try:
        _require_sellable(product, sku, inventory)
        available = _available(inventory)
        if quantity > available:
            raise PendingActionServiceError(
                "insufficient_inventory",
                "Requested quantity is not currently available.",
                details={"available_quantity": available},
            )
        view = _create_catalog_pending_action(
            session,
            user_id=user_id,
            thread_id=thread_id,
            product=product,
            sku=sku,
            inventory=inventory,
            quantity=quantity,
            origin_identifier=identifier,
        )
    except PendingActionServiceError as exc:
        return CartActionOutcome(
            status="failed",
            code=exc.code,
            details=exc.details,
        )
    return CartActionOutcome(
        status="prepared",
        pending_action_id=view.pending_action_id,
        pending_action=view,
    )


def _create_catalog_pending_action(
    session: Session,
    *,
    user_id: str,
    thread_id: str | None,
    product: CatalogProduct,
    sku: CatalogSku,
    inventory: CatalogInventory,
    quantity: int,
    source_run_id: str | None = None,
    source_recommendation_schema_version: str | None = None,
    origin_identifier: str | None = None,
) -> PendingActionView:
    now = _now()
    amount = Decimal(sku.money_amount).quantize(Decimal("0.01"))
    payload: dict[str, Any] = {
        "schema_version": PENDING_ACTION_SCHEMA_VERSION,
        "sku_id": str(sku.id),
        "initial_quantity": quantity,
        "quantity": quantity,
        "source_product_id": str(product.id),
        "product_code_snapshot": product.product_code,
        "product_name_snapshot": product.name,
        "sku_code_snapshot": sku.sku_code,
        "sku_name_snapshot": sku.name,
        "price_snapshot": {"amount": format(amount, ".2f"), "currency": sku.currency},
        "currency_snapshot": sku.currency,
        "availability_snapshot": {
            "sale_status": sku.sale_status,
            "available_quantity": _available(inventory),
            "in_stock": _available(inventory) > 0,
            "reason_code": None if _available(inventory) > 0 else "out_of_stock",
        },
    }
    metadata: dict[str, Any] = {"schema_version": PENDING_ACTION_SCHEMA_VERSION}
    if source_run_id is not None:
        payload["source_run_id"] = source_run_id
        payload["source_recommendation_schema_version"] = source_recommendation_schema_version
    if origin_identifier is not None:
        payload["origin"] = "legacy_chat"
        payload["origin_identifier"] = origin_identifier.strip()
        metadata["origin"] = "legacy_chat"
    action = PendingAction(
        id=str(uuid4()), user_id=user_id, thread_id=thread_id, action_type="add_to_cart",
        payload_json=payload, risk_class="high",
        preview_text=f"Add {quantity} x {product.name} ({sku.sku_code}) to cart",
        status="pending", version=1, result_json={}, metadata_json=metadata,
        expires_at=now + DEFAULT_PENDING_ACTION_TTL, created_at=now, updated_at=now,
    )
    session.add(action)
    session.flush()
    return pending_action_to_view(session, action)


def get_pending_action_view(session: Session, *, pending_action_id: str, user_id: str, thread_id: str) -> PendingActionView:
    action = _get_scoped_action(session, pending_action_id, user_id, thread_id, lock=True)
    if action.status == "pending" and _is_expired(action.expires_at):
        _expire_action(session, action)
    return pending_action_to_view(session, action)


def confirm_add_to_cart(
    session: Session, *, pending_action_id: str, user_id: str, thread_id: str,
    expected_version: int | None, updated_fields: dict[str, Any] | None = None,
) -> PendingActionTransitionResponse:
    action = _get_scoped_action(session, pending_action_id, user_id, thread_id, lock=True)
    request_hash = _request_hash("confirm", updated_fields)
    if action.status != "pending":
        return _replay_or_conflict(action, request_hash)
    payload = action.payload_json or {}
    if payload.get("schema_version") != PENDING_ACTION_SCHEMA_VERSION:
        raise _terminal_error(session, action, "confirm", request_hash, "unsupported_action_schema", "Pending action schema is not supported.")
    if expected_version is None:
        raise PendingActionServiceError(
            "expected_version_required",
            "Canonical add-to-cart confirmation requires the client-held action version.",
        )
    if action.version != expected_version:
        raise PendingActionServiceError("version_conflict", "Pending action version is stale.", details={"current_version": action.version})
    if _is_expired(action.expires_at):
        raise _terminal_error(session, action, "confirm", request_hash, "action_expired", "Pending action has expired.", 410)
    fields = _normalize_fields(updated_fields)
    quantity = _validated_edit_quantity(fields, action)
    try:
        sku_id = UUID(str(payload["sku_id"]))
        source_product_id = UUID(str(payload["source_product_id"]))
    except (KeyError, TypeError, ValueError):
        raise _terminal_error(session, action, "confirm", request_hash, "invalid_action_payload", "Pending action payload is invalid.")
    product, sku, inventory = _load_catalog(session, sku_id, lock=True)
    if product is None or sku is None or inventory is None:
        raise _terminal_error(session, action, "confirm", request_hash, "catalog_not_found", "Catalog SKU is no longer available.", 404)
    if product.id != source_product_id:
        raise _terminal_error(session, action, "confirm", request_hash, "catalog_identity_changed", "Catalog SKU identity changed.")
    if product.sale_status != "active":
        raise _terminal_error(session, action, "confirm", request_hash, "product_inactive", "Catalog product is no longer active.")
    if sku.sale_status != "active":
        raise _terminal_error(session, action, "confirm", request_hash, "sku_inactive", "Catalog SKU is no longer active.")
    available = _available(inventory)
    existing = get_cart_item_for_update(session, user_id=user_id, sku_id=sku_id)
    existing_quantity = existing.quantity if existing else 0
    merged_quantity = quantity + existing_quantity
    if merged_quantity > MAX_CART_ITEM_QUANTITY:
        raise PendingActionServiceError("cart_quantity_limit", "Combined cart quantity exceeds the limit.", details={"max_quantity": MAX_CART_ITEM_QUANTITY, "current_quantity": merged_quantity})
    if merged_quantity > available:
        raise PendingActionServiceError("insufficient_inventory", "Combined cart quantity is not currently available.", details={"available_quantity": available, "current_quantity": existing_quantity})
    amount = Decimal(sku.money_amount).quantize(Decimal("0.01"))
    snapshot = payload.get("price_snapshot") or {}
    snapshot_amount = snapshot.get("amount")
    snapshot_currency = snapshot.get("currency") or payload.get("currency_snapshot")
    price_changed = str(snapshot_amount) != format(amount, ".2f") or snapshot_currency != sku.currency
    payload["quantity"] = quantity
    action.payload_json = payload
    cart_item = upsert_cart_item(session, user_id=user_id, sku_id=sku_id, quantity=merged_quantity)
    cart_view = get_cart_item_view(session, user_id=user_id, sku_id=sku_id)
    view = pending_action_to_view(session, action)
    record = _persist_success(
        session, action, "confirm", request_hash, view, cart_view, price_changed=price_changed,
        snapshot_money=_money_or_none(snapshot_amount, snapshot_currency),
        current_money=Money(amount=format(amount, ".2f"), currency=sku.currency),
        requested_quantity=quantity, cart_quantity=merged_quantity, status="confirmed",
    )
    return _response_from_record(record, replay=False)


def confirm_save_preference(
    session: Session,
    *,
    pending_action_id: str,
    user_id: str,
    thread_id: str | None,
    expected_version: int | None,
    updated_fields: dict[str, Any] | None = None,
) -> PendingActionTransitionResponse:
    """Confirm one canonical append-only preference action deterministically."""

    action = _get_scoped_action(session, pending_action_id, user_id, thread_id, lock=True)
    request_hash = _request_hash("confirm", updated_fields)
    if action.status != "pending":
        return _replay_or_conflict(action, request_hash)
    payload = action.payload_json or {}
    if (
        payload.get("schema_version") != PREFERENCE_ACTION_SCHEMA_VERSION
        or payload.get("operation") != PREFERENCE_ACTION_OPERATION
    ):
        raise _terminal_error(
            session,
            action,
            "confirm",
            request_hash,
            "unsupported_action_schema",
            "Pending preference action schema is not supported.",
        )
    if expected_version is None:
        raise PendingActionServiceError(
            "expected_version_required",
            "Canonical preference confirmation requires the client-held action version.",
        )
    if action.version != expected_version:
        raise PendingActionServiceError(
            "version_conflict",
            "Pending preference action version is stale.",
            details={"current_version": action.version},
        )
    if _is_expired(action.expires_at):
        raise _terminal_error(
            session,
            action,
            "confirm",
            request_hash,
            "action_expired",
            "Pending preference action has expired.",
            410,
        )

    fields = _validate_preference_edits(updated_fields)
    merged_payload = {**payload, **fields}
    try:
        canonical_payload = SavePreferenceActionPayload.model_validate(merged_payload)
    except Exception:
        raise _terminal_error(
            session,
            action,
            "confirm",
            request_hash,
            "invalid_action_payload",
            "Pending preference action payload is invalid.",
        )

    preference_repository.add_user_preference(
        session,
        user_id=user_id.strip(),
        preference_type=canonical_payload.preference_type,
        preference_value=canonical_payload.preference_value,
    )
    action.payload_json = canonical_payload.model_dump(mode="json")
    view = pending_action_to_view(session, action)
    record = _persist_success(
        session,
        action,
        "confirm",
        request_hash,
        view,
        None,
        status="confirmed",
    )
    return _response_from_record(record, replay=False)


def cancel_pending_action(session: Session, *, pending_action_id: str, user_id: str, thread_id: str, expected_version: int) -> PendingActionTransitionResponse:
    action = _get_scoped_action(session, pending_action_id, user_id, thread_id, lock=True)
    request_hash = _request_hash("cancel", None)
    if action.status != "pending":
        return _replay_or_conflict(action, request_hash)
    if action.version != expected_version:
        raise PendingActionServiceError("version_conflict", "Pending action version is stale.", details={"current_version": action.version})
    if _is_expired(action.expires_at):
        raise _terminal_error(session, action, "cancel", request_hash, "action_expired", "Pending action has expired.", 410)
    view = pending_action_to_view(session, action)
    record = _persist_success(session, action, "cancel", request_hash, view, None, status="cancelled")
    return _response_from_record(record, replay=False)


def pending_action_to_view(session: Session, action: PendingAction) -> PendingActionView:
    payload = action.payload_json or {}
    if action.action_type == "add_to_cart" and payload.get("schema_version") == PENDING_ACTION_SCHEMA_VERSION:
        preview = _snapshot_preview(action, payload)
        editable = [IntegerEditableField(field="quantity", label="Quantity", current_value=int(payload.get("quantity", 1)))] if action.status == "pending" else []
    elif action.action_type == "add_to_cart":
        preview, editable = _legacy_preview(session, action)
    elif action.action_type == "save_preference":
        preview, editable = _legacy_preference_preview(action)
    else:
        preview, editable = action.preview_text or None, []
    return PendingActionView(
        pending_action_id=action.id, action_type=action.action_type, risk_class=action.risk_class,
        status=action.status, version=action.version, expires_at=action.expires_at,
        preview=preview, editable_fields=editable, confirm_label="Confirm", cancel_label="Cancel",
    )


def _snapshot_preview(action: PendingAction, payload: dict[str, Any]) -> AddToCartPreview:
    snapshot = payload.get("price_snapshot") or {}
    amount, currency = snapshot.get("amount"), snapshot.get("currency") or payload.get("currency_snapshot")
    money = _money_or_none(amount, currency)
    quantity = int(payload.get("quantity", 1))
    availability_data = payload.get("availability_snapshot")
    availability = AvailabilityView.model_validate(availability_data) if availability_data else None
    try:
        sku_id = UUID(str(payload["sku_id"]))
    except (KeyError, TypeError, ValueError):
        sku_id = None
    try:
        product_id = UUID(str(payload["source_product_id"]))
    except (KeyError, TypeError, ValueError):
        product_id = None
    return AddToCartPreview(
        kind="catalog_sku", sku_id=sku_id, sku_code=str(payload.get("sku_code_snapshot", "")),
        product_id=product_id, product_code=payload.get("product_code_snapshot"),
        product_name=str(payload.get("product_name_snapshot", "Catalog product")), sku_name=payload.get("sku_name_snapshot"),
        requested_quantity=quantity, unit_money_snapshot=money,
        subtotal_money_snapshot=Money(amount=format((Decimal(str(amount)) * quantity).quantize(Decimal("0.01")), ".2f"), currency=str(currency)) if money else None,
        availability_snapshot=availability, preview_text=action.preview_text or None,
    )


def _legacy_preview(session: Session, action: PendingAction):
    payload = action.payload_json or {}
    product = session.get(Product, payload.get("product_id")) if payload.get("product_id") else None
    quantity = payload.get("quantity", 1)
    if product is None or type(quantity) is not int or not 1 <= quantity <= MAX_CART_ITEM_QUANTITY:
        return action.preview_text or "Add item to cart", []
    preview = AddToCartPreview(
        kind="legacy_product", legacy_product_id=product.product_id, product_name=product.name,
        requested_quantity=quantity, unit_money_snapshot=None, subtotal_money_snapshot=None,
        availability_snapshot=None, preview_text=action.preview_text or None,
    )
    editable = [IntegerEditableField(field="quantity", label="Quantity", current_value=quantity)] if action.status == "pending" else []
    return preview, editable


def _legacy_preference_preview(action: PendingAction):
    payload = action.payload_json or {}
    preference_type = str(payload.get("preference_type", "other"))
    preference_value = str(payload.get("preference_value", ""))
    if action.status != "pending":
        return action.preview_text or "Save preference", []
    editable = [
        EnumEditableField(
            field="preference_type", label="Preference type", current_value=preference_type,
            options=["budget", "brand", "avoid", "usage", "style", "other"],
        ),
        TextEditableField(
            field="preference_value", label="Preference value", current_value=preference_value,
            min_length=1, max_length=2000,
        ),
    ]
    return action.preview_text or "Save preference", editable


def _response_from_record(record: PendingActionResolutionRecord, *, replay: bool) -> PendingActionTransitionResponse:
    return PendingActionTransitionResponse(
        pending_action=record.pending_action, cart_item=record.cart_item, price_changed=record.price_changed,
        snapshot_money=record.snapshot_money, current_money=record.current_money,
        requested_quantity=record.requested_quantity, cart_quantity=record.cart_quantity, idempotent_replay=replay,
    )


def _replay_or_conflict(action: PendingAction, request_hash: str) -> PendingActionTransitionResponse:
    if action.resolution_request_hash == request_hash and action.result_json:
        try:
            record = PendingActionResolutionRecord.model_validate(action.result_json)
        except Exception as exc:
            raise PendingActionServiceError("invalid_action_payload", "Persisted action resolution is invalid.") from exc
        if record.response_kind == "success":
            return _response_from_record(record, replay=True)
        raise PendingActionServiceError.from_record(record, replay=True)
    raise PendingActionServiceError("action_resolution_conflict", "Pending action has already been resolved.", details={"action_status": action.status, "current_version": action.version})


def _persist_success(session: Session, action: PendingAction, transition: str, request_hash: str, view: PendingActionView, cart_item: CartItemView | None, *, status: str, price_changed: bool = False, snapshot_money: Money | None = None, current_money: Money | None = None, requested_quantity: int | None = None, cart_quantity: int | None = None) -> PendingActionResolutionRecord:
    view = view.model_copy(update={"status": status, "version": action.version + 1, "editable_fields": []})
    record = PendingActionResolutionRecord(
        schema_version=RESOLUTION_SCHEMA_VERSION, transition=transition, request_hash=request_hash,
        http_status=200, response_kind="success", pending_action=view, cart_item=cart_item,
        price_changed=price_changed, snapshot_money=snapshot_money, current_money=current_money,
        requested_quantity=requested_quantity, cart_quantity=cart_quantity, resolved_at=_now(),
    )
    _mark_terminal(action, status=status, record=record, request_hash=request_hash)
    session.flush()
    return record


def _terminal_error(session: Session, action: PendingAction, transition: str, request_hash: str, code: str, message: str, status_code: int = 409, details: dict[str, Any] | None = None):
    view = pending_action_to_view(session, action)
    terminal_status = "expired" if code == "action_expired" else "failed"
    view = view.model_copy(update={"status": terminal_status, "version": action.version + 1, "editable_fields": []})
    error = ActionErrorResponse(code=code, message=message, details=PendingActionErrorDetails.model_validate(details or {}), idempotent_replay=False)
    record = PendingActionResolutionRecord(schema_version=RESOLUTION_SCHEMA_VERSION, transition=transition, request_hash=request_hash, http_status=status_code, response_kind="error", pending_action=view, error=error, resolved_at=_now())
    _mark_terminal(action, status=terminal_status, record=record, request_hash=request_hash)
    session.flush()
    raise PendingActionServiceError(code, message, status_code=status_code, details=error.details, persisted_terminal=True, resolution_record=record)


def _expire_action(session: Session, action: PendingAction) -> None:
    view = pending_action_to_view(session, action)
    view = view.model_copy(update={"status": "expired", "version": action.version + 1, "editable_fields": []})
    record = PendingActionResolutionRecord(schema_version=RESOLUTION_SCHEMA_VERSION, transition="expire", request_hash=None, http_status=200, response_kind="success", pending_action=view, resolved_at=_now())
    _mark_terminal(action, status="expired", record=record, request_hash=None)
    session.flush()


def _mark_terminal(action: PendingAction, *, status: str, record: PendingActionResolutionRecord, request_hash: str | None) -> None:
    action.status, action.result_json = status, record.model_dump(mode="json")
    action.resolution_request_hash, action.resolved_at = request_hash, record.resolved_at
    action.version += 1
    action.updated_at = _now()


def _normalize_fields(fields: dict[str, Any] | None) -> dict[str, Any]:
    if fields is None:
        return {}
    return fields.model_dump(exclude_none=True) if hasattr(fields, "model_dump") else dict(fields)


def _validated_edit_quantity(fields: dict[str, Any], action: PendingAction) -> int:
    if set(fields) - {"quantity"}:
        raise PendingActionServiceError("invalid_updated_fields", "Only quantity may be edited.")
    raw = fields.get("quantity", (action.payload_json or {}).get("quantity", 1))
    if type(raw) is not int or not 1 <= raw <= MAX_CART_ITEM_QUANTITY:
        raise PendingActionServiceError("invalid_quantity", "Quantity must be an integer between 1 and 20.")
    return raw


def _validate_preference_edits(fields: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_fields(fields)
    if set(normalized) - {"preference_type", "preference_value"}:
        raise PendingActionServiceError(
            "invalid_updated_fields",
            "Only preference_type and preference_value may be edited.",
        )
    if "preference_type" in normalized:
        preference_type = normalized["preference_type"]
        if not isinstance(preference_type, str):
            raise PendingActionServiceError("invalid_updated_fields", "Preference type is invalid.")
        normalized_type, was_invalid = preference_repository._normalize_preference_type(
            preference_type
        )
        if was_invalid:
            raise PendingActionServiceError("invalid_updated_fields", "Preference type is invalid.")
        normalized["preference_type"] = normalized_type
    if "preference_value" in normalized:
        preference_value = normalized["preference_value"]
        if (
            not isinstance(preference_value, str)
            or not preference_value.strip()
            or len(preference_value.strip()) > 2000
        ):
            raise PendingActionServiceError("invalid_updated_fields", "Preference value is invalid.")
        normalized["preference_value"] = preference_value.strip()
    return normalized


def _request_hash(transition: str, fields: dict[str, Any] | None) -> str:
    raw = json.dumps({"transition": transition, "updated_fields": _normalize_fields(fields) if fields is not None else None}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_catalog(session: Session, sku_id: UUID, *, lock: bool = False):
    sku = session.get(CatalogSku, sku_id, with_for_update=lock)
    if sku is None:
        return None, None, None
    product = session.get(CatalogProduct, sku.product_id, with_for_update=lock)
    inventory = session.get(CatalogInventory, sku.id, with_for_update=lock)
    return product, sku, inventory


def _require_sellable(product: CatalogProduct | None, sku: CatalogSku | None, inventory: CatalogInventory | None) -> None:
    if product is None or sku is None or inventory is None:
        raise PendingActionServiceError("catalog_not_found", "Catalog SKU is no longer available.", status_code=404)
    if product.sale_status != "active":
        raise PendingActionServiceError("product_inactive", "Catalog product is not active.")
    if sku.sale_status != "active":
        raise PendingActionServiceError("sku_inactive", "Catalog SKU is not active.")


def _get_scoped_action(session: Session, action_id: str, user_id: str, thread_id: str, *, lock: bool = False) -> PendingAction:
    statement = select(PendingAction).where(PendingAction.id == action_id)
    if lock:
        statement = statement.with_for_update()
    action = session.scalar(statement)
    if action is None or action.user_id != user_id or action.thread_id != thread_id:
        raise PendingActionServiceError("pending_action_not_found", "Pending action was not found.", status_code=404)
    return action


def _available(inventory: CatalogInventory | None) -> int:
    return 0 if inventory is None else max(0, inventory.on_hand_quantity - inventory.reserved_quantity)


def _money_or_none(amount: Any, currency: Any) -> Money | None:
    if amount in (None, "") or currency in (None, ""):
        return None
    return Money(amount=str(amount), currency=str(currency))


def _validate_quantity(quantity: int) -> None:
    if type(quantity) is not int or not 1 <= quantity <= MAX_CART_ITEM_QUANTITY:
        raise PendingActionServiceError("invalid_quantity", "Quantity must be an integer between 1 and 20.")


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    value = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    return value <= _now()


def _now() -> datetime:
    return datetime.now(timezone.utc)
