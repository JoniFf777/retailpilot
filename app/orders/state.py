"""Small immutable contracts shared by Order services and routes."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def request_hash(request: BaseModel) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json", exclude_none=False),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        raise ValueError("Idempotency-Key must contain only stable ASCII characters and be 1-128 characters long.")
    return value


def encode_order_cursor(created_at: datetime, order_id: Any) -> str:
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(order_id).lower()},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_order_cursor(value: str) -> tuple[datetime, str]:
    import base64
    from uuid import UUID

    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        data = json.loads(raw.decode("utf-8"))
        created_at = datetime.fromisoformat(data["created_at"])
        order_id = str(UUID(data["id"]))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("cursor is invalid") from exc
    if created_at.tzinfo is None or set(data) != {"created_at", "id"}:
        raise ValueError("cursor is invalid")
    return created_at, order_id
