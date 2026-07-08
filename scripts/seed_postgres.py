"""Seed PostgreSQL structured business tables from TechHub JSON data."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.models import Customer, Order, OrderItem, Product


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "structured"
SEED_FILENAMES = {
    "customers": "customers.json",
    "products": "products.json",
    "orders": "orders.json",
    "order_items": "order_items.json",
}


@dataclass(frozen=True)
class SeedData:
    customers: list[dict[str, Any]]
    products: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    order_items: list[dict[str, Any]]


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list.")
    return data


def load_seed_data(data_dir: Path = DEFAULT_DATA_DIR) -> SeedData:
    """Load seed JSON files without touching PostgreSQL."""
    data_dir = Path(data_dir)
    loaded = {
        name: _load_json_list(data_dir / filename)
        for name, filename in SEED_FILENAMES.items()
    }
    return SeedData(**loaded)


def get_seed_counts(seed_data: SeedData) -> dict[str, int]:
    """Return row counts for each seed collection."""
    return {
        "customers": len(seed_data.customers),
        "products": len(seed_data.products),
        "orders": len(seed_data.orders),
        "order_items": len(seed_data.order_items),
    }


def print_seed_counts(seed_data: SeedData) -> None:
    counts = get_seed_counts(seed_data)
    for name, filename in SEED_FILENAMES.items():
        print(f"读取 {filename}：{counts[name]} 条")


def _parse_optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _normalize_product(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["in_stock"] = bool(normalized["in_stock"])
    return normalized


def _normalize_order(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["order_date"] = date.fromisoformat(normalized["order_date"])
    normalized["shipped_date"] = _parse_optional_date(normalized.get("shipped_date"))
    return normalized


def _merge_rows(
    session: Session,
    model: type,
    rows: list[dict[str, Any]],
    normalizer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> None:
    for row in rows:
        values = normalizer(row) if normalizer else row
        session.merge(model(**values))


def clear_seed_tables(session: Session) -> None:
    """Clear seed-owned tables in reverse foreign-key order."""
    for model in (OrderItem, Order, Product, Customer):
        session.execute(model.__table__.delete())


def seed_database(
    seed_data: SeedData,
    *,
    clear: bool = False,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Write structured seed data to PostgreSQL."""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    session = session_factory()
    try:
        if clear:
            clear_seed_tables(session)
            print("已清空 customers/products/orders/order_items 表")

        _merge_rows(session, Customer, seed_data.customers)
        print(f"导入 customers：{len(seed_data.customers)} 条")

        _merge_rows(session, Product, seed_data.products, _normalize_product)
        print(f"导入 products：{len(seed_data.products)} 条")

        _merge_rows(session, Order, seed_data.orders, _normalize_order)
        print(f"导入 orders：{len(seed_data.orders)} 条")

        _merge_rows(session, OrderItem, seed_data.order_items)
        print(f"导入 order_items：{len(seed_data.order_items)} 条")

        session.commit()
        print("seed 完成")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_seed(
    *,
    clear: bool = False,
    dry_run: bool = False,
    data_dir: Path = DEFAULT_DATA_DIR,
    session_factory: Callable[[], Session] | None = None,
) -> SeedData:
    seed_data = load_seed_data(data_dir)
    print_seed_counts(seed_data)

    if dry_run:
        print("dry-run：未写入 PostgreSQL")
        return seed_data

    seed_database(seed_data, clear=clear, session_factory=session_factory)
    return seed_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed PostgreSQL structured business tables from JSON files."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="先清空 customers/products/orders/order_items 表再导入。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将导入的数据数量，不写数据库。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_seed(clear=args.clear, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
