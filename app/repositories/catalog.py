"""Synchronous Catalog repositories.  Callers own transaction boundaries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import AttributeDefinition, CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.models import Product
from app.schemas.catalog import (
    CatalogAttributeDefinition,
    CatalogIdentifierResolution,
    CatalogSkuCandidate,
)


def list_active_skus(
    session: Session,
    *,
    category_code: str,
) -> list[CatalogSkuCandidate]:
    statement = (
        select(CatalogSku, CatalogProduct, CatalogInventory)
        .join(CatalogProduct, CatalogSku.product_id == CatalogProduct.id)
        .join(CatalogInventory, CatalogInventory.sku_id == CatalogSku.id)
        .join(CatalogProduct.category)
        .where(
            CatalogProduct.sale_status == "active",
            CatalogSku.sale_status == "active",
            CatalogProduct.category.has(code=category_code, status="active"),
            CatalogInventory.on_hand_quantity > CatalogInventory.reserved_quantity,
        )
        .order_by(CatalogSku.sku_code.asc())
    )
    rows = session.execute(statement).all()
    definitions = list_catalog_attribute_definitions(session, category_code=category_code)
    return [
        _candidate(sku, product, inventory, definitions=definitions)
        for sku, product, inventory in rows
    ]


def list_active_laptop_skus(session: Session) -> list[CatalogSkuCandidate]:
    """Backward-compatible Laptop retrieval wrapper."""

    return list_active_skus(session, category_code="laptop")


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


def resolve_catalog_identifier(
    session: Session, identifier: str
) -> CatalogIdentifierResolution:
    """Resolve an untyped legacy identifier without namespace precedence."""

    raw = identifier.strip()
    if not raw:
        return CatalogIdentifierResolution(status="not_found", code="catalog_not_found")

    sku_hits = list(
        session.scalars(select(CatalogSku).where(CatalogSku.sku_code == raw)).all()
    )
    legacy_product_hits = list(
        session.scalars(
            select(CatalogProduct).where(CatalogProduct.legacy_product_id == raw)
        ).all()
    )
    product_code_hits = list(
        session.scalars(select(CatalogProduct).where(CatalogProduct.product_code == raw)).all()
    )

    matched_namespaces: list[str] = []
    if sku_hits:
        matched_namespaces.append("sku_code")
    if legacy_product_hits:
        matched_namespaces.append("legacy_product_id")
    if product_code_hits:
        matched_namespaces.append("product_code")
    if not matched_namespaces:
        return CatalogIdentifierResolution(status="not_found", code="catalog_not_found")

    concrete_targets: set[tuple[UUID, UUID]] = {
        (sku.product_id, sku.id) for sku in sku_hits
    }
    product_hits = [*legacy_product_hits, *product_code_hits]
    product_sku_ids: dict[UUID, list[UUID]] = {}
    for product in product_hits:
        sku_ids = list(
            session.scalars(
                select(CatalogSku.id)
                .where(CatalogSku.product_id == product.id)
                .order_by(CatalogSku.id.asc())
            ).all()
        )
        product_sku_ids[product.id] = sku_ids
        concrete_targets.update((product.id, sku_id) for sku_id in sku_ids)

    identity_product_ids = {sku.product_id for sku in sku_hits}
    identity_product_ids.update(product.id for product in product_hits)
    product_ids = {product_id for product_id, _ in concrete_targets}
    has_zero_sku_product = any(len(sku_ids) == 0 for sku_ids in product_sku_ids.values())
    if has_zero_sku_product:
        if len(identity_product_ids) > 1:
            return CatalogIdentifierResolution(
                status="ambiguous",
                code="catalog_identifier_ambiguous",
                matched_namespaces=tuple(matched_namespaces),
                target_count=len(concrete_targets),
            )
        return CatalogIdentifierResolution(
            status="not_found",
            code="catalog_not_found",
            matched_namespaces=tuple(matched_namespaces),
            target_count=0,
        )

    has_product_ambiguity = any(len(sku_ids) > 1 for sku_ids in product_sku_ids.values())
    if has_product_ambiguity:
        code = "catalog_identifier_ambiguous" if len(product_ids) > 1 else "sku_ambiguous"
        return CatalogIdentifierResolution(
            status="ambiguous",
            code=code,
            matched_namespaces=tuple(matched_namespaces),
            target_count=len(concrete_targets),
        )

    if len(concrete_targets) != 1 or len(product_ids) != 1:
        return CatalogIdentifierResolution(
            status="ambiguous",
            code="catalog_identifier_ambiguous",
            matched_namespaces=tuple(matched_namespaces),
            target_count=len(concrete_targets),
        )

    product_id, sku_id = next(iter(concrete_targets))
    return CatalogIdentifierResolution(
        status="resolved",
        product_id=product_id,
        sku_id=sku_id,
        matched_namespaces=tuple(matched_namespaces),
        target_count=1,
    )


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
    product = session.get(CatalogProduct, product_id)
    category_code = product.category.code if product is not None and product.category else "laptop"
    definitions = list_catalog_attribute_definitions(session, category_code=category_code)
    return [
        _candidate(sku, product, inventory, definitions=definitions)
        for sku, product, inventory in session.execute(statement).all()
    ]
