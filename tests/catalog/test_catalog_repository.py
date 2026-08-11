from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.catalog import models as catalog_models  # noqa: F401
from app.catalog.models import CatalogInventory, CatalogProduct, CatalogSku
from app.db import models as legacy_models  # noqa: F401
from app.db.base import Base
from app.db.models import Product
from app.repositories.catalog import list_active_laptop_skus, reconcile_legacy_mappings, resolve_legacy_product
from scripts.seed_shopmind_catalog import load_catalog_seed, seed_catalog


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_catalog_repository_reads_only_active_available_laptop_skus() -> None:
    session = make_session(); seed_catalog(session, load_catalog_seed()); session.commit()
    candidate = session.scalars(select(CatalogSku)).first()
    session.get(CatalogInventory, candidate.id).reserved_quantity = session.get(CatalogInventory, candidate.id).on_hand_quantity
    session.commit()
    rows = list_active_laptop_skus(session)
    assert len(rows) == 4
    assert all(row.currency == "CNY" and row.available_quantity > 0 for row in rows)


def test_legacy_mapping_resolution_and_reconciliation_are_read_only() -> None:
    session = make_session(); seed_catalog(session, load_catalog_seed()); session.add(Product(product_id="TECH-LAP-001", name="Legacy", category="Laptops", price=1, in_stock=True)); session.commit()
    resolved = resolve_legacy_product(session, "TECH-LAP-001")
    report = reconcile_legacy_mappings(session)
    assert resolved is not None
    assert report["resolved"] == ["TECH-LAP-001"]
    assert "TECH-LAP-002" in report["dangling"]
