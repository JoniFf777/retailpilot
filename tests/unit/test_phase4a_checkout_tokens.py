from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.checkout.tokens import (
    CheckoutTokenError,
    build_cart_fingerprint,
    build_price_fingerprint,
    create_checkout_token,
    owner_fingerprint,
    verify_checkout_token,
)
from app.orders.state import request_hash
from app.schemas.orders import CreateOrderRequest


SECRET = "phase4a-test-secret-0123456789abcdef"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SKU_A = UUID("00000000-0000-0000-0000-00000000000a")
SKU_B = UUID("00000000-0000-0000-0000-00000000000b")


def _token(*, user_id: str = "user-a", expires_ttl: int = 900) -> str:
    cart = [
        {"cart_item_id": "00000000-0000-0000-0000-000000000002", "sku_id": SKU_B, "quantity": 1, "version": 1},
        {"cart_item_id": "00000000-0000-0000-0000-000000000001", "sku_id": SKU_A, "quantity": 2, "version": 3},
    ]
    prices = [
        {"sku_id": SKU_B, "unit_price_amount": "19.9", "currency": "CNY"},
        {"sku_id": SKU_A, "unit_price_amount": "5.00", "currency": "CNY"},
    ]
    return create_checkout_token(
        user_id=user_id,
        cart_fingerprint=build_cart_fingerprint(cart),
        price_lines=prices,
        currency="CNY",
        subtotal_amount=Decimal("29.80"),
        secret=SECRET,
        ttl_seconds=expires_ttl,
        now=NOW,
    )


def test_token_round_trip_is_canonical_and_owner_is_hashed() -> None:
    token = _token()
    verified = verify_checkout_token(token, user_id="user-a", secret=SECRET, now=NOW)
    assert verified.payload.price_lines[0].sku_id == SKU_A
    assert verified.payload.price_lines[0].unit_price_amount == "5.00"
    assert verified.payload.owner_fingerprint == owner_fingerprint("user-a")
    assert "user-a" not in token
    assert token == _token()


def test_token_rejects_tamper_wrong_owner_unknown_schema_and_expiry() -> None:
    token = _token()
    left, payload, signature = token.split(".")
    tampered = f"{left}.{payload[:-1]}A.{signature}"
    with pytest.raises(CheckoutTokenError) as tamper:
        verify_checkout_token(tampered, user_id="user-a", secret=SECRET, now=NOW)
    assert tamper.value.code == "checkout_invalid"
    with pytest.raises(CheckoutTokenError) as owner:
        verify_checkout_token(token, user_id="user-b", secret=SECRET, now=NOW)
    assert owner.value.code == "checkout_invalid"
    with pytest.raises(CheckoutTokenError) as expiry:
        verify_checkout_token(token, user_id="user-a", secret=SECRET, now=NOW + timedelta(seconds=901))
    assert expiry.value.code == "checkout_expired"


def test_fingerprints_and_request_hash_are_order_independent_and_exact() -> None:
    first = [
        {"cart_item_id": SKU_A, "sku_id": SKU_B, "quantity": 1, "version": 2},
        {"cart_item_id": SKU_B, "sku_id": SKU_A, "quantity": 2, "version": 4},
    ]
    assert build_cart_fingerprint(first) == build_cart_fingerprint(reversed(first))
    prices = [
        {"sku_id": SKU_B, "unit_price_amount": "2", "currency": "CNY"},
        {"sku_id": SKU_A, "unit_price_amount": "1.00", "currency": "CNY"},
    ]
    assert build_price_fingerprint(prices) == build_price_fingerprint(reversed(prices))
    request = CreateOrderRequest(checkout_token="token")
    assert request_hash(request) == request_hash(CreateOrderRequest.model_validate({"checkout_token": "token"}))
    assert request_hash(request) != request_hash(CreateOrderRequest(checkout_token="token-2"))
