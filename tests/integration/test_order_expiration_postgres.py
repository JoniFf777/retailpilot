"""Real PostgreSQL migration, expiry, locking, and payment-safety checks."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.core.settings import Settings, get_settings
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder
from app.outbox.models import ShopMindOutboxEvent
from app.payments.models import ShopMindPaymentAttempt
from app.payments.providers import ProviderOutcome
from app.repositories.shopmind_cart import upsert_cart_item
from app.schemas.orders import CreateOrderRequest
from app.schemas.payments import PaymentAttemptRequest
from app.services import order_expiration
from app.services.checkout import preview_checkout
from app.services.order_expiration import expire_orders_once
from app.services.orders import OrderServiceError, cancel_order, create_order
from app.services.payments import (
    PaymentServiceError,
    claim_payment_attempt,
    finalize_payment,
    persist_provider_outcome,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for Order expiration PostgreSQL checks",
)


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def _bootstrap_schema(engine, schema: str) -> None:
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".alembic_version (
                    version_num VARCHAR(32) NOT NULL PRIMARY KEY
                )'''
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


def _engine_at_head(head: str):
    engine_url = get_settings().test_database_url
    schema = f"shopmind_expiration_{uuid4().hex}"
    bootstrap = create_engine(engine_url, pool_pre_ping=True)
    _bootstrap_schema(bootstrap, schema)
    bootstrap.dispose()
    engine = create_engine(engine_url, pool_pre_ping=True)

    @event.listens_for(engine, "checkout")
    def _set_private_search_path(dbapi_connection, _connection_record, _proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    with engine.connect() as connection:
        command.stamp(_alembic(connection), "0007_governance_audit")
        command.upgrade(_alembic(connection), head)
    return engine, schema


@pytest.fixture(scope="function")
def expiration_factory():
    engine, schema = _engine_at_head("0015_shopmind_order_expiration")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory, engine
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def _seed_order(
    factory,
    *,
    user_id: str,
    settings: Settings | None = None,
    stock: int = 5,
) -> tuple[UUID, UUID, Settings]:
    settings = settings or Settings(shopmind_checkout_signing_secret="p" * 32)
    session: Session = factory()
    category = CatalogCategory(
        code=f"expiration-pg-{uuid4().hex}",
        name="Expiration PG",
        status="active",
        managed_by_seed=False,
    )
    product = CatalogProduct(
        product_code=f"EXP-PG-{uuid4().hex}",
        category=category,
        brand="ShopMind",
        name="Expiration PG Product",
        sale_status="active",
        attributes_json={},
        managed_by_seed=False,
    )
    sku = CatalogSku(
        product=product,
        sku_code=f"EXP-PG-SKU-{uuid4().hex}",
        name="Default",
        money_amount=Decimal("10.00"),
        currency="CNY",
        sale_status="active",
        variant_attributes_json={},
        managed_by_seed=False,
    )
    session.add_all(
        [
            category,
            product,
            sku,
            CatalogInventory(sku=sku, on_hand_quantity=stock, reserved_quantity=0, version=0),
        ]
    )
    session.flush()
    sku_id = sku.id
    upsert_cart_item(session, user_id=user_id, sku_id=sku_id, quantity=1)
    session.commit()
    preview = preview_checkout(session, user_id=user_id, settings=settings)
    assert preview.checkout_token
    session.close()

    session = factory()
    result = create_order(
        session,
        user_id=user_id,
        idempotency_key=f"order-{uuid4().hex}",
        request=CreateOrderRequest(checkout_token=preview.checkout_token),
        settings=settings,
    )
    session.commit()
    order_id = result.order.order_id
    session.close()
    return order_id, sku_id, settings


def _set_expiry(factory, order_id: UUID, expires_at: datetime) -> None:
    session: Session = factory()
    session.execute(
        update(ShopMindOrder)
        .where(ShopMindOrder.id == order_id)
        .values(expires_at=expires_at)
    )
    session.commit()
    session.close()


def test_expiration_migration_backfills_and_enforces_deadline_checks() -> None:
    engine, schema = _engine_at_head("0014_shopmind_outbox_events")
    created_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    pending_id = uuid4()
    paid_id = uuid4()
    cancelled_id = uuid4()
    try:
        with engine.begin() as connection:
            for order_id, status in (
                (pending_id, "pending_payment"),
                (paid_id, "paid"),
                (cancelled_id, "cancelled"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO shopmind_orders "
                        "(id, user_id, status, currency, subtotal_amount, total_amount, "
                        "checkout_cart_fingerprint, idempotency_key, request_hash, version, created_at, updated_at) "
                        "VALUES (:id, :user_id, :status, 'CNY', 10.00, 10.00, :fingerprint, :key, :hash, 1, :created_at, :updated_at)"
                    ),
                    {
                        "id": order_id,
                        "user_id": f"migration-{status}",
                        "status": status,
                        "fingerprint": "a" * 64,
                        "key": f"key-{status}",
                        "hash": "b" * 64,
                        "created_at": created_at,
                        "updated_at": created_at,
                    },
                )
        with engine.begin() as connection:
            command.upgrade(_alembic(connection), "0015_shopmind_order_expiration")
            pending = connection.execute(
                text("SELECT expires_at FROM shopmind_orders WHERE id = :id"),
                {"id": pending_id},
            ).scalar_one()
            assert pending == created_at + timedelta(seconds=1_800)
            assert connection.execute(
                text("SELECT expires_at FROM shopmind_orders WHERE id = :id"),
                {"id": paid_id},
            ).scalar_one_or_none() is None
            checks = {
                row["name"]
                for row in inspect(connection).get_check_constraints(
                    "shopmind_orders", schema=schema
                )
            }
            indexes = {
                row["name"]
                for row in inspect(connection).get_indexes("shopmind_orders", schema=schema)
            }
            assert "ck_shopmind_orders_expiration_deadline" in checks
            assert "idx_shopmind_orders_expiration" in indexes
            for status in ("pending_payment", "expired"):
                savepoint = connection.begin_nested()
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text(
                            "INSERT INTO shopmind_orders "
                            "(id, user_id, status, currency, subtotal_amount, total_amount, "
                            "checkout_cart_fingerprint, idempotency_key, request_hash, version, created_at, updated_at) "
                            "VALUES (:id, :user_id, :status, 'CNY', 10.00, 10.00, :fingerprint, :key, :hash, 1, :created_at, :updated_at)"
                        ),
                        {
                            "id": uuid4(),
                            "user_id": f"null-{status}",
                            "status": status,
                            "fingerprint": "c" * 64,
                            "key": f"null-key-{status}",
                            "hash": "d" * 64,
                            "created_at": created_at,
                            "updated_at": created_at,
                        },
                    )
                savepoint.rollback()
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def test_two_expiry_workers_use_skip_locked_and_release_once(expiration_factory, monkeypatch) -> None:
    factory, engine = expiration_factory
    order_id, _sku_id, settings = _seed_order(factory, user_id="two-workers", stock=1)
    now = datetime.now(timezone.utc)
    _set_expiry(factory, order_id, now - timedelta(seconds=1))

    entered = threading.Event()
    release = threading.Event()
    original_release = order_expiration.release_active_reservations

    def blocked_release(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=15)
        return original_release(*args, **kwargs)

    monkeypatch.setattr(order_expiration, "release_active_reservations", blocked_release)
    result_one: list[dict[str, int]] = []
    result_two: list[dict[str, int]] = []

    def worker(target: list[dict[str, int]]) -> None:
        target.append(expire_orders_once(factory, settings, now=now, batch_size=1).as_dict())

    first = threading.Thread(target=worker, args=(result_one,))
    first.start()
    assert entered.wait(timeout=15)
    second = threading.Thread(target=worker, args=(result_two,))
    second.start()
    second.join(timeout=15)
    release.set()
    first.join(timeout=15)
    assert not first.is_alive() and not second.is_alive()
    assert result_two == [{"attempted": 0, "expired": 0, "deferred_payment": 0, "inconsistent": 0, "failed": 0}]
    assert result_one == [{"attempted": 1, "expired": 1, "deferred_payment": 0, "inconsistent": 0, "failed": 0}]

    session: Session = factory()
    inventory = session.get(CatalogInventory, _sku_id)
    event_count = session.scalar(
        select(ShopMindOutboxEvent.id).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.expired.v1",
        ).with_only_columns(ShopMindOutboxEvent.id)
    )
    assert inventory is not None and inventory.reserved_quantity == 0
    assert event_count is not None
    assert session.scalar(
        select(ShopMindOutboxEvent.id).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.expired.v1",
        ).limit(2).offset(1)
    ) is None
    session.close()


def test_provider_succeeded_defers_then_finalization_consumes(expiration_factory) -> None:
    factory, _engine = expiration_factory
    order_id, sku_id, settings = _seed_order(factory, user_id="provider-success")
    session: Session = factory()
    claim = claim_payment_attempt(
        session,
        user_id="provider-success",
        order_id=order_id,
        idempotency_key="provider-success-key",
        request=PaymentAttemptRequest(provider="mock", payment_method_ref="method"),
    )
    session.commit()
    persist_provider_outcome(
        session,
        attempt_id=claim.attempt_id,
        outcome=ProviderOutcome(
            status="succeeded",
            provider_payment_id="provider-success-id",
            failure_code=None,
            result_at=datetime.now(timezone.utc),
        ),
    )
    session.commit()
    session.close()

    now = datetime.now(timezone.utc)
    _set_expiry(factory, order_id, now - timedelta(seconds=1))
    deferred = expire_orders_once(factory, settings, now=now)
    assert deferred.deferred_payment == 1 and deferred.expired == 0
    session = factory()
    finalize_payment(
        session,
        user_id="provider-success",
        order_id=order_id,
        attempt_id=claim.attempt_id,
    )
    session.commit()
    order = session.get(ShopMindOrder, order_id)
    reservation = session.scalar(select(ShopMindInventoryReservation))
    inventory = session.get(CatalogInventory, sku_id)
    assert order is not None and order.status == "paid"
    assert reservation is not None and reservation.status == "consumed"
    assert inventory is not None and inventory.on_hand_quantity == 4 and inventory.reserved_quantity == 0
    session.close()


def test_provider_succeeded_blocks_cancel_without_release(expiration_factory) -> None:
    factory, _engine = expiration_factory
    order_id, sku_id, _settings = _seed_order(factory, user_id="cancel-provider-success")
    session: Session = factory()
    claim = claim_payment_attempt(
        session,
        user_id="cancel-provider-success",
        order_id=order_id,
        idempotency_key="cancel-provider-success-key",
        request=PaymentAttemptRequest(provider="mock", payment_method_ref="method"),
    )
    session.commit()
    persist_provider_outcome(
        session,
        attempt_id=claim.attempt_id,
        outcome=ProviderOutcome(
            status="succeeded",
            provider_payment_id="provider-success-id",
            failure_code=None,
            result_at=datetime.now(timezone.utc),
        ),
    )
    session.commit()
    session.close()
    session = factory()
    with pytest.raises(OrderServiceError) as error:
        cancel_order(session, user_id="cancel-provider-success", order_id=order_id)
    assert error.value.code == "payment_in_progress"
    session.rollback()
    order = session.get(ShopMindOrder, order_id)
    inventory = session.get(CatalogInventory, sku_id)
    assert order is not None and order.status == "pending_payment"
    assert inventory is not None and inventory.reserved_quantity == 1
    session.close()


def test_payment_finalization_lock_wins_over_expiry(expiration_factory) -> None:
    factory, _engine = expiration_factory
    order_id, _sku_id, settings = _seed_order(factory, user_id="finalize-vs-expiry")
    session: Session = factory()
    claim = claim_payment_attempt(
        session,
        user_id="finalize-vs-expiry",
        order_id=order_id,
        idempotency_key="finalize-vs-expiry-key",
        request=PaymentAttemptRequest(provider="mock", payment_method_ref="method"),
    )
    session.commit()
    persist_provider_outcome(
        session,
        attempt_id=claim.attempt_id,
        outcome=ProviderOutcome(
            status="succeeded",
            provider_payment_id="finalize-vs-expiry-provider",
            failure_code=None,
            result_at=datetime.now(timezone.utc),
        ),
    )
    session.commit()
    session.close()
    now = datetime.now(timezone.utc)
    _set_expiry(factory, order_id, now - timedelta(seconds=1))
    lock_acquired = threading.Event()
    release_lock = threading.Event()
    finalization_result: list[str] = []

    def finalizer() -> None:
        current: Session = factory()
        try:
            current.scalar(
                select(ShopMindOrder)
                .where(ShopMindOrder.id == order_id)
                .with_for_update()
            )
            lock_acquired.set()
            assert release_lock.wait(timeout=15)
            finalize_payment(
                current,
                user_id="finalize-vs-expiry",
                order_id=order_id,
                attempt_id=claim.attempt_id,
            )
            current.commit()
            finalization_result.append("paid")
        finally:
            current.close()

    finalizer_thread = threading.Thread(target=finalizer)
    finalizer_thread.start()
    assert lock_acquired.wait(timeout=15)
    expiry_summary: list[dict[str, int]] = []

    def expiry_worker() -> None:
        expiry_summary.append(expire_orders_once(factory, settings, now=now, batch_size=1).as_dict())

    expiry_thread = threading.Thread(target=expiry_worker)
    expiry_thread.start()
    expiry_thread.join(timeout=15)
    release_lock.set()
    finalizer_thread.join(timeout=15)
    assert not expiry_thread.is_alive() and not finalizer_thread.is_alive()
    assert expiry_summary == [{"attempted": 0, "expired": 0, "deferred_payment": 0, "inconsistent": 0, "failed": 0}]
    assert finalization_result == ["paid"]
    session = factory()
    order = session.get(ShopMindOrder, order_id)
    reservation = session.scalar(select(ShopMindInventoryReservation))
    assert order is not None and order.status == "paid"
    assert reservation is not None and reservation.status == "consumed"
    session.close()


def test_succeeded_pending_payment_blocks_cancel_and_expiry(expiration_factory) -> None:
    factory, engine = expiration_factory
    order_id, sku_id, settings = _seed_order(factory, user_id="inconsistent-pg")
    now = datetime.now(timezone.utc)
    session: Session = factory()
    session.add(
        ShopMindPaymentAttempt(
            order_id=order_id,
            user_id="inconsistent-pg",
            provider="mock",
            provider_payment_id="already-succeeded",
            provider_idempotency_key=f"provider-{uuid4().hex}",
            status="succeeded",
            amount=Decimal("10.00"),
            currency="CNY",
            idempotency_key=f"payment-{uuid4().hex}",
            request_hash="e" * 64,
            provider_result_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    with pytest.raises(OrderServiceError) as error:
        cancel_order(session, user_id="inconsistent-pg", order_id=order_id)
    assert error.value.code == "payment_state_inconsistent"
    session.rollback()
    session.close()
    _set_expiry(factory, order_id, now - timedelta(seconds=1))
    summary = expire_orders_once(factory, settings, now=now)
    assert summary.inconsistent == 1 and summary.expired == 0
    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status FROM shopmind_orders WHERE id = :order_id"),
            {"order_id": order_id},
        ).scalar_one()
        reserved = connection.execute(
            text("SELECT reserved_quantity FROM shopmind_inventory WHERE sku_id = :sku_id"),
            {"sku_id": sku_id},
        ).scalar_one()
        cancelled_events = connection.execute(
            text(
                "SELECT count(*) FROM shopmind_outbox_events "
                "WHERE aggregate_id = :order_id AND event_type = 'shopmind.order.cancelled.v1'"
            ),
            {"order_id": order_id},
        ).scalar_one()
        expired_events = connection.execute(
            text(
                "SELECT count(*) FROM shopmind_outbox_events "
                "WHERE aggregate_id = :order_id AND event_type = 'shopmind.order.expired.v1'"
            ),
            {"order_id": order_id},
        ).scalar_one()
        assert status == "pending_payment"
        assert reserved == 1
        assert cancelled_events == 0 and expired_events == 0
