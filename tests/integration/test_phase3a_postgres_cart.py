"""Phase 3A direct Cart acceptance against a real PostgreSQL database.

Run with ``RUN_POSTGRES_INTEGRATION=1`` and an isolated ``TEST_DATABASE_URL``.
Each test uses unique catalog/user identifiers and never truncates shared data.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.cart.models import ShopMindCartItem
from app.core.settings import get_settings
from app.db.models import AgentRun, ConversationThread
from app.repositories.shopmind_cart import get_cart_response, upsert_cart_item
from app.schemas.recommendation import AvailabilityView, LaptopConstraints, Money, Recommendation, RecommendationResult
from app.services.cart import CartServiceError, update_cart_item
from app.services.pending_actions import confirm_add_to_cart, create_add_to_cart_pending_action


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for real PostgreSQL acceptance",
)


@pytest.fixture(scope="module")
def db_factory():
    engine_url = get_settings().test_database_url
    schema = f"shopmind_phase3a_cart_{uuid4().hex}"
    bootstrap = create_engine(engine_url, pool_pre_ping=True)
    with bootstrap.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".alembic_version '
                '(version_num VARCHAR(32) NOT NULL PRIMARY KEY)'
            )
        )
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".pending_actions (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    thread_id VARCHAR,
                    action_type VARCHAR(64) NOT NULL,
                    payload_json JSONB NOT NULL,
                    risk_class VARCHAR NOT NULL DEFAULT 'high',
                    preview_text TEXT NOT NULL DEFAULT '',
                    status VARCHAR(32) NOT NULL,
                    expires_at TIMESTAMPTZ,
                    metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )'''
            )
        )
        connection.commit()
    bootstrap.dispose()
    engine = create_engine(engine_url, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_private_search_path(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    @event.listens_for(engine, "checkout")
    def _restore_private_search_path(dbapi_connection, _connection_record, _connection_proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    with engine.connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.stamp(config, "0007_governance_audit")
        command.upgrade(config, "0011_shopmind_cart")
    with engine.begin() as connection:
        ConversationThread.__table__.create(connection, checkfirst=True)
        AgentRun.__table__.create(connection, checkfirst=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def _seed_cart(factory: sessionmaker, *, user_id: str | None = None, quantity: int = 1, available: int = 10):
    session: Session = factory()
    user = user_id or f"phase3a-user-{uuid4().hex}"
    category = CatalogCategory(code=f"phase3a-{uuid4().hex[:10]}", name="Laptop", status="active")
    product = CatalogProduct(
        product_code=f"P3A-{uuid4().hex[:10]}", category=category, brand="ShopMind",
        name="Phase 3A Laptop", sale_status="active", attributes_json={},
    )
    sku = CatalogSku(
        product=product, sku_code=f"P3A-SKU-{uuid4().hex[:10]}", name="16GB",
        money_amount=Decimal("5999.00"), currency="CNY", sale_status="active", variant_attributes_json={},
    )
    inventory = CatalogInventory(sku=sku, on_hand_quantity=available, reserved_quantity=0, version=0)
    session.add_all([category, product, sku, inventory])
    session.flush()
    item = upsert_cart_item(session, user_id=user, sku_id=sku.id, quantity=quantity)
    session.commit()
    ids = (user, item.id, sku.id, product.id)
    session.close()
    return ids


def _seed_action(factory: sessionmaker):
    user, item_id, sku_id, product_id = _seed_cart(factory)
    session: Session = factory()
    thread_id = f"phase3a-thread-{uuid4().hex}"
    thread = ConversationThread(
        id=thread_id, user_id=user, client_thread_id=thread_id, status="active",
        metadata_json={}, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    product = session.get(CatalogProduct, product_id)
    sku = session.get(CatalogSku, sku_id)
    recommendation = RecommendationResult(
        outcome="recommended", ranking_policy_version="v1", request_summary="phase3a",
        structured_constraints=LaptopConstraints(),
        recommendations=[Recommendation(
            product_id=product.id, sku_id=sku.id, product_name=product.name, sku_name=sku.name,
            money=Money(amount="5999", currency="CNY"), specifications=[], score=90, score_breakdown=[],
            availability=AvailabilityView(sale_status="active", available_quantity=10, in_stock=True), reason="match",
        )],
    )
    run = AgentRun(
        id=f"phase3a-run-{uuid4().hex}", thread=thread, user_id=user, operation="chat", mode="multi",
        status="completed", request_id=uuid4().hex, trace_id=uuid4().hex, request_json={},
        result_json={"recommendation": recommendation.model_dump(mode="json")}, usage_json={},
        tool_call_records_json=[], metadata_json={}, started_at=datetime.now(timezone.utc),
    )
    session.add_all([thread, run])
    session.commit()
    action = create_add_to_cart_pending_action(
        session, user_id=user, thread_id=thread_id, source_run_id=run.id, sku_id=sku_id, quantity=1,
    )
    session.commit()
    session.close()
    return user, item_id, sku_id, action.pending_action_id, thread_id


def test_postgres_patch_boundaries_and_inventory_unchanged(db_factory):
    user, item_id, sku_id, _ = _seed_cart(db_factory, available=3)
    session: Session = db_factory()
    inventory_before = session.get(CatalogInventory, sku_id)
    before = (inventory_before.on_hand_quantity, inventory_before.reserved_quantity, inventory_before.version)
    result = update_cart_item(session, user_id=user, cart_item_id=item_id, expected_version=1, quantity=3)
    session.commit()
    assert result.item.quantity == 3 and result.item.version == 2
    inventory_after = session.get(CatalogInventory, sku_id)
    assert (inventory_after.on_hand_quantity, inventory_after.reserved_quantity, inventory_after.version) == before
    with pytest.raises(CartServiceError) as shortage:
        update_cart_item(session, user_id=user, cart_item_id=item_id, expected_version=2, quantity=4)
    assert shortage.value.code == "insufficient_inventory"
    session.rollback(); session.close()


def test_postgres_patch_rejects_inactive_and_missing_inventory(db_factory):
    user, item_id, sku_id, product_id = _seed_cart(db_factory, available=5)
    session: Session = db_factory()
    product = session.get(CatalogProduct, product_id)
    product.sale_status = "inactive"
    session.commit()
    with pytest.raises(CartServiceError) as inactive:
        update_cart_item(session, user_id=user, cart_item_id=item_id, expected_version=1, quantity=1)
    assert inactive.value.code == "product_inactive"
    session.rollback()

    product.sale_status = "active"
    session.delete(session.get(CatalogInventory, sku_id))
    session.commit()
    with pytest.raises(CartServiceError) as missing:
        update_cart_item(session, user_id=user, cart_item_id=item_id, expected_version=1, quantity=1)
    assert missing.value.code == "inventory_missing"
    session.rollback(); session.close()


def test_postgres_patch_flush_rollback_preserves_quantity(db_factory):
    user, item_id, _, _ = _seed_cart(db_factory, available=5)
    session: Session = db_factory()
    update_cart_item(session, user_id=user, cart_item_id=item_id, expected_version=1, quantity=2)
    session.rollback()
    session.close()
    check: Session = db_factory()
    item = check.get(ShopMindCartItem, item_id)
    assert item.quantity == 1 and item.version == 1
    check.close()


def test_postgres_patch_patch_serializes_on_cart_item(db_factory):
    user, item_id, _, _ = _seed_cart(db_factory, available=10)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker(quantity: int):
        session: Session = db_factory()
        barrier.wait()
        try:
            update_cart_item(session, user_id=user, cart_item_id=item_id, expected_version=1, quantity=quantity)
            session.commit(); outcomes.append("updated")
        except CartServiceError as exc:
            session.rollback(); outcomes.append(exc.code)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(2,)), threading.Thread(target=worker, args=(3,))]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=30)
    assert len(outcomes) == 2
    assert outcomes.count("updated") == 1
    assert outcomes.count("cart_version_conflict") == 1


def test_postgres_patch_vs_phase2_confirm_has_no_lost_update(db_factory):
    user, item_id, sku_id, action_id, thread_id = _seed_action(db_factory)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def patch_worker():
        session: Session = db_factory(); barrier.wait()
        try:
            update_cart_item(session, user_id=user, cart_item_id=item_id, expected_version=1, quantity=2)
            session.commit(); outcomes.append("patched")
        except CartServiceError as exc:
            session.rollback(); outcomes.append(exc.code)
        finally: session.close()

    def confirm_worker():
        session: Session = db_factory(); barrier.wait()
        try:
            confirm_add_to_cart(session, pending_action_id=action_id, user_id=user, thread_id=thread_id, expected_version=1)
            session.commit(); outcomes.append("confirmed")
        except Exception as exc:
            session.rollback(); outcomes.append(getattr(exc, "code", type(exc).__name__))
        finally: session.close()

    threads = [threading.Thread(target=patch_worker), threading.Thread(target=confirm_worker)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=30)
    assert len(outcomes) == 2
    assert set(outcomes).issubset({"patched", "confirmed", "cart_version_conflict"})
    check: Session = db_factory()
    item = check.get(ShopMindCartItem, item_id)
    assert item.quantity in {2, 3}
    check.close()


def test_postgres_cart_summary_and_owner_isolation(db_factory):
    user, item_id, sku_id, _ = _seed_cart(db_factory, quantity=2)
    session: Session = db_factory()
    own = get_cart_response(session, user_id=user)
    other = get_cart_response(session, user_id=f"other-{uuid4().hex}")
    assert own.item_count == 1 and own.total_quantity == 2 and own.subtotal.amount == "11998.00"
    assert other.items == [] and other.subtotal is None and other.currency is None
    session.close()
