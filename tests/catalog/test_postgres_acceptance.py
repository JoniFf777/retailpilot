"""Phase 1A real-PostgreSQL acceptance checks in disposable schemas."""

from __future__ import annotations

import copy
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1 for Catalog PostgreSQL acceptance", allow_module_level=True)

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.core.settings import get_settings
from app.db.models import Product
from app.repositories.catalog import (
    get_catalog_product, get_catalog_sku, list_active_laptop_skus,
    list_alternative_skus, reconcile_legacy_mappings, resolve_legacy_product,
)
from app.recommendation.service import build_laptop_recommendation
from app.recommendation.constraints import parse_laptop_constraints
from app.repositories.documents import (
    search_policy_documents,
    search_product_documents_for_product_ids,
)
from app.schemas.recommendation import LaptopConstraints
from scripts.seed_shopmind_catalog import load_catalog_seed, seed_catalog


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def catalog_session():
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    schema = f"shopmind_catalog_acceptance_{uuid4().hex}"
    connection = engine.connect()
    session = None
    try:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.commit()
        print({"acceptance_schema": schema, "lifecycle": "create → stamp/migrate/seed → drop cascade"})
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".alembic_version '
                '(version_num VARCHAR(32) NOT NULL PRIMARY KEY)'
            )
        )
        connection.commit()
        connection.execute(text(f'SET search_path TO "{schema}", public'))
        connection.commit()
        command.stamp(_alembic(connection), "0007_governance_audit")
        command.upgrade(_alembic(connection), "0009_shopmind_skus_inventory")
        session = sessionmaker(bind=connection, expire_on_commit=False)()
        yield session, engine, schema
    finally:
        if session is not None:
            session.close()
        connection.execute(text("SET search_path TO public"))
        connection.commit()
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        connection.commit()
        connection.close()
        engine.dispose()


def _category(session, code: str = "laptop", parent_id=None):
    category = CatalogCategory(code=code, name=code, status="active", parent_id=parent_id)
    session.add(category); session.flush()
    return category


def _product_with_sku(session, category, code: str, *, legacy_id: str | None = None, amount: Decimal = Decimal("1.00"), currency: str = "CNY"):
    product = CatalogProduct(product_code=f"P-{code}", legacy_product_id=legacy_id, category_id=category.id, brand="Test", name=code, sale_status="active")
    session.add(product); session.flush()
    sku = CatalogSku(product_id=product.id, sku_code=f"S-{code}", name=code, money_amount=amount, currency=currency, sale_status="active")
    session.add(sku); session.flush()
    return product, sku


def test_real_postgres_catalog_constraints_and_no_legacy_fk(catalog_session) -> None:
    session, _, schema = catalog_session
    root = _category(session)
    session.add(CatalogCategory(code="laptop", name="duplicate", status="active"))
    with pytest.raises(IntegrityError): session.flush()
    session.rollback()
    root = _category(session)
    first_parent = _category(session, "first-parent")
    second_parent = _category(session, "second-parent")
    _category(session, "child", first_parent.id)
    session.add(CatalogCategory(code="child", name="duplicate child", status="active", parent_id=first_parent.id))
    with pytest.raises(IntegrityError): session.flush()
    session.rollback()
    root = _category(session)
    first_parent = _category(session, "first-parent")
    second_parent = _category(session, "second-parent")
    _category(session, "child", first_parent.id); _category(session, "child", second_parent.id)
    product, sku = _product_with_sku(session, root, "one", legacy_id="TECH-LAP-001")
    session.add(CatalogProduct(product_code="P-one", category_id=root.id, brand="Test", name="duplicate", sale_status="active"))
    with pytest.raises(IntegrityError): session.flush()
    session.rollback()
    root = _category(session)
    product, sku = _product_with_sku(session, root, "one", legacy_id="TECH-LAP-001")
    session.add(CatalogProduct(product_code="P-two", legacy_product_id="TECH-LAP-001", category_id=root.id, brand="Test", name="duplicate legacy", sale_status="active"))
    with pytest.raises(IntegrityError): session.flush()
    session.rollback()
    root = _category(session)
    _, first_null = _product_with_sku(session, root, "null-one")
    _, second_null = _product_with_sku(session, root, "null-two")
    session.add(CatalogSku(product_id=second_null.product_id, sku_code=first_null.sku_code, name="duplicate sku", money_amount=Decimal("1.00"), currency="CNY", sale_status="active"))
    with pytest.raises(IntegrityError): session.flush()
    session.rollback()
    constraints = session.execute(text("""
        SELECT c.conrelid::regclass::text
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE c.contype = 'f' AND n.nspname = :schema AND c.confrelid = 'public.products'::regclass
    """), {"schema": schema}).all()
    assert constraints == []


