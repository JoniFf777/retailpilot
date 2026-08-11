"""Stateless, signed Checkout tokens used by the Phase 4A order boundary."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Iterable, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator


TOKEN_SCHEMA_VERSION = "shopmind.checkout-token.v1"
TOKEN_PREFIX = "v1"
MAX_TOKEN_LENGTH = 65_536
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class CheckoutTokenError(ValueError):
    """A typed, safe-to-return Checkout token validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CheckoutTokenUnavailable(CheckoutTokenError):
    def __init__(self) -> None:
        super().__init__("checkout_unavailable", "Checkout is not configured on this server.")


class CheckoutPriceLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku_id: UUID
    unit_price_amount: StrictStr
    currency: StrictStr

    @field_validator("unit_price_amount")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("price amount must be a decimal string") from exc
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError("price amount must be positive with at most two decimals")
        return format(amount.quantize(Decimal("0.01")), ".2f")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        if len(value) != 3 or not value.isalpha() or value != value.upper():
            raise ValueError("currency must be an uppercase three-letter code")
        return value


class CheckoutTokenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictStr
    owner_fingerprint: StrictStr = Field(min_length=64, max_length=64)
    cart_fingerprint: StrictStr = Field(min_length=64, max_length=64)
    price_fingerprint: StrictStr = Field(min_length=64, max_length=64)
    price_lines: list[CheckoutPriceLine] = Field(min_length=1)
    currency: StrictStr
    subtotal_amount: StrictStr
    issued_at: StrictInt = Field(ge=0)
    expires_at: StrictInt = Field(ge=1)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != TOKEN_SCHEMA_VERSION:
            raise ValueError("unknown checkout token schema")
        return value

    @field_validator("owner_fingerprint", "cart_fingerprint", "price_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("fingerprint must be lowercase hexadecimal")
        return value

    @field_validator("currency")
    @classmethod
    def validate_payload_currency(cls, value: str) -> str:
        if len(value) != 3 or not value.isalpha() or value != value.upper():
            raise ValueError("currency must be an uppercase three-letter code")
        return value

    @field_validator("subtotal_amount")
    @classmethod
    def validate_subtotal(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("subtotal must be a decimal string") from exc
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError("subtotal must be positive with at most two decimals")
        return format(amount.quantize(Decimal("0.01")), ".2f")

    @model_validator(mode="after")
    def validate_payload(self) -> "CheckoutTokenPayload":
        if self.expires_at <= self.issued_at:
            raise ValueError("checkout token expiry must follow issuance")
        if len({line.sku_id for line in self.price_lines}) != len(self.price_lines):
            raise ValueError("checkout token contains duplicate SKUs")
        if any(line.currency != self.currency for line in self.price_lines):
            raise ValueError("checkout token contains mixed currencies")
        expected = build_price_fingerprint(self.price_lines)
        if expected != self.price_fingerprint:
            raise ValueError("checkout token price fingerprint is invalid")
        return self


@dataclass(frozen=True)
class VerifiedCheckoutToken:
    payload: CheckoutTokenPayload
    raw_payload: bytes


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _uuid_text(value: UUID | str) -> str:
    return str(value).lower()


def _amount_text(value: Decimal | str) -> str:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be decimal") from exc
    if not amount.is_finite():
        raise ValueError("amount must be finite")
    return format(amount.quantize(Decimal("0.01")), ".2f")


def owner_fingerprint(user_id: str) -> str:
    return sha256(("shopmind.checkout.owner\0" + user_id).encode("utf-8")).hexdigest()


def build_cart_fingerprint(items: Iterable[Mapping[str, Any]]) -> str:
    normalized = [
        {
            "cart_item_id": _uuid_text(item["cart_item_id"]),
            "sku_id": _uuid_text(item["sku_id"]),
            "quantity": int(item["quantity"]),
            "version": int(item["version"]),
        }
        for item in items
    ]
    normalized.sort(key=lambda item: (item["sku_id"], item["cart_item_id"]))
    return sha256(_canonical_json(normalized)).hexdigest()


def _price_line_dict(line: CheckoutPriceLine | Mapping[str, Any]) -> dict[str, str]:
    if isinstance(line, CheckoutPriceLine):
        return {
            "sku_id": _uuid_text(line.sku_id),
            "unit_price_amount": _amount_text(line.unit_price_amount),
            "currency": line.currency,
        }
    return {
        "sku_id": _uuid_text(line["sku_id"]),
        "unit_price_amount": _amount_text(line["unit_price_amount"]),
        "currency": str(line["currency"]).upper(),
    }


def build_price_fingerprint(lines: Iterable[CheckoutPriceLine | Mapping[str, Any]]) -> str:
    normalized = [_price_line_dict(line) for line in lines]
    normalized.sort(key=lambda line: line["sku_id"])
    return sha256(_canonical_json(normalized)).hexdigest()


def _encode_segment(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_segment(value: str) -> bytes:
    if not value or not _SEGMENT_RE.fullmatch(value):
        raise CheckoutTokenError("checkout_invalid", "Checkout token encoding is invalid.")
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise CheckoutTokenError("checkout_invalid", "Checkout token encoding is invalid.") from exc


def _secret_bytes(secret: str | None) -> bytes:
    if secret is None or len(secret) < 32:
        raise CheckoutTokenUnavailable()
    return secret.encode("utf-8")


def create_checkout_token(
    *,
    user_id: str,
    cart_fingerprint: str,
    price_lines: Iterable[CheckoutPriceLine | Mapping[str, Any]],
    currency: str,
    subtotal_amount: Decimal | str,
    secret: str | None,
    ttl_seconds: int,
    now: datetime | None = None,
) -> str:
    secret_bytes = _secret_bytes(secret)
    issued_at = int((now or datetime.now(timezone.utc)).timestamp())
    payload_lines = [CheckoutPriceLine.model_validate(_price_line_dict(line)) for line in price_lines]
    payload_data = CheckoutTokenPayload(
        schema_version=TOKEN_SCHEMA_VERSION,
        owner_fingerprint=owner_fingerprint(user_id),
        cart_fingerprint=cart_fingerprint,
        price_fingerprint=build_price_fingerprint(payload_lines),
        price_lines=sorted(payload_lines, key=lambda line: str(line.sku_id).lower()),
        currency=currency,
        subtotal_amount=_amount_text(subtotal_amount),
        issued_at=issued_at,
        expires_at=issued_at + ttl_seconds,
    )
    raw_payload = _canonical_json(payload_data.model_dump(mode="json"))
    signature = hmac.new(secret_bytes, raw_payload, hashlib.sha256).digest()
    token = f"{TOKEN_PREFIX}.{_encode_segment(raw_payload)}.{_encode_segment(signature)}"
    if len(token) > MAX_TOKEN_LENGTH:
        raise CheckoutTokenError("checkout_invalid", "Checkout token is too large.")
    return token


def verify_checkout_token(
    token: str,
    *,
    user_id: str,
    secret: str | None,
    now: datetime | None = None,
) -> VerifiedCheckoutToken:
    _secret_bytes(secret)
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        raise CheckoutTokenError("checkout_invalid", "Checkout token is invalid.")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        raise CheckoutTokenError("checkout_invalid", "Checkout token is invalid.")
    raw_payload = _decode_segment(parts[1])
    signature = _decode_segment(parts[2])
    if len(signature) != hashlib.sha256().digest_size:
        raise CheckoutTokenError("checkout_invalid", "Checkout token signature is invalid.")
    expected = hmac.new(_secret_bytes(secret), raw_payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise CheckoutTokenError("checkout_invalid", "Checkout token signature is invalid.")
    try:
        decoded = json.loads(raw_payload.decode("utf-8"))
        payload = CheckoutTokenPayload.model_validate(decoded)
        if _canonical_json(payload.model_dump(mode="json")) != raw_payload:
            raise ValueError("non-canonical payload")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CheckoutTokenError("checkout_invalid", "Checkout token payload is invalid.") from exc
    if payload.owner_fingerprint != owner_fingerprint(user_id):
        raise CheckoutTokenError("checkout_invalid", "Checkout token owner is invalid.")
    current = int((now or datetime.now(timezone.utc)).timestamp())
    if current >= payload.expires_at:
        raise CheckoutTokenError("checkout_expired", "Checkout token has expired.")
    return VerifiedCheckoutToken(payload=payload, raw_payload=raw_payload)


__all__ = [
    "CheckoutPriceLine",
    "CheckoutTokenError",
    "CheckoutTokenPayload",
    "CheckoutTokenUnavailable",
    "VerifiedCheckoutToken",
    "build_cart_fingerprint",
    "build_price_fingerprint",
    "create_checkout_token",
    "owner_fingerprint",
    "verify_checkout_token",
]
