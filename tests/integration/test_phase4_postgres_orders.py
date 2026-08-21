"""Real PostgreSQL Phase 4A migration and transaction checks.

The suite is explicitly gated and uses a random private schema. It never
changes the configured public schema or the public Alembic revision.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.cart.models import ShopMindCartItem
from app.checkout.tokens import CheckoutPriceLine, build_cart_fingerprint, create_checkout_token
from app.core.settings import Settings, get_settings
from app.db.models import AgentRun, ConversationThread, PendingAction
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder
from app.outbox.models import ShopMindOutboxEvent
from app.repositories.shopmind_cart import upsert_cart_item
from app.schemas.orders import CreateOrderRequest
from app.schemas.recommendation import AvailabilityView, LaptopConstraints, Money, Recommendation, RecommendationResult
from app.services.checkout import preview_checkout
from app.services.orders import OrderServiceError, cancel_order, create_order
from app.services.pending_actions import confirm_add_to_cart, create_add_to_cart_pending_action


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for Phase 4A PostgreSQL checks",
)


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def _assert_phase4_schema(connection, schema: str) -> None:
    inspector = inspect(connection)
    order_item_columns = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns("shopmind_order_items", schema=schema)
    }
    assert all(
        order_item_columns[name] is False
        for name in (
            "product_code_snapshot",
            "product_name_snapshot",
            "sku_code_snapshot",
            "sku_name_snapshot",
        )
    )
    order_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("shopmind_orders", schema=schema)
    }
    item_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("shopmind_order_items", schema=schema)
    }
    reservation_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("shopmind_inventory_reservations", schema=schema)
    }
    assert order_uniques["uq_shopmind_orders_user_idempotency"] == ("user_id", "idempotency_key")
    assert item_uniques["uq_shopmind_order_items_order_sku"] == ("order_id", "sku_id")
    assert reservation_uniques["uq_shopmind_inventory_reservations_order_item"] == ("order_item_id",)
    item_fks = {
        tuple(foreign_key["constrained_columns"]): (
            foreign_key["referred_table"],
            foreign_key.get("options", {}).get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys("shopmind_order_items", schema=schema)
    }
    reservation_fks = {
        tuple(foreign_key["constrained_columns"]): (
            foreign_key["referred_table"],
            foreign_key.get("options", {}).get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys("shopmind_inventory_reservations", schema=schema)
    }
    assert item_fks[("order_id",)] == ("shopmind_orders", "CASCADE")
    assert item_fks[("sku_id",)] == ("shopmind_product_skus", "RESTRICT")
    assert reservation_fks[("order_item_id",)] == ("shopmind_order_items", "RESTRICT")
    assert reservation_fks[("sku_id",)] == ("shopmind_product_skus", "RESTRICT")
    order_checks = {constraint["name"] for constraint in inspector.get_check_constraints("shopmind_orders", schema=schema)}
    item_checks = {constraint["name"] for constraint in inspector.get_check_constraints("shopmind_order_items", schema=schema)}
    reservation_checks = {constraint["name"] for constraint in inspector.get_check_constraints("shopmind_inventory_reservations", schema=schema)}
    assert {
        "ck_shopmind_orders_status",
        "ck_shopmind_orders_total_equals_subtotal",
        "ck_shopmind_orders_cart_fingerprint_length",
        "ck_shopmind_orders_request_hash_length",
    }.issubset(order_checks)
    assert {
        "ck_shopmind_order_items_unit_price_positive",
        "ck_shopmind_order_items_quantity_bounds",
        "ck_shopmind_order_items_line_total_matches",
    }.issubset(item_checks)
    assert {
        "ck_shopmind_inventory_reservations_status",
        "ck_shopmind_inventory_reservations_release_state",
    }.issubset(reservation_checks)
    order_indexes = {index["name"] for index in inspector.get_indexes("shopmind_orders", schema=schema)}
    reservation_indexes = {
        index["name"]
        for index in inspector.get_indexes("shopmind_inventory_reservations", schema=schema)
    }
    assert {
        "idx_shopmind_orders_user_created_at_id",
        "idx_shopmind_orders_user_status_created_at",
    }.issubset(order_indexes)
    assert "idx_shopmind_inventory_reservations_sku_status" in reservation_indexes


def test_phase4a_migrations_round_trip_in_private_schema() -> None:
    engine = create_engine(get_settings().test_database_url, pool_pre_ping=True)
    schema = f"shopmind_phase4a_{uuid4().hex}"
    with engine.connect() as connection:
        public_revision = connection.execute(
            text("SELECT version_num FROM public.alembic_version LIMIT 1")
        ).scalar_one_or_none()
        public_tables_before = connection.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar_one()
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
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        try:
            command.stamp(_alembic(connection), "0007_governance_audit")
            for revision in (
                "0008_shopmind_catalog_identity",
                "0009_shopmind_skus_inventory",
                "0010_pending_action_contract",
                "0011_shopmind_cart",
                "0012_shopmind_orders",
            ):
                command.upgrade(_alembic(connection), revision)
            table_names = set(inspect(connection).get_table_names(schema=schema))
            assert {
                "shopmind_orders",
                "shopmind_order_items",
                "shopmind_inventory_reservations",
            }.issubset(table_names)
            _assert_phase4_schema(connection, schema)
            assert MigrationContext.configure(connection).get_current_revision() == "0012_shopmind_orders"
            command.downgrade(_alembic(connection), "0011_shopmind_cart")
            assert MigrationContext.configure(connection).get_current_revision() == "0011_shopmind_cart"
            command.upgrade(_alembic(connection), "0012_shopmind_orders")
            assert MigrationContext.configure(connection).get_current_revision() == "0012_shopmind_orders"
        finally:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        public_revision_after = connection.execute(
            text("SELECT version_num FROM public.alembic_version LIMIT 1")
        ).scalar_one_or_none()
        public_tables_after = connection.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar_one()
        assert public_revision_after == public_revision
        assert public_tables_after == public_tables_before
    engine.dispose()


@pytest.fixture(scope="function")
def phase4a_factory():
    engine_url = get_settings().test_database_url
    schema = f"shopmind_phase4a_orders_{uuid4().hex}"
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

    with engine.connect() as connection:
        command.stamp(_alembic(connection), "0007_governance_audit")
        # The Phase 4 service now enqueues the accepted Phase 6A Order event in
        # the same transaction, so the regression fixture must use the current
        # migration head while keeping the Phase 4 transaction scenarios
        # unchanged.
        command.upgrade(_alembic(connection), "0015_shopmind_order_expiration")
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


def _seed_order_case(factory, *, users: tuple[str, ...] = ("phase4a-a", "phase4a-b"), stock: int = 1):
    session: Session = factory()
    category = CatalogCategory(code=f"p4a-{uuid4().hex}", name="Laptop", status="active", managed_by_seed=False)
    product = CatalogProduct(
        product_code=f"P4A-{uuid4().hex}", category=category, brand="ShopMind",
        name="Phase 4A Product", sale_status="active", attributes_json={}, managed_by_seed=False,
    )
    sku = CatalogSku(
        product=product, sku_code=f"P4A-SKU-{uuid4().hex}", name="Base",
        money_amount=Decimal("10.00"), currency="CNY", sale_status="active",
        variant_attributes_json={}, managed_by_seed=False,
    )
    inventory = CatalogInventory(sku=sku, on_hand_quantity=stock, reserved_quantity=0, version=0)
    session.add_all([category, product, sku, inventory])
    session.flush()
    for user in users:
        upsert_cart_item(session, user_id=user, sku_id=sku.id, quantity=1)
    session.commit()
    settings = Settings(shopmind_checkout_signing_secret="p" * 32)
    tokens = {}
    for user in users:
        preview = preview_checkout(session, user_id=user, settings=settings)
        assert preview.checkout_token
        tokens[user] = preview.checkout_token
    ids = (sku.id, inventory.sku_id, product.id)
    session.close()
    return settings, tokens, ids


def _seed_multi_sku_case(
    factory,
    *,
    cart_sequences: dict[str, tuple[int, ...]],
    currencies: tuple[str, ...] = ("CNY", "CNY"),
    stocks: tuple[int, ...] = (2, 2),
):
    session: Session = factory()
    category = CatalogCategory(code=f"p4a-multi-{uuid4().hex}", name="Laptop", status="active", managed_by_seed=False)
    sku_ids = []
    for index, (currency, stock) in enumerate(zip(currencies, stocks, strict=True)):
        product = CatalogProduct(
            product_code=f"P4A-M-{uuid4().hex}", category=category, brand="ShopMind",
            name=f"Phase 4A Product {index}", sale_status="active", attributes_json={}, managed_by_seed=False,
        )
        sku = CatalogSku(
            product=product, sku_code=f"P4A-M-SKU-{uuid4().hex}", name=f"Variant {index}",
            money_amount=Decimal("10.00") + index, currency=currency, sale_status="active",
            variant_attributes_json={}, managed_by_seed=False,
        )
        session.add_all([product, sku, CatalogInventory(sku=sku, on_hand_quantity=stock, reserved_quantity=0, version=0)])
        session.flush()
        sku_ids.append(sku.id)
    for user_id, sequence in cart_sequences.items():
        for index in sequence:
            upsert_cart_item(session, user_id=user_id, sku_id=sku_ids[index], quantity=1)
    session.commit()
    settings = Settings(shopmind_checkout_signing_secret="p" * 32)
    tokens = {
        user_id: preview_checkout(session, user_id=user_id, settings=settings).checkout_token
        for user_id in cart_sequences
    }
    assert all(tokens.values())
    session.close()
    return settings, tokens, tuple(sku_ids)


def _fresh_token(
    session: Session,
    *,
    user_id: str,
    secret: str,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> str:
    cart_rows = list(
        session.scalars(
            select(ShopMindCartItem)
            .where(ShopMindCartItem.user_id == user_id)
            .order_by(ShopMindCartItem.sku_id.asc(), ShopMindCartItem.id.asc())
        ).all()
    )
    skus = {row.sku_id: session.get(CatalogSku, row.sku_id) for row in cart_rows}
    currency = next(iter({sku.currency for sku in skus.values()}))
    subtotal = sum((Decimal(skus[row.sku_id].money_amount) * row.quantity for row in cart_rows), Decimal("0.00"))
    return create_checkout_token(
        user_id=user_id,
        cart_fingerprint=build_cart_fingerprint(
            {"cart_item_id": row.id, "sku_id": row.sku_id, "quantity": row.quantity, "version": row.version}
            for row in cart_rows
        ),
        price_lines=[
            CheckoutPriceLine(
                sku_id=row.sku_id,
                unit_price_amount=format(Decimal(skus[row.sku_id].money_amount).quantize(Decimal("0.01")), ".2f"),
                currency=skus[row.sku_id].currency,
            )
            for row in cart_rows
        ],
        currency=currency,
        subtotal_amount=subtotal,
        secret=secret,
        ttl_seconds=ttl_seconds,
        now=now,
    )


def _state_for_skus(session: Session, sku_ids) -> list[tuple[int, int]]:
    return [
        (inventory.reserved_quantity, inventory.version)
        for inventory in session.scalars(
            select(CatalogInventory)
            .where(CatalogInventory.sku_id.in_(sku_ids))
            .order_by(CatalogInventory.sku_id.asc())
        ).all()
    ]


def _seed_phase2_pending_action(factory):
    settings, tokens, ids = _seed_order_case(factory, users=("phase4a-action-race",), stock=2)
    user_id = "phase4a-action-race"
    session: Session = factory()
    sku = session.get(CatalogSku, ids[0])
    product = session.get(CatalogProduct, ids[2])
    assert sku is not None and product is not None
    now = datetime.now(timezone.utc)
    thread_id = f"phase4a-thread-{uuid4().hex}"
    run_id = f"phase4a-run-{uuid4().hex}"
    thread = ConversationThread(
        id=thread_id,
        user_id=user_id,
        client_thread_id=thread_id,
        status="active",
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    recommendation = RecommendationResult(
        outcome="recommended",
        ranking_policy_version="v1",
        request_summary="phase4a pending action race",
        structured_constraints=LaptopConstraints(),
        recommendations=[
            Recommendation(
                product_id=product.id,
                sku_id=sku.id,
                product_name=product.name,
                sku_name=sku.name,
                money=Money(amount="10.00", currency="CNY"),
                specifications=[],
                score=90,
                score_breakdown=[],
                availability=AvailabilityView(sale_status="active", available_quantity=2, in_stock=True),
                reason="match",
            )
        ],
    )
    run = AgentRun(
        id=run_id,
        thread=thread,
        user_id=user_id,
        operation="chat",
        mode="multi",
        status="completed",
        request_id=uuid4().hex,
        trace_id=uuid4().hex,
        request_json={},
        result_json={"recommendation": recommendation.model_dump(mode="json")},
        usage_json={},
        tool_call_records_json=[],
        metadata_json={},
        started_at=now,
    )
    session.add_all([thread, run])
    session.flush()
    action = create_add_to_cart_pending_action(
        session,
        user_id=user_id,
        thread_id=thread_id,
        source_run_id=run_id,
        sku_id=sku.id,
        quantity=1,
    )
    session.commit()
    session.close()
    return settings, tokens[user_id], ids, thread_id, action.pending_action_id


def _concurrent_create(factory, *, user_id: str, token: str, key: str):
    result = []
    barrier = threading.Barrier(2)

    def worker():
        session: Session = factory()
        try:
            barrier.wait(timeout=10)
            value = create_order(
                session,
                user_id=user_id,
                idempotency_key=key,
                request=CreateOrderRequest(checkout_token=token),
                settings=Settings(shopmind_checkout_signing_secret="p" * 32),
            )
            session.commit()
            result.append(("success", value.idempotent_replay))
        except OrderServiceError as exc:
            session.rollback()
            result.append(("error", exc.code))
        finally:
            session.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    return result


def test_phase4a_last_stock_concurrency_and_partial_rollback(phase4a_factory):
    settings, tokens, ids = _seed_order_case(phase4a_factory, stock=1)
    results = []
    barrier = threading.Barrier(2)

    def worker(user):
        session: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            value = create_order(
                session, user_id=user, idempotency_key=f"stock-{user}",
                request=CreateOrderRequest(checkout_token=tokens[user]), settings=settings,
            )
            session.commit()
            results.append(("success", user, value.order.order_id))
        except OrderServiceError as exc:
            session.rollback()
            results.append(("error", user, exc.code))
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(user,)) for user in tokens]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(row[0] for row in results) == ["error", "success"]
    assert sorted(row[2] if row[0] == "error" else "ok" for row in results) == ["insufficient_inventory", "ok"]
    session: Session = phase4a_factory()
    inventory = session.get(CatalogInventory, ids[1])
    assert (inventory.reserved_quantity, inventory.version) == (1, 1)
    assert len(session.scalars(select(ShopMindOrder)).all()) == 1
    assert session.scalar(select(ShopMindOrder).where(ShopMindOrder.id == next(row[2] for row in results if row[0] == "success")))
    assert len(session.scalars(select(ShopMindInventoryReservation).where(ShopMindInventoryReservation.status == "active")).all()) == 1
    assert len(session.scalars(select(ShopMindCartItem)).all()) == 1
    session.close()


def test_phase4a_same_key_concurrent_replay_and_conflict(phase4a_factory):
    settings, tokens, ids = _seed_order_case(phase4a_factory, users=("phase4a-same",), stock=2)
    token = tokens["phase4a-same"]
    replay_results = _concurrent_create(phase4a_factory, user_id="phase4a-same", token=token, key="same-key")
    assert sorted(replay_results) == [("success", False), ("success", True)]
    session: Session = phase4a_factory()
    assert len(session.scalars(select(ShopMindOrder).where(ShopMindOrder.idempotency_key == "same-key")).all()) == 1
    assert len(session.scalars(select(ShopMindInventoryReservation).where(ShopMindInventoryReservation.status == "active")).all()) == 1
    assert _state_for_skus(session, [ids[0]]) == [(1, 1)]
    assert session.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-same")).all() == []
    session.close()

    settings, tokens, _ = _seed_order_case(phase4a_factory, users=("phase4a-conflict",), stock=2)
    first = tokens["phase4a-conflict"]
    second = create_checkout_token(
        user_id="phase4a-conflict",
        cart_fingerprint=build_cart_fingerprint([]),
        price_lines=[CheckoutPriceLine(sku_id=uuid4(), unit_price_amount="1.00", currency="CNY")],
        currency="CNY", subtotal_amount="1.00", secret="p" * 32, ttl_seconds=900,
    )
    session = phase4a_factory()
    create_order(session, user_id="phase4a-conflict", idempotency_key="conflict-key", request=CreateOrderRequest(checkout_token=first), settings=settings)
    session.commit()
    with pytest.raises(OrderServiceError) as conflict:
        create_order(session, user_id="phase4a-conflict", idempotency_key="conflict-key", request=CreateOrderRequest(checkout_token=second), settings=Settings())
    assert conflict.value.code == "idempotency_conflict"
    session.rollback()
    session.close()


def test_phase4a_cancel_concurrency_releases_once(phase4a_factory):
    settings, tokens, ids = _seed_order_case(phase4a_factory, users=("phase4a-cancel",), stock=2)
    session: Session = phase4a_factory()
    created = create_order(session, user_id="phase4a-cancel", idempotency_key="cancel-key", request=CreateOrderRequest(checkout_token=tokens["phase4a-cancel"]), settings=settings)
    session.commit()
    order_id = created.order.order_id
    session.close()
    results = []
    barrier = threading.Barrier(2)

    def worker():
        current: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            value = cancel_order(current, user_id="phase4a-cancel", order_id=order_id)
            current.commit()
            results.append(value.idempotent_replay)
        except OrderServiceError as exc:
            current.rollback()
            results.append(exc.code)
        finally:
            current.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == [False, True]
    current = phase4a_factory()
    reservation = current.scalar(select(ShopMindInventoryReservation).where(ShopMindInventoryReservation.order_item_id.is_not(None)))
    assert reservation.status == "released"
    assert len(current.scalars(select(ShopMindOrder).where(ShopMindOrder.id == order_id)).all()) == 1
    assert len(current.scalars(select(ShopMindInventoryReservation)).all()) == 1
    assert _state_for_skus(current, [ids[0]]) == [(0, 2)]
    assert current.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-cancel")).all() == []
    current.close()


def test_phase4a_replay_after_token_expiry(phase4a_factory):
    settings, _, ids = _seed_order_case(phase4a_factory, users=("phase4a-expired",), stock=2)
    session: Session = phase4a_factory()
    token = _fresh_token(
        session,
        user_id="phase4a-expired",
        secret="p" * 32,
        ttl_seconds=1,
    )
    created = create_order(
        session,
        user_id="phase4a-expired",
        idempotency_key="expiry-replay",
        request=CreateOrderRequest(checkout_token=token),
        settings=settings,
    )
    session.commit()
    time.sleep(1.1)
    replay = create_order(
        session,
        user_id="phase4a-expired",
        idempotency_key="expiry-replay",
        request=CreateOrderRequest(checkout_token=token),
        settings=settings,
    )
    assert replay.idempotent_replay is True and replay.order.order_id == created.order.order_id
    assert len(session.scalars(select(ShopMindOrder).where(ShopMindOrder.idempotency_key == "expiry-replay")).all()) == 1
    assert _state_for_skus(session, [ids[0]]) == [(1, 1)]
    assert session.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-expired")).all() == []
    session.close()


def test_phase4a_same_key_different_request_is_truly_concurrent(phase4a_factory):
    settings, tokens, ids = _seed_order_case(phase4a_factory, users=("phase4a-conflict-race",), stock=2)
    session: Session = phase4a_factory()
    second_token = _fresh_token(
        session,
        user_id="phase4a-conflict-race",
        secret="p" * 32,
        now=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    session.close()
    barrier = threading.Barrier(2)
    results = []

    def worker(token: str):
        current: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            response = create_order(
                current,
                user_id="phase4a-conflict-race",
                idempotency_key="conflict-race",
                request=CreateOrderRequest(checkout_token=token),
                settings=settings,
            )
            current.commit()
            results.append(("success", response.idempotent_replay))
        except OrderServiceError as exc:
            current.rollback()
            results.append(("error", exc.code))
        finally:
            current.close()

    threads = [threading.Thread(target=worker, args=(tokens["phase4a-conflict-race"],)), threading.Thread(target=worker, args=(second_token,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results) == [("error", "idempotency_conflict"), ("success", False)]
    current = phase4a_factory()
    assert len(current.scalars(select(ShopMindOrder).where(ShopMindOrder.idempotency_key == "conflict-race")).all()) == 1
    assert current.scalars(select(ShopMindInventoryReservation).where(ShopMindInventoryReservation.status == "active")).all()
    assert _state_for_skus(current, [ids[0]]) == [(1, 1)]
    assert current.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-conflict-race")).all() == []
    current.close()


def test_phase4a_multisku_ab_ba_has_no_deadlock(phase4a_factory):
    settings, tokens, sku_ids = _seed_multi_sku_case(
        phase4a_factory,
        cart_sequences={"phase4a-ab": (0, 1), "phase4a-ba": (1, 0)},
        stocks=(2, 2),
    )
    barrier = threading.Barrier(2)
    results = []

    def worker(user_id: str):
        current: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            response = create_order(
                current,
                user_id=user_id,
                idempotency_key=f"ab-ba-{user_id}",
                request=CreateOrderRequest(checkout_token=tokens[user_id]),
                settings=settings,
            )
            current.commit()
            results.append(response.idempotent_replay)
        finally:
            current.close()

    threads = [threading.Thread(target=worker, args=(user_id,)) for user_id in tokens]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results) == [False, False]
    current = phase4a_factory()
    assert len(current.scalars(select(ShopMindOrder)).all()) == 2
    assert len(current.scalars(select(ShopMindInventoryReservation).where(ShopMindInventoryReservation.status == "active")).all()) == 4
    assert _state_for_skus(current, sku_ids) == [(2, 2), (2, 2)]
    assert current.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id.in_(tokens))).all() == []
    current.close()


def test_phase4a_mixed_currency_and_multisku_failure_rollback(phase4a_factory):
    settings, tokens, sku_ids = _seed_multi_sku_case(
        phase4a_factory,
        cart_sequences={"phase4a-mixed": (0, 1)},
        stocks=(1, 1),
    )
    session: Session = phase4a_factory()
    changed_sku = session.get(CatalogSku, sku_ids[1])
    changed_sku.currency = "USD"
    session.commit()
    with pytest.raises(OrderServiceError) as mixed:
        create_order(
            session,
            user_id="phase4a-mixed",
            idempotency_key="mixed-priority",
            request=CreateOrderRequest(checkout_token=tokens["phase4a-mixed"]),
            settings=settings,
        )
    assert mixed.value.code == "mixed_currency"
    session.rollback()
    assert session.scalars(select(ShopMindOrder).where(ShopMindOrder.idempotency_key == "mixed-priority")).all() == []
    assert session.scalars(select(ShopMindOutboxEvent)).all() == []
    assert session.scalars(select(ShopMindInventoryReservation)).all() == []
    assert _state_for_skus(session, sku_ids) == [(0, 0), (0, 0)]
    assert len(session.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-mixed")).all()) == 2
    session.close()

    settings, tokens, sku_ids = _seed_multi_sku_case(
        phase4a_factory,
        cart_sequences={"phase4a-rollback": (0, 1)},
        stocks=(1, 1),
    )
    session = phase4a_factory()
    second_inventory = session.get(CatalogInventory, sku_ids[1])
    second_inventory.on_hand_quantity = 0
    session.commit()
    with pytest.raises(OrderServiceError) as insufficient:
        create_order(
            session,
            user_id="phase4a-rollback",
            idempotency_key="multisku-rollback",
            request=CreateOrderRequest(checkout_token=tokens["phase4a-rollback"]),
            settings=settings,
        )
    assert insufficient.value.code == "insufficient_inventory"
    session.rollback()
    assert session.scalars(select(ShopMindOrder).where(ShopMindOrder.idempotency_key == "multisku-rollback")).all() == []
    assert session.scalars(select(ShopMindOutboxEvent)).all() == []
    assert session.scalars(select(ShopMindInventoryReservation)).all() == []
    assert _state_for_skus(session, sku_ids) == [(0, 0), (0, 0)]
    assert len(session.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-rollback")).all()) == 2
    session.close()


def test_phase4a_corrupt_reservation_cancel_rolls_back_safely(phase4a_factory):
    settings, tokens, ids = _seed_order_case(phase4a_factory, users=("phase4a-corrupt",), stock=2)
    session: Session = phase4a_factory()
    created = create_order(
        session,
        user_id="phase4a-corrupt",
        idempotency_key="corrupt-order",
        request=CreateOrderRequest(checkout_token=tokens["phase4a-corrupt"]),
        settings=settings,
    )
    session.commit()
    reservation = session.scalar(select(ShopMindInventoryReservation))
    reservation.status = "released"
    reservation.released_at = datetime.now(timezone.utc)
    session.commit()
    with pytest.raises(OrderServiceError) as inconsistent:
        cancel_order(session, user_id="phase4a-corrupt", order_id=created.order.order_id)
    assert inconsistent.value.code == "reservation_inconsistent"
    session.rollback()
    persisted = session.get(ShopMindOrder, created.order.order_id)
    assert persisted.status == "pending_payment"
    assert len(session.scalars(select(ShopMindInventoryReservation)).all()) == 1
    assert session.scalar(select(ShopMindInventoryReservation)).status == "released"
    assert _state_for_skus(session, [ids[0]]) == [(1, 1)]
    assert len(session.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-corrupt")).all()) == 0
    session.close()


def test_phase4a_create_replay_vs_cancel_race_is_serialized(phase4a_factory):
    settings, tokens, ids = _seed_order_case(phase4a_factory, users=("phase4a-create-cancel",), stock=2)
    session: Session = phase4a_factory()
    created = create_order(
        session,
        user_id="phase4a-create-cancel",
        idempotency_key="create-cancel",
        request=CreateOrderRequest(checkout_token=tokens["phase4a-create-cancel"]),
        settings=settings,
    )
    session.commit()
    barrier = threading.Barrier(2)
    results = []

    def replay_create():
        current: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            replay = create_order(
                current,
                user_id="phase4a-create-cancel",
                idempotency_key="create-cancel",
                request=CreateOrderRequest(checkout_token=tokens["phase4a-create-cancel"]),
                settings=settings,
            )
            current.commit()
            results.append(("create", replay.idempotent_replay))
        finally:
            current.close()

    def cancel():
        current: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            response = cancel_order(current, user_id="phase4a-create-cancel", order_id=created.order.order_id)
            current.commit()
            results.append(("cancel", response.idempotent_replay))
        finally:
            current.close()

    threads = [threading.Thread(target=replay_create), threading.Thread(target=cancel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results) == [("cancel", False), ("create", True)]
    session.close()
    current = phase4a_factory()
    order = current.get(ShopMindOrder, created.order.order_id)
    assert order.status == "cancelled"
    assert current.scalar(select(ShopMindInventoryReservation)).status == "released"
    assert _state_for_skus(current, [ids[0]]) == [(0, 2)]
    assert current.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-create-cancel")).all() == []
    current.close()


def test_phase4a_create_vs_phase2_pending_action_confirm_is_serialized(phase4a_factory):
    settings, token, ids, thread_id, action_id = _seed_phase2_pending_action(phase4a_factory)
    user_id = "phase4a-action-race"
    barrier = threading.Barrier(2)
    results = []

    def create_worker():
        current: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            response = create_order(
                current,
                user_id=user_id,
                idempotency_key="phase2-action-race",
                request=CreateOrderRequest(checkout_token=token),
                settings=settings,
            )
            current.commit()
            results.append(("create", "success", response.idempotent_replay))
        except OrderServiceError as exc:
            current.rollback()
            results.append(("create", "error", exc.code))
        finally:
            current.close()

    def confirm_worker():
        current: Session = phase4a_factory()
        try:
            barrier.wait(timeout=10)
            response = confirm_add_to_cart(
                current,
                pending_action_id=action_id,
                user_id=user_id,
                thread_id=thread_id,
                expected_version=1,
            )
            current.commit()
            results.append(("confirm", "success", response.idempotent_replay))
        finally:
            current.close()

    threads = [threading.Thread(target=create_worker), threading.Thread(target=confirm_worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert any(result[:2] == ("confirm", "success") for result in results)

    current = phase4a_factory()
    action = current.get(PendingAction, action_id)
    assert action is not None and action.status == "confirmed"
    cart = current.scalar(select(ShopMindCartItem).where(ShopMindCartItem.user_id == user_id))
    order_count = len(current.scalars(select(ShopMindOrder).where(ShopMindOrder.user_id == user_id)).all())
    active_reservations = current.scalars(
        select(ShopMindInventoryReservation).where(ShopMindInventoryReservation.status == "active")
    ).all()
    if any(result == ("create", "success", False) for result in results):
        assert order_count == 1
        assert len(active_reservations) == 1
        assert _state_for_skus(current, [ids[0]]) == [(1, 1)]
        assert cart is not None and cart.quantity == 1
    else:
        assert ("create", "error", "cart_changed") in results
        assert order_count == 0
        assert active_reservations == []
        assert _state_for_skus(current, [ids[0]]) == [(0, 0)]
        assert cart is not None and cart.quantity == 2
    current.close()
