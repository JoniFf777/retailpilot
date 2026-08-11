"""Synchronous Catalog repositories.  Callers own transaction boundaries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import AttributeDefinition, CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.models import Product
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate


def list_active_laptop_skus(session: Session) -> list[CatalogSkuCandidate]:
    statement = (
        select(CatalogSku, CatalogProduct, CatalogInventory)
        .join(CatalogProduct, CatalogSku.product_id == CatalogProduct.id)
        .join(CatalogInventory, CatalogInventory.sku_id == CatalogSku.id)
        .join(CatalogProduct.category)
        .where(
            CatalogProduct.sale_status == "active",
            CatalogSku.sale_status == "active",
            CatalogProduct.category.has(code="laptop", status="active"),
            CatalogInventory.on_hand_quantity > CatalogInventory.reserved_quantity,
        )
        .order_by(CatalogSku.sku_code.asc())
    )
    rows = session.execute(statement).all()
    definitions = list_catalog_attribute_definitions(session, category_code="laptop")
    return [
        _candidate(sku, product, inventory, definitions=definitions)
        for sku, product, inventory in rows
    ]


def list_catalog_attribute_definitions(
    session: Session,
    *,
    category_code: str,
) -> list[CatalogAttributeDefinition]:
    """Return ordered, explicitly defined fields for one catalog category."""

    statement = (
        select(AttributeDefinition)
        .join(CatalogCategory, AttributeDefinition.category_id == CatalogCategory.id)
        .where(CatalogCategory.code == category_code, CatalogCategory.status == "active")
        .order_by(AttributeDefinition.display_order.asc(), AttributeDefinition.code.asc())
    )
    return [
        CatalogAttributeDefinition(
            code=item.code,
            name=item.name,
            scope=item.scope,
            data_type=item.data_type,
            unit=item.unit,
            comparable=item.comparable,
            display_order=item.display_order,
        )
        for item in session.scalars(statement).all()
    ]


def _candidate(
    sku: CatalogSku,
    product: CatalogProduct,
    inventory: CatalogInventory,
    *,
    definitions: list[CatalogAttributeDefinition] | None = None,
) -> CatalogSkuCandidate:
    return CatalogSkuCandidate(
        product_id=product.id, product_code=product.product_code, legacy_product_id=product.legacy_product_id,
        product_name=product.name, brand=product.brand, sku_id=sku.id, sku_code=sku.sku_code,
        sku_name=sku.name, money_amount=sku.money_amount, currency=sku.currency,
        product_attributes=product.attributes_json, variant_attributes=sku.variant_attributes_json,
        attribute_definitions=definitions or [],
        available_quantity=inventory.on_hand_quantity - inventory.reserved_quantity,
    )


def get_catalog_product(session: Session, product_id: UUID) -> CatalogProduct | None:
    return session.get(CatalogProduct, product_id)


def get_catalog_sku(session: Session, sku_id: UUID) -> CatalogSku | None:
    return session.get(CatalogSku, sku_id)


def resolve_legacy_product(session: Session, legacy_product_id: str) -> CatalogProduct | None:
    return session.scalar(select(CatalogProduct).where(CatalogProduct.legacy_product_id == legacy_product_id))


def reconcile_legacy_mappings(session: Session) -> dict[str, list[str]]:
    """Report mapping health without changing either the legacy or Catalog table."""
    catalog_ids = set(session.scalars(select(CatalogProduct.legacy_product_id).where(CatalogProduct.legacy_product_id.is_not(None))).all())
    legacy_ids = set(
        session.scalars(
            select(Product.product_id).where(Product.product_id.in_(catalog_ids))
        ).all()
    ) if catalog_ids else set()
    return {"resolved": sorted(legacy_ids), "dangling": sorted(catalog_ids - legacy_ids)}


def list_alternative_skus(session: Session, product_id: UUID, exclude_sku_id: UUID) -> list[CatalogSkuCandidate]:
    statement = (
        select(CatalogSku, CatalogProduct, CatalogInventory)
        .join(CatalogProduct, CatalogSku.product_id == CatalogProduct.id)
        .join(CatalogInventory, CatalogInventory.sku_id == CatalogSku.id)
        .where(CatalogSku.product_id == product_id, CatalogSku.id != exclude_sku_id,
               CatalogSku.sale_status == "active", CatalogInventory.on_hand_quantity > CatalogInventory.reserved_quantity)
        .order_by(CatalogSku.money_amount.asc(), CatalogSku.sku_code.asc())
    )
    definitions = list_catalog_attribute_definitions(session, category_code="laptop")
    return [
        _candidate(sku, product, inventory, definitions=definitions)
        for sku, product, inventory in session.execute(statement).all()
    ]
