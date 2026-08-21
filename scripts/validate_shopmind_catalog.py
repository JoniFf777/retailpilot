"""Validate managed Laptop/Monitor recommendation seed data deterministically."""

from __future__ import annotations

import argparse
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = (
    PROJECT_ROOT / "data" / "catalog" / "laptop_catalog.json",
    PROJECT_ROOT / "data" / "catalog" / "monitor_catalog.json",
)
DEFAULT_DOCS = PROJECT_ROOT / "data" / "documents" / "products"
_CURRENCY = re.compile(r"^[A-Z]{3}$")

REQUIRED_ATTRIBUTES: dict[str, dict[str, type | tuple[type, ...]]] = {
    "laptop": {
        "cpu_tier": str,
        "gpu_tier": str,
        "memory_gb": int,
        "storage_gb": int,
        "weight_kg": (int, float),
        "screen_inches": (int, float),
        "use_cases": list,
    },
    "monitor": {
        "size_inches": (int, float),
        "resolution": str,
        "refresh_rate_hz": int,
        "panel_type": str,
        "use_cases": list,
    },
}
VALID_STATUS = {"draft", "active", "inactive"}
VALID_MONITOR_RESOLUTIONS = {"1080p", "1440p", "4k"}


def _issue(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def _money(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() and amount > 0 else None


def _matches_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    if expected is int and isinstance(value, bool):
        return False
    if isinstance(expected, tuple) and int in expected and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def validate_catalog_files(
    seed_paths: Iterable[Path] = DEFAULT_SEEDS,
    *,
    docs_dir: Path = DEFAULT_DOCS,
) -> dict[str, Any]:
    """Return a stable JSON-compatible validation report without writing data."""

    issues: list[dict[str, str]] = []
    categories: dict[str, dict[str, Any]] = {}
    category_codes: set[str] = set()
    product_codes: dict[str, str] = {}
    legacy_ids: dict[str, str] = {}
    sku_codes: dict[str, str] = {}
    all_doc_ids: set[str] = set()
    docs_dir = Path(docs_dir)
    for doc in sorted(docs_dir.glob("*.md")):
        all_doc_ids.add(doc.stem)

    for seed_path in seed_paths:
        seed_path = Path(seed_path)
        path_label = str(seed_path)
        try:
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(_issue("seed_invalid_json", path_label, type(exc).__name__))
            continue
        category = seed.get("category") or {}
        category_code = category.get("code")
        if category_code in category_codes:
            issues.append(_issue("duplicate_category", f"{path_label}:category.code", str(category_code)))
        if category_code:
            category_codes.add(category_code)
        if category_code not in REQUIRED_ATTRIBUTES:
            issues.append(_issue("unsupported_category", f"{path_label}:category.code", str(category_code)))
            required = {}
        else:
            required = REQUIRED_ATTRIBUTES[category_code]
        bucket = categories.setdefault(
            str(category_code),
            {"products": 0, "skus": 0, "attributes": len(seed.get("attribute_definitions") or []), "docs": 0, "in_stock": 0, "out_of_stock": 0, "prices": []},
        )
        for product_index, product in enumerate(seed.get("products") or []):
            product_path = f"{path_label}:products[{product_index}]"
            bucket["products"] += 1
            product_code = product.get("product_code")
            if not isinstance(product_code, str) or not product_code.strip():
                issues.append(_issue("product_code_missing", product_path, "product_code is required"))
            elif product_code in product_codes:
                issues.append(_issue("duplicate_product_code", product_path, product_code))
            else:
                product_codes[product_code] = path_label
            legacy_id = product.get("legacy_product_id")
            if not isinstance(legacy_id, str) or not legacy_id.strip():
                issues.append(_issue("legacy_product_id_missing", product_path, "legacy_product_id is required"))
            elif legacy_id in legacy_ids:
                issues.append(_issue("duplicate_legacy_product_id", product_path, legacy_id))
            else:
                legacy_ids[legacy_id] = path_label
            if product.get("sale_status") not in VALID_STATUS:
                issues.append(_issue("invalid_product_status", product_path, str(product.get("sale_status"))))
            attributes = product.get("attributes")
            if not isinstance(attributes, dict):
                issues.append(_issue("product_attributes_invalid", product_path, "attributes must be an object"))
                attributes = {}
            for code, expected in required.items():
                value = attributes.get(code)
                if value is None:
                    issues.append(_issue("required_attribute_missing", f"{product_path}:attributes.{code}", category_code or ""))
                elif not _matches_type(value, expected):
                    issues.append(_issue("attribute_type_invalid", f"{product_path}:attributes.{code}", type(value).__name__))
            if category_code == "monitor" and attributes.get("resolution") not in VALID_MONITOR_RESOLUTIONS:
                issues.append(_issue("monitor_resolution_invalid", f"{product_path}:attributes.resolution", str(attributes.get("resolution"))))
            sku = product.get("sku") or {}
            sku_path = f"{product_path}:sku"
            bucket["skus"] += 1
            sku_code = sku.get("sku_code")
            if not isinstance(sku_code, str) or not sku_code.strip():
                issues.append(_issue("sku_code_missing", sku_path, "sku_code is required"))
            elif sku_code in sku_codes:
                issues.append(_issue("duplicate_sku_code", sku_path, sku_code))
            else:
                sku_codes[sku_code] = path_label
            if sku.get("sale_status") not in VALID_STATUS:
                issues.append(_issue("invalid_sku_status", sku_path, str(sku.get("sale_status"))))
            amount = _money(sku.get("money_amount"))
            if amount is None:
                issues.append(_issue("money_invalid", f"{sku_path}:money_amount", str(sku.get("money_amount"))))
            else:
                bucket["prices"].append(amount)
            currency = sku.get("currency")
            if not isinstance(currency, str) or not _CURRENCY.fullmatch(currency):
                issues.append(_issue("currency_invalid", f"{sku_path}:currency", str(currency)))
            inventory = sku.get("inventory")
            if not isinstance(inventory, int) or isinstance(inventory, bool) or inventory < 0:
                issues.append(_issue("inventory_invalid", f"{sku_path}:inventory", str(inventory)))
            elif inventory > 0:
                bucket["in_stock"] += 1
            else:
                bucket["out_of_stock"] += 1
            if legacy_id:
                doc_path = docs_dir / f"{legacy_id}.md"
                if not doc_path.exists():
                    issues.append(_issue("document_missing", str(doc_path), legacy_id))
                else:
                    bucket["docs"] += 1
                    # Existing corpus documents use the canonical legacy ID as
                    # their filename; the file identity is authoritative for
                    # alignment, while document prose remains evidence only.
                    if doc_path.stem != legacy_id:
                        issues.append(_issue("document_identity_mismatch", str(doc_path), legacy_id))

    for bucket in categories.values():
        minimum = min(bucket["prices"], default=None)
        maximum = max(bucket["prices"], default=None)
        bucket["price_min"] = None if minimum is None else format(minimum, ".2f")
        bucket["price_max"] = None if maximum is None else format(maximum, ".2f")
        del bucket["prices"]
    report = {
        "valid": not issues,
        "seed_files": [str(Path(path)) for path in seed_paths],
        "counts": {"categories": len(categories), "products": len(product_codes), "skus": len(sku_codes), "documents": len(all_doc_ids)},
        "categories": categories,
        "issues": sorted(issues, key=lambda item: (item["code"], item["path"], item["detail"])),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", action="append", type=Path, help="Managed seed JSON; repeat for multiple files.")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()
    report = validate_catalog_files(args.data or DEFAULT_SEEDS, docs_dir=args.docs_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
