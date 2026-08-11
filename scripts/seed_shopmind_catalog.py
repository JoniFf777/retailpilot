"""Idempotently seed the independent ShopMind Laptop Catalog."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import AttributeDefinition, CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.models import Product


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "data" / "catalog" / "laptop_catalog.json"


@dataclass
class SeedReport:
    inserted: dict[str, int] = field(default_factory=lambda: {"categories": 0, "attributes": 0, "products": 0, "skus": 0, "inventory": 0})
    skipped: dict[str, int] = field(default_factory=lambda: {"categories": 0, "attributes": 0, "products": 0, "skus": 0, "inventory": 0})
    updated: dict[str, int] = field(default_factory=lambda: {"categories": 0, "attributes": 0, "products": 0, "skus": 0})
    dangling_legacy_ids: list[str] = field(default_factory=list)


def load_catalog_seed(path: Path = DEFAULT_CATALOG_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _managed_values(seed: dict[str, Any]) -> dict[str, object]:
    return {"managed_by_seed": True, "seed_source": seed["seed_source"], "seed_version": seed["seed_version"]}


def _replace_if_owned(record: object, values: dict[str, object], seed: dict[str, Any], report: SeedReport, key: str, replace: bool) -> None:
    if replace and getattr(record, "managed_by_seed") and getattr(record, "seed_source") == seed["seed_source"]:
        for name, value in values.items(): setattr(record, name, value)
        report.updated[key] += 1
    else:
        report.skipped[key] += 1


def _legacy_mapping_report(session: Session, products: list[dict[str, Any]]) -> list[str]:
    legacy_ids = [row.get("legacy_product_id") for row in products if row.get("legacy_product_id")]
    if not legacy_ids:
        return []
    existing = set(session.scalars(select(Product.product_id).where(Product.product_id.in_(legacy_ids))).all())
    return sorted(set(legacy_ids) - existing)


def seed_catalog(session: Session, seed: dict[str, Any], *, replace_managed_seed: bool = False, dry_run: bool = False) -> SeedReport:
    """Stage Catalog rows in this session; this function never commits."""
    report = SeedReport()
    managed = _managed_values(seed)
    category_data = seed["category"]
    category = session.scalar(select(CatalogCategory).where(CatalogCategory.parent_id.is_(None), CatalogCategory.code == category_data["code"]))
    category_values = {**category_data, **managed}
    if category is None:
        category = CatalogCategory(**category_values); session.add(category); session.flush(); report.inserted["categories"] += 1
    else:
        _replace_if_owned(category, category_values, seed, report, "categories", replace_managed_seed)
    for row in seed["attribute_definitions"]:
        record = session.scalar(select(AttributeDefinition).where(AttributeDefinition.category_id == category.id, AttributeDefinition.code == row["code"]))
        values = {**row, "category_id": category.id, "options_json": row.get("options_json", []), **managed}
        if record is None:
            session.add(AttributeDefinition(**values)); report.inserted["attributes"] += 1
        else:
            _replace_if_owned(record, values, seed, report, "attributes", replace_managed_seed)
    session.flush()
    for row in seed["products"]:
        product = session.scalar(select(CatalogProduct).where(CatalogProduct.product_code == row["product_code"]))
        values = {key: row.get(key) for key in ("product_code", "legacy_product_id", "brand", "name", "description", "sale_status")}
        values.update(category_id=category.id, attributes_json=row["attributes"], **managed)
        if product is None:
            product = CatalogProduct(**values); session.add(product); session.flush(); report.inserted["products"] += 1
        else:
            _replace_if_owned(product, values, seed, report, "products", replace_managed_seed)
        sku_row = row["sku"]
        sku = session.scalar(select(CatalogSku).where(CatalogSku.sku_code == sku_row["sku_code"]))
        sku_values = {key: sku_row[key] for key in ("sku_code", "name", "money_amount", "currency", "sale_status")}
        sku_values.update(product_id=product.id, variant_attributes_json=sku_row.get("variant_attributes", {}), **managed)
        if sku is None:
            sku = CatalogSku(**sku_values); session.add(sku); session.flush(); report.inserted["skus"] += 1
        else:
            _replace_if_owned(sku, sku_values, seed, report, "skus", replace_managed_seed)
        inventory = session.get(CatalogInventory, sku.id)
        if inventory is None:
            session.add(CatalogInventory(sku_id=sku.id, on_hand_quantity=sku_row["inventory"], reserved_quantity=0, version=0)); report.inserted["inventory"] += 1
        else:
            report.skipped["inventory"] += 1
    session.flush()
    report.dangling_legacy_ids = _legacy_mapping_report(session, seed["products"])
    if dry_run:
        session.rollback()
    return report


def print_report(report: SeedReport, *, replace_managed_seed: bool) -> None:
    print(f"插入：{report.inserted}；跳过：{report.skipped}；更新：{report.updated}")
    print(f"dangling legacy mapping：{report.dangling_legacy_ids}")


def run_seed(*, path: Path = DEFAULT_CATALOG_PATH, replace_managed_seed: bool = False, dry_run: bool = False, session_factory: Callable[[], Session] | None = None) -> SeedReport:
    if session_factory is None:
        from app.db.session import SessionLocal
        session_factory = SessionLocal
    session = session_factory()
    try:
        print("变更计划：" + ("replace managed seed" if replace_managed_seed else "insert missing only"))
        report = seed_catalog(session, load_catalog_seed(path), replace_managed_seed=replace_managed_seed, dry_run=dry_run)
        print_report(report, replace_managed_seed=replace_managed_seed)
        if not dry_run: session.commit()
        return report
    except Exception:
        session.rollback(); raise
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the independent ShopMind catalog.")
    parser.add_argument("--replace-managed-seed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data", type=Path, default=DEFAULT_CATALOG_PATH)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_seed(path=args.data, replace_managed_seed=args.replace_managed_seed, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
