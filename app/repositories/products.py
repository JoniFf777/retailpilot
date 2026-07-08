"""Product repository functions backed by SQLAlchemy sessions."""

from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Product


def _money_to_float(value: Decimal | float | int) -> float:
    return float(value)


def product_to_dict(product: Product) -> dict[str, Any]:
    return {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category,
        "price": _money_to_float(product.price),
        "in_stock": bool(product.in_stock),
    }


def search_products(
    session: Session,
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = True,
    limit: int = 5,
) -> list[dict[str, Any]]:
    statement = select(Product)

    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(Product.name.ilike(pattern), Product.category.ilike(pattern))
        )

    if category:
        statement = statement.where(
            func.lower(Product.category) == category.strip().lower()
        )

    if max_price is not None:
        statement = statement.where(Product.price <= max_price)

    if in_stock_only:
        statement = statement.where(Product.in_stock.is_(True))

    statement = statement.order_by(Product.price.asc(), Product.name.asc()).limit(limit)
    return [product_to_dict(product) for product in session.scalars(statement).all()]


def get_product_detail(
    session: Session, product_identifier: str
) -> dict[str, Any] | None:
    identifier = product_identifier.strip()
    product = session.get(Product, identifier)
    if product is not None:
        return product_to_dict(product)

    statement = (
        select(Product)
        .where(Product.name.ilike(f"%{identifier}%"))
        .order_by(Product.price.asc(), Product.name.asc())
        .limit(1)
    )
    product = session.scalars(statement).first()
    return product_to_dict(product) if product else None


def get_products_by_ids(
    session: Session, product_identifiers: Sequence[str]
) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for identifier in product_identifiers:
        product = get_product_detail(session, identifier)
        if product is not None:
            products.append(product)
    return products
