"""Small, reusable guards for ShopMind's shopping fact boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DYNAMIC_FACT_KEYS = frozenset(
    {
        "price",
        "amount",
        "inventory",
        "available_quantity",
        "stock",
        "in_stock",
        "sale_status",
        "promotion",
        "discount",
        "order_status",
        "payment_status",
        "cart_status",
    }
)


class ShoppingFactConflict(ValueError):
    """Raised when untrusted evidence tries to become a shopping fact."""


def non_authoritative_document_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return metadata with dynamic commerce facts explicitly quarantined."""

    result = dict(metadata)
    quarantined: list[str] = []
    for key in tuple(result):
        if key.casefold() in DYNAMIC_FACT_KEYS:
            quarantined.append(key)
            result.pop(key, None)
    if quarantined:
        result["non_authoritative_fields"] = sorted(
            set(result.get("non_authoritative_fields", ())) | set(quarantined)
        )
    result["authority"] = "evidence_only"
    return result


def ensure_no_business_writer(result: Mapping[str, Any]) -> None:
    """Reject an extension result that attempts to carry a business mutation."""

    side_effect = str(result.get("side_effect", "none")).casefold()
    if side_effect in {"write", "sensitive_write", "mutation"}:
        raise ShoppingFactConflict("Shopping extensions cannot write business state.")


def catalog_authority(catalog_value: Any, evidence_value: Any) -> tuple[Any, bool]:
    """Return the Catalog value and whether evidence attempted to disagree."""

    return catalog_value, evidence_value is not None and evidence_value != catalog_value


__all__ = [
    "DYNAMIC_FACT_KEYS",
    "ShoppingFactConflict",
    "catalog_authority",
    "ensure_no_business_writer",
    "non_authoritative_document_metadata",
]