def test_real_postgres_money_and_inventory_checks(catalog_session) -> None:
    session, _, _ = catalog_session
    category = _category(session)
    for amount, currency in ((Decimal("0"), "CNY"), (Decimal("1"), "CN"), (Decimal("1"), "cny")):
        product = CatalogProduct(product_code=f"P-{uuid4()}", category_id=category.id, brand="Test", name="bad", sale_status="active")
        session.add(product); session.flush()
        session.add(CatalogSku(product_id=product.id, sku_code=f"S-{uuid4()}", name="bad", money_amount=amount, currency=currency, sale_status="active"))
        with pytest.raises(IntegrityError): session.flush()
        session.rollback(); category = _category(session)
    product, sku = _product_with_sku(session, category, "precision", amount=Decimal("1.234"))
    session.flush(); session.refresh(sku)
    assert sku.money_amount == Decimal("1.23")
    for on_hand, reserved, version in ((-1, 0, 0), (1, -1, 0), (1, 2, 0), (1, 0, -1)):
        product, sku = _product_with_sku(session, category, str(uuid4()))
        session.add(CatalogInventory(sku_id=sku.id, on_hand_quantity=on_hand, reserved_quantity=reserved, version=version))
        with pytest.raises(IntegrityError): session.flush()
        session.rollback(); category = _category(session)
    product, sku = _product_with_sku(session, category, "zero-stock")
    session.add(CatalogInventory(sku_id=sku.id, on_hand_quantity=0, reserved_quantity=0, version=0)); session.flush()


