from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.catalog import models as catalog_models  # noqa: F401
from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db import models as legacy_models  # noqa: F401
from app.db.base import Base


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_catalog_models_are_registered_in_shared_metadata() -> None:
    assert {"shopmind_categories", "shopmind_attribute_definitions", "shopmind_products", "shopmind_product_skus", "shopmind_inventory"}.issubset(Base.metadata.tables)


def test_catalog_uuid_and_unique_business_codes_work_on_sqlite() -> None:
    session = make_session()
    category = CatalogCategory(code="laptop", name="Laptop", status="active")
    session.add(category); session.flush()
    product = CatalogProduct(product_code="LAP-ONE", category_id=category.id, brand="Test", name="One", sale_status="active")
    session.add(product); session.flush()
    session.add(CatalogSku(product_id=product.id, sku_code="LAP-ONE-BASE", name="Base", money_amount=Decimal("1.00"), currency="CNY", sale_status="active"))
    session.commit()
    session.add(CatalogProduct(product_code="LAP-ONE", category_id=category.id, brand="Test", name="Duplicate", sale_status="active"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_money_and_inventory_constraints_reject_invalid_values() -> None:
    session = make_session()
    category = CatalogCategory(code="laptop", name="Laptop", status="active")
    session.add(category); session.flush()
    product = CatalogProduct(product_code="LAP-CHECK", category_id=category.id, brand="Test", name="Check", sale_status="active")
    session.add(product); session.flush()
    bad_sku = CatalogSku(product_id=product.id, sku_code="LAP-CHECK-BAD", name="Bad", money_amount=Decimal("0"), currency="cny", sale_status="active")
    session.add(bad_sku)
    with pytest.raises(IntegrityError): session.flush()
    session.rollback()
    category = CatalogCategory(code="laptop", name="Laptop", status="active")
    session.add(category); session.flush()
    product = CatalogProduct(product_code="LAP-INVENTORY", category_id=category.id, brand="Test", name="Inventory", sale_status="active")
    session.add(product); session.flush()
    sku = CatalogSku(product_id=product.id, sku_code="LAP-INVENTORY-BASE", name="Base", money_amount=Decimal("1.00"), currency="CNY", sale_status="active")
    session.add(sku); session.flush()
    session.add(CatalogInventory(sku_id=sku.id, on_hand_quantity=1, reserved_quantity=2, version=0))
    with pytest.raises(IntegrityError): session.flush()
