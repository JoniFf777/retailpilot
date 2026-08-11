from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.catalog import models as catalog_models  # noqa: F401
from app.catalog.models import CatalogInventory, CatalogProduct, CatalogSku
from app.db import models as legacy_models  # noqa: F401
from app.db.base import Base
from app.db.models import Product
from scripts.seed_shopmind_catalog import load_catalog_seed, run_seed, seed_catalog


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_catalog_seed_is_idempotent_and_does_not_modify_legacy_products() -> None:
    session = make_session()
    session.add(Product(product_id="TECH-LAP-001", name="Legacy name", category="Laptops", price=1, in_stock=True)); session.commit()
    seed = load_catalog_seed()
    first = seed_catalog(session, seed); session.commit()
    second = seed_catalog(session, seed); session.commit()
    assert first.inserted["products"] == 5
    assert second.inserted["products"] == 0
    assert session.get(Product, "TECH-LAP-001").name == "Legacy name"
    assert len(session.scalars(select(CatalogProduct)).all()) == 5
    assert len(session.scalars(select(CatalogSku)).all()) == 5


def test_replace_only_updates_managed_seed_and_never_resets_inventory() -> None:
    session = make_session(); seed = load_catalog_seed()
    seed_catalog(session, seed); session.commit()
    product = session.scalars(select(CatalogProduct)).first(); sku = session.scalars(select(CatalogSku)).first()
    product.name = "Manual product"; product.managed_by_seed = False
    inventory = session.get(CatalogInventory, sku.id); inventory.on_hand_quantity = 1; session.commit()
    report = seed_catalog(session, seed, replace_managed_seed=True); session.commit()
    assert product.name == "Manual product"
    assert session.get(CatalogInventory, sku.id).on_hand_quantity == 1
    assert report.skipped["inventory"] == 5


def test_seed_reports_dangling_legacy_mapping_without_rejecting_catalog_product() -> None:
    session = make_session(); report = seed_catalog(session, load_catalog_seed()); session.commit()
    assert "TECH-LAP-001" in report.dangling_legacy_ids
    assert session.scalar(select(CatalogProduct).where(CatalogProduct.legacy_product_id == "TECH-LAP-001")) is not None


def test_seed_script_prints_change_plan_before_dry_run(capsys) -> None:
    session = make_session()
    run_seed(dry_run=True, session_factory=lambda: session)
    output = capsys.readouterr().out
    assert output.index("变更计划") < output.index("插入：")
    assert session.scalars(select(CatalogProduct)).all() == []