def test_real_postgres_seed_repository_and_demo_acceptance(catalog_session) -> None:
    session, engine, _ = catalog_session
    seed = load_catalog_seed()
    first = seed_catalog(session, seed); session.commit()
    second = seed_catalog(session, seed); session.commit()
    assert first.inserted == {"categories": 1, "attributes": 7, "products": 5, "skus": 5, "inventory": 5}
    assert second.inserted == {"categories": 0, "attributes": 0, "products": 0, "skus": 0, "inventory": 0}
    assert second.skipped["products"] == 5 and second.skipped["skus"] == 5
    legacy_ids = sorted({row["legacy_product_id"] for row in seed["products"] if row.get("legacy_product_id")})
    existing_legacy_ids = set(session.scalars(select(Product.product_id).where(Product.product_id.in_(legacy_ids))).all())
    expected_dangling = sorted(set(legacy_ids) - existing_legacy_ids)
    assert first.dangling_legacy_ids == expected_dangling
    product = session.scalar(select(CatalogProduct).where(CatalogProduct.product_code == "LAP-HP-PAV-15"))
    sku = session.scalar(select(CatalogSku).where(CatalogSku.product_id == product.id))
    inventory = session.get(CatalogInventory, sku.id)
    product.name = "Manual managed name"; inventory.on_hand_quantity = 3; session.commit()
    regular = seed_catalog(session, seed); session.commit()
    assert product.name == "Manual managed name" and inventory.on_hand_quantity == 3
    assert regular.skipped["products"] == 5
    replacement = seed_catalog(session, seed, replace_managed_seed=True); session.commit()
    assert product.name == "HP Pavilion 15" and inventory.on_hand_quantity == 3
    product.managed_by_seed = False; product.name = "Manual unmanaged name"; session.commit()
    nonmanaged = seed_catalog(session, seed, replace_managed_seed=True); session.commit()
    assert product.name == "Manual unmanaged name" and nonmanaged.skipped["products"] >= 1
    before = session.scalar(select(CatalogProduct).count()) if False else len(session.scalars(select(CatalogProduct)).all())
    invalid = copy.deepcopy(seed); invalid["products"].append({**copy.deepcopy(seed["products"][0]), "product_code": "LAP-FAIL-ROLLBACK"})
    with pytest.raises(IntegrityError): seed_catalog(session, invalid)
    session.rollback()
    assert len(session.scalars(select(CatalogProduct)).all()) == before
    product.managed_by_seed = True
    product.name = "HP Pavilion 15"
    inventory.on_hand_quantity = 25
    session.commit()
    mapping = reconcile_legacy_mappings(session)
    assert mapping == {"resolved": sorted(existing_legacy_ids), "dangling": expected_dangling}
    candidates = list_active_laptop_skus(session)
    assert len(candidates) == 5
    query_count = 0
    def count_sql(*_):
        nonlocal query_count
        query_count += 1
    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        first_candidate = candidates[0]
        assert get_catalog_product(session, first_candidate.product_id) is not None
        assert get_catalog_sku(session, first_candidate.sku_id) is not None
        # Catalog resolution is the compatibility bridge and remains available
        # even when the old Product row is dangling; reconciliation reports the
        # separate legacy-row health explicitly.
        assert resolve_legacy_product(session, "TECH-LAP-001") is not None
        list_active_laptop_skus(session)
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)
    # Catalog candidate retrieval intentionally adds one ordered
    # AttributeDefinition query; it remains constant (no per-SKU N+1).
    assert query_count == 5
    selected_candidate = next(row for row in candidates if row.product_code == "LAP-HP-PAV-15")
    selected_product = get_catalog_product(session, selected_candidate.product_id)
    alternative = CatalogSku(product_id=selected_product.id, sku_code="LAP-ALT-POSTGRES", name="Alternative", money_amount=Decimal("9999.00"), currency="CNY", sale_status="active")
    session.add(alternative); session.flush()
    session.add(CatalogInventory(sku_id=alternative.id, on_hand_quantity=1, reserved_quantity=0, version=0)); session.commit()
    assert [item.sku_code for item in list_alternative_skus(session, selected_product.id, selected_candidate.sku_id)] == ["LAP-ALT-POSTGRES"]
    transient = CatalogCategory(code="rollback-only", name="rollback-only", status="active")
    session.add(transient); session.flush()
    list_active_laptop_skus(session)
    session.rollback()
    assert session.scalar(select(CatalogCategory).where(CatalogCategory.code == "rollback-only")) is None
    product = session.scalar(select(CatalogProduct).where(CatalogProduct.product_code == "LAP-DELL-XPS-13"))
    sku = session.scalar(select(CatalogSku).where(CatalogSku.product_id == product.id))
    sku.sale_status = "inactive"; session.commit()
    session.expire_all()
    active_after_inactive = list_active_laptop_skus(session)
    assert all(row.product_code != "LAP-DELL-XPS-13" for row in active_after_inactive)
    sku.sale_status = "active"; session.get(CatalogInventory, sku.id).reserved_quantity = session.get(CatalogInventory, sku.id).on_hand_quantity; session.commit(); session.expire_all()
    assert all(row.product_code != "LAP-DELL-XPS-13" for row in list_active_laptop_skus(session))
    demo_query = "预算 6000 元以内，主要用于 Java 开发，偶尔剪视频，内存至少 16GB，希望尽量轻。"
    constraints = parse_laptop_constraints(demo_query)
    result = build_laptop_recommendation(candidates, constraints, demo_query)
    repeat = build_laptop_recommendation(candidates, constraints, demo_query)
    assert result.model_dump(mode="json") == repeat.model_dump(mode="json")
    assert result.outcome == "recommended"
    assert [item.sku_name for item in result.recommendations] == ["16GB / 512GB"]
    assert result.recommendations[0].score == 70
    assert result.recommendations[0].alternative_skus == []
    print({"first_seed": first.__dict__, "second_seed": second.__dict__, "mapping": mapping, "demo_candidate_count": len(candidates), "demo_hard_match_count": len(result.recommendations), "demo": result.model_dump(mode="json"), "repository_sql_count": query_count})


def test_real_postgres_top_k_legacy_whitelist_rag_and_policy_read(catalog_session) -> None:
    """Exercise the actual pgvector repository with a Catalog-selected whitelist."""

    session, _, _ = catalog_session
    seed_catalog(session, load_catalog_seed())
    session.commit()
    candidates = list_active_laptop_skus(session)
    ranking = build_laptop_recommendation(
        candidates,
        parse_laptop_constraints("预算 6000 元以内，Java 开发，内存至少 16GB"),
        "预算 6000 元以内，Java 开发，内存至少 16GB",
    )
    top_k_ids = {
        candidate.legacy_product_id
        for candidate in candidates
        if candidate.legacy_product_id
        and any(candidate.sku_id == recommendation.sku_id for recommendation in ranking.recommendations)
    }
    dimension = session.scalar(
        text("SELECT vector_dims(embedding) FROM public.documents WHERE embedding IS NOT NULL LIMIT 1")
    )
    assert dimension and dimension > 0
    embedding = [0.0] * int(dimension)
    product_documents = search_product_documents_for_product_ids(
        session, embedding, product_ids=sorted(top_k_ids), k=6
    )
    policy_documents = search_policy_documents(session, embedding, k=2)
    assert all(document["product_id"] in top_k_ids for document in product_documents)
    assert len(policy_documents) <= 2
    print({"top_k_legacy_product_ids": sorted(top_k_ids), "exact_product_rag_count": len(product_documents), "policy_rag_count": len(policy_documents)})
