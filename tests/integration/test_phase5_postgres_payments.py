"""Real PostgreSQL Phase 5A Payment Attempt and finalization acceptance."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.core.settings import Settings, get_settings
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder
from app.payments.models import ShopMindPaymentAttempt
from app.payments.providers import MockPaymentProvider, ProviderChargeRequest, ProviderOutcome
from app.repositories.shopmind_cart import upsert_cart_item
from app.schemas.orders import CreateOrderRequest
from app.schemas.payments import PaymentAttemptRequest
from app.services.checkout import preview_checkout
from app.services.orders import OrderServiceError, cancel_order, create_order
from app.services.payments import (
    PaymentServiceError,
    claim_payment_attempt,
    finalize_payment,
    persist_provider_outcome,
    resolve_provider_outcome,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for Phase 5A PostgreSQL checks",
)


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def _bootstrap_private_schema(engine, schema: str) -> None:
    with engine.connect() as connection:
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


@pytest.fixture(scope="function")
def phase5a_factory():
    engine_url = get_settings().test_database_url
    schema = f"shopmind_phase5a_{uuid4().hex}"
    bootstrap = create_engine(engine_url, pool_pre_ping=True)
    _bootstrap_private_schema(bootstrap, schema)
    bootstrap.dispose()

    engine = create_engine(engine_url, pool_pre_ping=True)

    @event.listens_for(engine, "checkout")
    def _set_private_search_path(dbapi_connection, _connection_record, _proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    with engine.connect() as connection:
        command.stamp(_alembic(connection), "0007_governance_audit")
        # Payment finalization enqueues its success event in the same
        # transaction; run the unchanged Phase 5A scenarios at the current
        # migration head.
        command.upgrade(_alembic(connection), "0015_shopmind_order_expiration")

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def _seed_order(
    factory,
    *,
    user_id: str,
    sku_count: int = 1,
    stocks: tuple[int, ...] | None = None,
    quantities: tuple[int, ...] | None = None,
):
    stocks = stocks or tuple(2 for _ in range(sku_count))
    quantities = quantities or tuple(1 for _ in range(sku_count))
    session: Session = factory()
    category = CatalogCategory(
        code=f"p5a-{uuid4().hex}",
        name="Phase 5A",
        status="active",
        managed_by_seed=False,
    )
    sku_ids = []
    for index in range(sku_count):
        product = CatalogProduct(
            product_code=f"P5A-{uuid4().hex}",
            category=category,
            brand="ShopMind",
            name=f"Phase 5A Product {index}",
            sale_status="active",
            attributes_json={},
            managed_by_seed=False,
        )
        sku = CatalogSku(
            product=product,
            sku_code=f"P5A-SKU-{uuid4().hex}",
            name=f"Variant {index}",
            money_amount=Decimal("10.00") + index,
            currency="CNY",
            sale_status="active",
            variant_attributes_json={},
            managed_by_seed=False,
        )
        session.add_all(
            [
                product,
                sku,
                CatalogInventory(
                    sku=sku,
                    on_hand_quantity=stocks[index],
                    reserved_quantity=0,
                    version=0,
                ),
            ]
        )
        session.flush()
        sku_ids.append(sku.id)
        upsert_cart_item(
            session,
            user_id=user_id,
            sku_id=sku.id,
            quantity=quantities[index],
        )
    session.commit()
    settings = Settings(shopmind_checkout_signing_secret="p" * 32)
    preview = preview_checkout(session, user_id=user_id, settings=settings)
    assert preview.checkout_token
    session.rollback()
    session.close()

    session = factory()
    created = create_order(
        session,
        user_id=user_id,
        idempotency_key=f"order-{uuid4().hex}",
        request=CreateOrderRequest(checkout_token=preview.checkout_token),
        settings=settings,
    )
    session.commit()
    order_id = created.order.order_id
    session.rollback()
    session.close()
    return order_id, tuple(sku_ids)


def _request(method: str = "method") -> PaymentAttemptRequest:
    return PaymentAttemptRequest(provider="mock", payment_method_ref=method)


def _complete_payment(factory, provider, *, user_id: str, order_id: UUID, key: str, method: str):
    session: Session = factory()
    try:
        claim = claim_payment_attempt(
            session,
            user_id=user_id,
            order_id=order_id,
            idempotency_key=key,
            request=_request(method),
        )
        session.commit()
        if claim.action == "replay_succeeded":
            return "replay"
        if claim.action == "replay_failed":
            return "failed_replay"
        if claim.action == "finalize":
            finalize_payment(session, user_id=user_id, order_id=order_id, attempt_id=claim.attempt_id)
            session.commit()
            return "success"
        outcome = resolve_provider_outcome(
            provider,
            claim=claim,
            request=_request(method),
        )
        persist_provider_outcome(session, attempt_id=claim.attempt_id, outcome=outcome)
        session.commit()
        if outcome.status == "declined":
            return "declined"
        if outcome.status == "unknown":
            return "unknown"
        finalize_payment(session, user_id=user_id, order_id=order_id, attempt_id=claim.attempt_id)
        session.commit()
        return "success"
    except (PaymentServiceError, OrderServiceError) as exc:
        session.rollback()
        return exc.code
    finally:
        session.close()


def _concurrent_payments(factory, provider, *, user_id: str, order_id: UUID, keys: tuple[str, ...]):
    barrier = threading.Barrier(len(keys))
    results: list[str] = []
    results_lock = threading.Lock()

    def worker(key: str) -> None:
        session: Session = factory()
        try:
            barrier.wait(timeout=15)
            claim = claim_payment_attempt(
                session,
                user_id=user_id,
                order_id=order_id,
                idempotency_key=key,
                request=_request(),
            )
            session.commit()
            if claim.action == "replay_succeeded":
                result = "replay"
            elif claim.action == "replay_failed":
                result = "failed_replay"
            elif claim.action == "finalize":
                finalize_payment(session, user_id=user_id, order_id=order_id, attempt_id=claim.attempt_id)
                session.commit()
                result = "success"
            else:
                outcome = resolve_provider_outcome(provider, claim=claim, request=_request())
                persist_provider_outcome(session, attempt_id=claim.attempt_id, outcome=outcome)
                session.commit()
                if outcome.status == "declined":
                    result = "declined"
                elif outcome.status == "unknown":
                    result = "unknown"
                else:
                    finalize_payment(session, user_id=user_id, order_id=order_id, attempt_id=claim.attempt_id)
                    session.commit()
                    result = "success"
        except (PaymentServiceError, OrderServiceError) as exc:
            session.rollback()
            result = exc.code
        finally:
            session.close()
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker, args=(key,)) for key in keys]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    return results


def test_phase5a_migration_round_trip_and_introspection(phase5a_factory) -> None:
    engine = phase5a_factory.kw["bind"]
    with engine.connect() as connection:
        public_revision = connection.execute(
            text("SELECT version_num FROM public.alembic_version LIMIT 1")
        ).scalar_one_or_none()
        private_schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        connection.execute(text("SET search_path TO public"))
        connection.commit()
        connection.execute(text(f'SET search_path TO "{private_schema}"'))
        connection.commit()
        command.downgrade(_alembic(connection), "0012_shopmind_orders")
        assert MigrationContext.configure(connection).get_current_revision() == "0012_shopmind_orders"
        command.upgrade(_alembic(connection), "0013_shopmind_payments")
        assert MigrationContext.configure(connection).get_current_revision() == "0013_shopmind_payments"

        inspector = inspect(connection)
        columns = {
            column["name"]: column["nullable"]
            for column in inspector.get_columns("shopmind_payment_attempts")
        }
        assert columns["provider_result_at"] is True
        assert columns["provider_idempotency_key"] is False
        reservation_columns = {
            column["name"]: column["nullable"]
            for column in inspector.get_columns("shopmind_inventory_reservations")
        }
        assert reservation_columns["consumed_at"] is True

        uniques = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("shopmind_payment_attempts")
        }
        assert uniques["uq_shopmind_payment_attempts_user_order_key"] == (
            "user_id", "order_id", "idempotency_key"
        )
        assert uniques["uq_shopmind_payment_attempts_provider_key"] == (
            "provider", "provider_idempotency_key"
        )
        indexes = {
            index["name"]: index
            for index in inspector.get_indexes("shopmind_payment_attempts")
        }
        assert indexes["uq_shopmind_payment_attempts_order_active"]["unique"] is True
        assert "idx_shopmind_payment_attempts_order_created_at" in indexes
        assert "idx_shopmind_payment_attempts_user_created_at" in indexes

        fks = {
            tuple(foreign_key["constrained_columns"]): (
                foreign_key["referred_table"],
                foreign_key.get("options", {}).get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys("shopmind_payment_attempts")
        }
        assert fks[("order_id",)] == ("shopmind_orders", "RESTRICT")

        checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("shopmind_payment_attempts")
        }
        assert {
            "ck_shopmind_payment_attempts_status",
            "ck_shopmind_payment_attempts_amount_positive",
            "ck_shopmind_payment_attempts_outcome_consistency",
        }.issubset(checks)
        order_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("shopmind_orders")
        }
        reservation_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("shopmind_inventory_reservations")
        }
        assert "ck_shopmind_orders_status" in order_checks
        assert "ck_shopmind_inventory_reservations_release_state" in reservation_checks
        assert public_revision == connection.execute(
            text("SELECT version_num FROM public.alembic_version LIMIT 1")
        ).scalar_one_or_none()


def test_phase5a_success_replay_and_exact_versions(phase5a_factory) -> None:
    order_id, sku_ids = _seed_order(phase5a_factory, user_id="phase5a-success")
    provider = MockPaymentProvider()
    assert _complete_payment(
        phase5a_factory, provider, user_id="phase5a-success", order_id=order_id,
        key="payment-success", method="method",
    ) == "success"
    assert _complete_payment(
        phase5a_factory, provider, user_id="phase5a-success", order_id=order_id,
        key="payment-success", method="method",
    ) == "replay"
    session: Session = phase5a_factory()
    order = session.get(ShopMindOrder, order_id)
    attempt = session.scalar(select(ShopMindPaymentAttempt))
    reservation = session.scalar(select(ShopMindInventoryReservation))
    inventory = session.get(CatalogInventory, sku_ids[0])
    assert order is not None and attempt is not None and reservation is not None and inventory is not None
    assert (order.status, order.version) == ("paid", 2)
    assert (attempt.status, provider.charge_calls) == ("succeeded", 1)
    assert (reservation.status, reservation.consumed_at is not None) == ("consumed", True)
    assert (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == (1, 0, 2)
    conflict_session: Session = phase5a_factory()
    with pytest.raises(PaymentServiceError) as conflict:
        claim_payment_attempt(
            conflict_session,
            user_id="phase5a-success",
            order_id=order_id,
            idempotency_key="payment-success",
            request=_request("different-method"),
        )
    assert conflict.value.code == "idempotency_conflict"
    conflict_session.rollback()
    conflict_session.close()

    paid_session = phase5a_factory()
    with pytest.raises(PaymentServiceError) as paid_error:
        claim_payment_attempt(
            paid_session,
            user_id="phase5a-success",
            order_id=order_id,
            idempotency_key="payment-after-paid",
            request=_request(),
        )
    assert paid_error.value.code == "order_already_paid"
    paid_session.rollback()
    with pytest.raises(OrderServiceError) as cancel_error:
        cancel_order(paid_session, user_id="phase5a-success", order_id=order_id)
    assert cancel_error.value.code == "order_not_cancellable"
    paid_session.rollback()
    paid_session.close()
    session.close()


def test_phase5a_truly_concurrent_same_key_is_one_attempt(phase5a_factory) -> None:
    order_id, sku_ids = _seed_order(phase5a_factory, user_id="phase5a-concurrent-same")
    provider = MockPaymentProvider()
    results = _concurrent_payments(
        phase5a_factory,
        provider,
        user_id="phase5a-concurrent-same",
        order_id=order_id,
        keys=("same-concurrent-key", "same-concurrent-key"),
    )
    assert all(result in {"success", "replay"} for result in results)
    session: Session = phase5a_factory()
    assert len(session.scalars(select(ShopMindPaymentAttempt)).all()) == 1
    inventory = session.get(CatalogInventory, sku_ids[0])
    order = session.get(ShopMindOrder, order_id)
    assert inventory is not None and order is not None
    assert (order.status, inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == ("paid", 1, 0, 2)
    session.close()


def test_phase5a_truly_concurrent_different_keys_cannot_double_pay(phase5a_factory) -> None:
    order_id, sku_ids = _seed_order(phase5a_factory, user_id="phase5a-concurrent-different")
    provider = MockPaymentProvider()
    results = _concurrent_payments(
        phase5a_factory,
        provider,
        user_id="phase5a-concurrent-different",
        order_id=order_id,
        keys=("different-key-a", "different-key-b"),
    )
    assert sum(result == "success" for result in results) == 1
    assert all(result in {"success", "payment_in_progress", "order_already_paid"} for result in results)
    session: Session = phase5a_factory()
    assert len(session.scalars(select(ShopMindPaymentAttempt)).all()) == 1
    inventory = session.get(CatalogInventory, sku_ids[0])
    assert inventory is not None
    assert (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == (1, 0, 2)
    session.close()


def test_phase5a_unknown_reconcile_and_declined_payment(phase5a_factory) -> None:
    order_id, sku_ids = _seed_order(phase5a_factory, user_id="phase5a-outcomes")
    provider = MockPaymentProvider(
        scenarios_by_method={
            "unknown": ("unknown", "success"),
            "decline": ("declined",),
        }
    )
    assert _complete_payment(
        phase5a_factory, provider, user_id="phase5a-outcomes", order_id=order_id,
        key="unknown-key", method="unknown",
    ) == "unknown"
    assert _complete_payment(
        phase5a_factory, provider, user_id="phase5a-outcomes", order_id=order_id,
        key="unknown-key", method="unknown",
    ) == "success"
    session: Session = phase5a_factory()
    order = session.get(ShopMindOrder, order_id)
    inventory = session.get(CatalogInventory, sku_ids[0])
    assert order is not None and inventory is not None
    assert order.status == "paid"
    assert (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == (1, 0, 2)
    session.close()

    declined_order_id, _ = _seed_order(phase5a_factory, user_id="phase5a-declined")
    assert _complete_payment(
        phase5a_factory, provider, user_id="phase5a-declined", order_id=declined_order_id,
        key="declined-key", method="decline",
    ) == "declined"


def test_phase5a_provider_succeeded_survives_local_failure_and_retries_without_charge(phase5a_factory) -> None:
    order_id, sku_ids = _seed_order(phase5a_factory, user_id="phase5a-repair")
    provider = MockPaymentProvider()
    session: Session = phase5a_factory()
    claim = claim_payment_attempt(
        session,
        user_id="phase5a-repair",
        order_id=order_id,
        idempotency_key="repair-key",
        request=_request(),
    )
    session.commit()
    outcome = provider.charge(
        ProviderChargeRequest(
            provider_idempotency_key=claim.provider_idempotency_key,
            amount="10.00",
            currency="CNY",
            payment_method_ref="method",
        )
    )
    persist_provider_outcome(session, attempt_id=claim.attempt_id, outcome=outcome)
    session.commit()
    stale_at = datetime.now(timezone.utc)
    persist_provider_outcome(
        session,
        attempt_id=claim.attempt_id,
        outcome=ProviderOutcome(
            status="unknown",
            provider_payment_id="stale-provider-payment",
            failure_code="provider_timeout",
            result_at=stale_at,
        ),
    )
    session.commit()
    persist_provider_outcome(
        session,
        attempt_id=claim.attempt_id,
        outcome=ProviderOutcome(
            status="declined",
            provider_payment_id="stale-provider-payment",
            failure_code="payment_declined",
            result_at=stale_at,
        ),
    )
    session.commit()
    assert session.get(ShopMindPaymentAttempt, claim.attempt_id).status == "provider_succeeded"
    reservation = session.scalar(select(ShopMindInventoryReservation))
    assert reservation is not None
    reservation.quantity = 2
    session.commit()
    session.close()

    session = phase5a_factory()
    with pytest.raises(PaymentServiceError) as error:
        finalize_payment(session, user_id="phase5a-repair", order_id=order_id, attempt_id=claim.attempt_id)
    assert error.value.code == "payment_finalization_pending"
    session.rollback()
    attempt = session.get(ShopMindPaymentAttempt, claim.attempt_id)
    order = session.get(ShopMindOrder, order_id)
    inventory = session.get(CatalogInventory, sku_ids[0])
    assert attempt is not None and order is not None and inventory is not None
    assert (attempt.status, order.status) == ("provider_succeeded", "pending_payment")
    assert (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == (2, 1, 1)
    reservation = session.scalar(select(ShopMindInventoryReservation))
    assert reservation is not None
    reservation.quantity = 1
    session.commit()
    finalize_payment(session, user_id="phase5a-repair", order_id=order_id, attempt_id=claim.attempt_id)
    session.commit()
    assert provider.charge_calls == 1
    assert session.get(ShopMindOrder, order_id).status == "paid"
    session.close()


def test_phase5a_multi_sku_partial_failure_rolls_back_all_changes(phase5a_factory) -> None:
    order_id, sku_ids = _seed_order(
        phase5a_factory,
        user_id="phase5a-multi",
        sku_count=2,
        stocks=(2, 2),
    )
    provider = MockPaymentProvider()
    session: Session = phase5a_factory()
    claim = claim_payment_attempt(
        session,
        user_id="phase5a-multi",
        order_id=order_id,
        idempotency_key="multi-key",
        request=_request(),
    )
    session.commit()
    outcome = provider.charge(
        ProviderChargeRequest(
            provider_idempotency_key=claim.provider_idempotency_key,
            amount="21.00",
            currency="CNY",
            payment_method_ref="method",
        )
    )
    persist_provider_outcome(session, attempt_id=claim.attempt_id, outcome=outcome)
    session.commit()
    second_inventory = session.get(CatalogInventory, sku_ids[1])
    assert second_inventory is not None
    second_inventory.reserved_quantity = 0
    session.commit()
    session.close()

    session = phase5a_factory()
    with pytest.raises(PaymentServiceError):
        finalize_payment(session, user_id="phase5a-multi", order_id=order_id, attempt_id=claim.attempt_id)
    session.rollback()
    inventories = list(
        session.scalars(
            select(CatalogInventory).where(CatalogInventory.sku_id.in_(sku_ids)).order_by(CatalogInventory.sku_id)
        ).all()
    )
    inventory_by_sku = {row.sku_id: row for row in inventories}
    assert [
        (
            inventory_by_sku[sku_id].on_hand_quantity,
            inventory_by_sku[sku_id].reserved_quantity,
            inventory_by_sku[sku_id].version,
        )
        for sku_id in sku_ids
    ] == [(2, 1, 1), (2, 0, 1)]
    assert session.get(ShopMindOrder, order_id).status == "pending_payment"
    session.close()


def test_phase5a_payment_vs_cancel_and_owner_conflict(phase5a_factory) -> None:
    order_id, sku_ids = _seed_order(phase5a_factory, user_id="phase5a-cancel")
    session: Session = phase5a_factory()
    claim = claim_payment_attempt(
        session,
        user_id="phase5a-cancel",
        order_id=order_id,
        idempotency_key="cancel-race-key",
        request=_request(),
    )
    session.commit()
    session.close()

    cancel_session: Session = phase5a_factory()
    with pytest.raises(OrderServiceError) as error:
        cancel_order(cancel_session, user_id="phase5a-cancel", order_id=order_id)
    assert error.value.code == "payment_in_progress"
    cancel_session.rollback()
    cancel_session.close()

    provider = MockPaymentProvider()
    assert _complete_payment(
        phase5a_factory, provider, user_id="phase5a-cancel", order_id=order_id,
        key="cancel-race-key", method="method",
    ) == "success"

    session = phase5a_factory()
    with pytest.raises(PaymentServiceError) as owner_error:
        claim_payment_attempt(
            session,
            user_id="other-owner",
            order_id=order_id,
            idempotency_key="other-key",
            request=_request(),
        )
    assert owner_error.value.code == "order_not_found"
    session.rollback()
    session.close()

    cancelled_order_id, _ = _seed_order(phase5a_factory, user_id="phase5a-cancel-first")
    cancel_first: Session = phase5a_factory()
    cancelled = cancel_order(
        cancel_first,
        user_id="phase5a-cancel-first",
        order_id=cancelled_order_id,
    )
    cancel_first.commit()
    assert cancelled.order.status == "cancelled"
    with pytest.raises(PaymentServiceError) as not_payable:
        claim_payment_attempt(
            cancel_first,
            user_id="phase5a-cancel-first",
            order_id=cancelled_order_id,
            idempotency_key="after-cancel",
            request=_request(),
        )
    assert not_payable.value.code == "order_not_payable"
    cancel_first.rollback()
    cancel_first.close()


def test_phase5a_payment_lock_first_vs_cancel_is_serialized(phase5a_factory) -> None:
    user_id = "phase5a-race-payment-first"
    order_id, sku_ids = _seed_order(phase5a_factory, user_id=user_id)
    provider = MockPaymentProvider()
    payment_locked = threading.Event()
    cancel_started = threading.Event()
    cancel_lock_acquired = threading.Event()
    release_payment = threading.Event()
    results: dict[str, str] = {}

    def payment_worker() -> None:
        session: Session = phase5a_factory()
        try:
            claim = claim_payment_attempt(
                session,
                user_id=user_id,
                order_id=order_id,
                idempotency_key="payment-first-race",
                request=_request(),
            )
            payment_locked.set()
            assert cancel_started.wait(timeout=15)
            assert release_payment.wait(timeout=15)
            session.commit()
            # Let the blocked Cancel transaction acquire the released Order
            # lock before Provider/finalization can change the Order state.
            assert cancel_lock_acquired.wait(timeout=15)
            outcome = resolve_provider_outcome(provider, claim=claim, request=_request())
            persist_provider_outcome(session, attempt_id=claim.attempt_id, outcome=outcome)
            session.commit()
            finalize_payment(session, user_id=user_id, order_id=order_id, attempt_id=claim.attempt_id)
            session.commit()
            results["payment"] = "success"
        except (PaymentServiceError, OrderServiceError) as exc:
            session.rollback()
            results["payment"] = exc.code
        finally:
            session.close()

    def cancel_worker() -> None:
        cancel_started.set()
        session: Session = phase5a_factory()
        try:
            locked_order = session.scalar(
                select(ShopMindOrder)
                .where(ShopMindOrder.id == order_id)
                .with_for_update()
            )
            assert locked_order is not None
            cancel_lock_acquired.set()
            cancel_order(session, user_id=user_id, order_id=order_id)
            session.commit()
            results["cancel"] = "cancelled"
        except OrderServiceError as exc:
            session.rollback()
            results["cancel"] = exc.code
        finally:
            session.close()

    payment_thread = threading.Thread(target=payment_worker)
    cancel_thread = threading.Thread(target=cancel_worker)
    payment_thread.start()
    assert payment_locked.wait(timeout=15)
    cancel_thread.start()
    assert cancel_started.wait(timeout=15)
    release_payment.set()
    payment_thread.join(timeout=30)
    cancel_thread.join(timeout=30)
    assert not payment_thread.is_alive()
    assert not cancel_thread.is_alive()
    assert results == {"payment": "success", "cancel": "payment_in_progress"}

    session = phase5a_factory()
    order = session.get(ShopMindOrder, order_id)
    attempt = session.scalar(select(ShopMindPaymentAttempt))
    reservation = session.scalar(select(ShopMindInventoryReservation))
    inventory = session.get(CatalogInventory, sku_ids[0])
    assert order is not None and attempt is not None and reservation is not None and inventory is not None
    assert order.status == "paid"
    assert (attempt.status, reservation.status) == ("succeeded", "consumed")
    assert (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == (1, 0, 2)
    assert provider.charge_calls == 1
    session.close()


def test_phase5a_cancel_lock_first_vs_payment_is_serialized(phase5a_factory) -> None:
    user_id = "phase5a-race-cancel-first"
    order_id, sku_ids = _seed_order(phase5a_factory, user_id=user_id)
    provider = MockPaymentProvider()
    cancel_locked = threading.Event()
    payment_started = threading.Event()
    release_cancel = threading.Event()
    results: dict[str, str] = {}

    def cancel_worker() -> None:
        session: Session = phase5a_factory()
        try:
            cancel_order(session, user_id=user_id, order_id=order_id)
            cancel_locked.set()
            assert payment_started.wait(timeout=15)
            assert release_cancel.wait(timeout=15)
            session.commit()
            results["cancel"] = "cancelled"
        except OrderServiceError as exc:
            session.rollback()
            results["cancel"] = exc.code
        finally:
            session.close()

    def payment_worker() -> None:
        payment_started.set()
        session: Session = phase5a_factory()
        try:
            claim_payment_attempt(
                session,
                user_id=user_id,
                order_id=order_id,
                idempotency_key="cancel-first-race",
                request=_request(),
            )
            session.commit()
            results["payment"] = "unexpected_success"
        except PaymentServiceError as exc:
            session.rollback()
            results["payment"] = exc.code
        finally:
            session.close()

    cancel_thread = threading.Thread(target=cancel_worker)
    payment_thread = threading.Thread(target=payment_worker)
    cancel_thread.start()
    assert cancel_locked.wait(timeout=15)
    payment_thread.start()
    assert payment_started.wait(timeout=15)
    release_cancel.set()
    cancel_thread.join(timeout=30)
    payment_thread.join(timeout=30)
    assert not cancel_thread.is_alive()
    assert not payment_thread.is_alive()
    assert results == {"cancel": "cancelled", "payment": "order_not_payable"}

    session = phase5a_factory()
    order = session.get(ShopMindOrder, order_id)
    attempt_count = len(session.scalars(select(ShopMindPaymentAttempt)).all())
    reservation = session.scalar(select(ShopMindInventoryReservation))
    inventory = session.get(CatalogInventory, sku_ids[0])
    assert order is not None and reservation is not None and inventory is not None
    assert (order.status, attempt_count, reservation.status) == ("cancelled", 0, "released")
    assert (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == (2, 0, 2)
    assert provider.charge_calls == 0
    session.close()
