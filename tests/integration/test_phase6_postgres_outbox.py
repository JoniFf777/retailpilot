"""Phase 6A PostgreSQL acceptance for the transactional Outbox."""

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
from sqlalchemy.orm import Session, sessionmaker

from app.cart.models import ShopMindCartItem
from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.core.settings import Settings, get_settings
from app.outbox.contracts import (
    OutboxEventEnvelope,
    build_order_created_event,
)
from app.outbox.models import ShopMindOutboxEvent
from app.outbox.publisher import OutboxPublisher
from app.outbox.repository import (
    claim_pending,
    enqueue_event,
    get_outbox_health_snapshot,
    get_outbox_operational_snapshot,
    mark_failure,
    mark_published,
    reclaim_expired,
    redrive_event,
)
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder, ShopMindOrderItem
from app.payments.models import ShopMindPaymentAttempt
from app.payments.providers import ProviderOutcome
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
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for Phase 6A PostgreSQL checks",
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
def phase6_factory():
    engine_url = get_settings().test_database_url
    schema = f"shopmind_phase6_{uuid4().hex}"
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
        command.upgrade(_alembic(connection), "0015_shopmind_order_expiration")

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory, engine
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def _event(*, aggregate_id: UUID, sequence: int, event_type: str = "shopmind.order.created.v1"):
    return OutboxEventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        aggregate_id=aggregate_id,
        aggregate_sequence=sequence,
        occurred_at=datetime.now(timezone.utc),
        payload={"order_id": str(aggregate_id), "sequence": sequence},
    )


def _seed_order(
    factory,
    *,
    user_id: str = "phase6-user",
    commit_order: bool = True,
) -> tuple[UUID, UUID]:
    session: Session = factory()
    category = CatalogCategory(
        code=f"p6-{uuid4().hex}", name="Phase 6", status="active", managed_by_seed=False
    )
    product = CatalogProduct(
        product_code=f"P6-{uuid4().hex}", category=category, brand="ShopMind",
        name="Phase 6 Product", sale_status="active", attributes_json={}, managed_by_seed=False
    )
    sku = CatalogSku(
        product=product, sku_code=f"P6-SKU-{uuid4().hex}", name="Variant",
        money_amount=Decimal("10.00"), currency="CNY", sale_status="active",
        variant_attributes_json={}, managed_by_seed=False
    )
    session.add_all([product, sku, CatalogInventory(sku=sku, on_hand_quantity=2, reserved_quantity=0, version=0)])
    session.flush()
    sku_id = sku.id
    upsert_cart_item(session, user_id=user_id, sku_id=sku.id, quantity=1)
    session.commit()
    settings = Settings(shopmind_checkout_signing_secret="p" * 32)
    preview = preview_checkout(session, user_id=user_id, settings=settings)
    session.rollback()
    session.close()

    session = factory()
    result = create_order(
        session,
        user_id=user_id,
        idempotency_key=f"order-{uuid4().hex}",
        request=CreateOrderRequest(checkout_token=preview.checkout_token),
        settings=settings,
    )
    order_id = result.order.order_id
    if commit_order:
        session.commit()
    else:
        session.rollback()
    session.close()
    return order_id, sku_id


def _complete_provider_success(factory, *, user_id: str, order_id: UUID) -> UUID:
    session = factory()
    request = PaymentAttemptRequest(provider="mock", payment_method_ref="mock-card")
    claim = claim_payment_attempt(
        session,
        user_id=user_id,
        order_id=order_id,
        idempotency_key=f"payment-{uuid4().hex}",
        request=request,
    )
    session.commit()
    outcome = ProviderOutcome(
        status="succeeded",
        provider_payment_id=f"mock-{uuid4().hex}",
        failure_code=None,
        result_at=datetime.now(timezone.utc),
    )
    persist_provider_outcome(session, attempt_id=claim.attempt_id, outcome=outcome)
    session.commit()
    finalize_payment(session, user_id=user_id, order_id=order_id, attempt_id=claim.attempt_id)
    session.commit()
    session.close()
    return claim.attempt_id


def test_migration_roundtrip_and_schema_constraints(phase6_factory) -> None:
    factory, engine = phase6_factory
    with engine.connect() as connection:
        inspector = inspect(connection)
        columns = {column["name"]: column for column in inspector.get_columns("shopmind_outbox_events")}
        assert set(columns) == {
            "id",
            "aggregate_type",
            "aggregate_id",
            "aggregate_sequence",
            "event_type",
            "event_version",
            "payload",
            "occurred_at",
            "status",
            "attempt_count",
            "redrive_count",
            "available_at",
            "lease_owner",
            "lease_until",
            "last_error",
            "broker_message_id",
            "created_at",
            "updated_at",
            "published_at",
        }
        assert {name for name, column in columns.items() if not column["nullable"]} == {
            "id",
            "aggregate_type",
            "aggregate_id",
            "aggregate_sequence",
            "event_type",
            "event_version",
            "payload",
            "occurred_at",
            "status",
            "attempt_count",
            "redrive_count",
            "available_at",
            "created_at",
            "updated_at",
        }
        assert {name for name, column in columns.items() if column["nullable"]} == {
            "lease_owner",
            "lease_until",
            "last_error",
            "broker_message_id",
            "published_at",
        }
        assert {constraint["name"] for constraint in inspector.get_unique_constraints("shopmind_outbox_events")} == {
            "uq_shopmind_outbox_aggregate_sequence"
        }
        check_names = {constraint["name"] for constraint in inspector.get_check_constraints("shopmind_outbox_events")}
        assert {
            "ck_shopmind_outbox_aggregate_sequence_positive",
            "ck_shopmind_outbox_event_version_positive",
            "ck_shopmind_outbox_status",
            "ck_shopmind_outbox_attempt_count_nonnegative",
            "ck_shopmind_outbox_redrive_count_nonnegative",
            "ck_shopmind_outbox_lease_state",
            "ck_shopmind_outbox_published_state",
        } == check_names
        indexes = {index["name"]: index for index in inspector.get_indexes("shopmind_outbox_events")}
        assert {
            "idx_shopmind_outbox_claim",
            "idx_shopmind_outbox_aggregate_order",
        } <= set(indexes)
        assert indexes["idx_shopmind_outbox_claim"]["column_names"] == [
            "status",
            "available_at",
            "lease_until",
            "created_at",
            "id",
        ]
        assert indexes["idx_shopmind_outbox_aggregate_order"]["column_names"] == [
            "aggregate_type",
            "aggregate_id",
            "aggregate_sequence",
        ]

        command.downgrade(_alembic(connection), "0013_shopmind_payments")
        assert "shopmind_outbox_events" not in inspect(connection).get_table_names()
        command.upgrade(_alembic(connection), "0014_shopmind_outbox_events")
        assert "shopmind_outbox_events" in inspect(connection).get_table_names()


def test_bounded_outbox_operational_snapshot_hides_payload(phase6_factory) -> None:
    factory, _engine = phase6_factory
    session = factory()
    pending = enqueue_event(session, _event(aggregate_id=uuid4(), sequence=1))
    pending_extra = enqueue_event(session, _event(aggregate_id=uuid4(), sequence=1))
    publishing = enqueue_event(session, _event(aggregate_id=uuid4(), sequence=1))
    dead_letter = enqueue_event(session, _event(aggregate_id=uuid4(), sequence=1))
    session.flush()
    session.execute(
        update(ShopMindOutboxEvent)
        .where(ShopMindOutboxEvent.id == publishing.id)
        .values(
            status="publishing",
            lease_owner=uuid4(),
            lease_until=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
    )
    session.execute(
        update(ShopMindOutboxEvent)
        .where(ShopMindOutboxEvent.id == dead_letter.id)
        .values(
            status="dead_letter",
            last_error="request_hash=private-value " + "x" * 900,
        )
    )
    session.commit()

    snapshot = get_outbox_operational_snapshot(session, recent_limit=1)
    health = get_outbox_health_snapshot(session, count_cap=1)

    assert snapshot["pending"] == 2
    assert snapshot["publishing"] == 1
    assert snapshot["dead_letter"] == 1
    assert len(snapshot["recent_dead_letters"]) == 1
    assert len(snapshot["recent_publish_failures"]) == 1
    assert "private-value" not in str(snapshot)
    assert "payload" not in str(snapshot)
    assert health["pending"] == 1
    assert health["pending_truncated"] is True
    assert health["publishing"] == 1
    assert health["dead_letter"] == 1
    assert "recent_dead_letters" not in health
    assert "recent_publish_failures" not in health
    assert pending_extra.id != pending.id
    session.close()


def test_same_aggregate_ordering_and_different_aggregate_parallel(phase6_factory) -> None:
    factory, _engine = phase6_factory
    aggregate_a = uuid4()
    aggregate_b = uuid4()
    session = factory()
    enqueue_event(session, _event(aggregate_id=aggregate_a, sequence=1))
    enqueue_event(session, _event(aggregate_id=aggregate_a, sequence=2, event_type="shopmind.order.cancelled.v1"))
    enqueue_event(session, _event(aggregate_id=aggregate_b, sequence=1))
    session.commit()

    first = claim_pending(session, batch_size=10, lease_seconds=60)
    assert {claim.envelope.aggregate_id for claim in first} == {aggregate_a, aggregate_b}
    assert [claim.envelope.aggregate_sequence for claim in first if claim.envelope.aggregate_id == aggregate_a] == [1]
    session.commit()

    for claim in first:
        assert mark_published(
            session,
            event_id=claim.event_id,
            lease_owner=claim.lease_owner,
            broker_message_id=f"broker-{claim.event_id}",
        )
    session.commit()
    second = claim_pending(session, batch_size=10, lease_seconds=60)
    assert [(claim.envelope.aggregate_id, claim.envelope.aggregate_sequence) for claim in second] == [(aggregate_a, 2)]
    session.rollback()
    session.close()


def test_expired_reclaim_and_stale_owner_cas(phase6_factory) -> None:
    factory, _engine = phase6_factory
    session = factory()
    event = enqueue_event(session, _event(aggregate_id=uuid4(), sequence=1))
    session.commit()
    first = claim_pending(session, batch_size=1, lease_seconds=1)[0]
    session.commit()
    session.execute(
        update(ShopMindOutboxEvent)
        .where(ShopMindOutboxEvent.id == event.id)
        .values(lease_until=datetime.now(timezone.utc) - timedelta(seconds=10))
    )
    session.commit()
    assert reclaim_expired(session) == 1
    session.commit()
    second = claim_pending(session, batch_size=1, lease_seconds=60)[0]
    session.commit()
    assert second.lease_owner != first.lease_owner
    assert second.event_id == first.event_id
    assert second.attempt_count == 2
    assert not mark_published(
        session,
        event_id=event.id,
        lease_owner=first.lease_owner,
        broker_message_id="stale",
    )
    session.rollback()
    current = session.get(ShopMindOutboxEvent, event.id)
    assert current is not None
    assert current.status == "publishing"
    assert current.lease_owner == second.lease_owner
    session.close()


def test_expired_reclaim_dead_letters_at_exact_max_attempts(phase6_factory) -> None:
    factory, _engine = phase6_factory
    aggregate_id = uuid4()
    session = factory()
    first_event = enqueue_event(session, _event(aggregate_id=aggregate_id, sequence=1))
    enqueue_event(
        session,
        _event(
            aggregate_id=aggregate_id,
            sequence=2,
            event_type="shopmind.order.cancelled.v1",
        ),
    )
    session.commit()

    for attempt_number in range(1, 12):
        claim = claim_pending(session, batch_size=1, lease_seconds=60)
        assert len(claim) == 1
        assert claim[0].event_id == first_event.id
        assert claim[0].attempt_count == attempt_number
        session.commit()
        session.execute(
            update(ShopMindOutboxEvent)
            .where(ShopMindOutboxEvent.id == first_event.id)
            .values(lease_until=datetime.now(timezone.utc) - timedelta(seconds=10))
        )
        session.commit()
        assert reclaim_expired(session, max_attempts=12) == 1
        session.commit()
        current = session.get(ShopMindOutboxEvent, first_event.id)
        assert current is not None
        assert current.status == "pending"
        assert current.attempt_count == attempt_number
        assert current.last_error == "delivery lease expired before completion"

    final_claim = claim_pending(session, batch_size=1, lease_seconds=60)
    assert len(final_claim) == 1
    assert final_claim[0].attempt_count == 12
    session.commit()
    session.execute(
        update(ShopMindOutboxEvent)
        .where(ShopMindOutboxEvent.id == first_event.id)
        .values(lease_until=datetime.now(timezone.utc) - timedelta(seconds=10))
    )
    session.commit()
    assert reclaim_expired(session, max_attempts=12) == 1
    session.commit()
    dead_letter = session.get(ShopMindOutboxEvent, first_event.id)
    assert dead_letter is not None
    assert dead_letter.status == "dead_letter"
    assert dead_letter.attempt_count == 12
    assert dead_letter.last_error == "delivery lease expired before completion"
    assert claim_pending(session, batch_size=10, lease_seconds=60) == []

    assert redrive_event(session, event_id=first_event.id)
    session.commit()
    redriven = session.get(ShopMindOutboxEvent, first_event.id)
    assert redriven is not None
    assert redriven.status == "pending"
    assert redriven.attempt_count == 0
    assert redriven.redrive_count == 1
    assert redriven.last_error is None
    redrive_claim = claim_pending(session, batch_size=1, lease_seconds=60)
    assert len(redrive_claim) == 1
    assert redrive_claim[0].event_id == first_event.id
    session.commit()
    assert mark_published(
        session,
        event_id=redrive_claim[0].event_id,
        lease_owner=redrive_claim[0].lease_owner,
        broker_message_id="broker-after-redrive",
    )
    session.commit()
    published = session.get(ShopMindOutboxEvent, first_event.id)
    assert published is not None
    assert published.status == "published"
    assert published.last_error is None
    second_claim = claim_pending(session, batch_size=1, lease_seconds=60)
    assert len(second_claim) == 1
    assert second_claim[0].envelope.aggregate_sequence == 2
    session.rollback()
    session.close()


def test_outbox_publisher_republishes_same_envelope_after_mark_crash(
    phase6_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def capture_event(event_name: str, **fields: object) -> None:
        events.append((event_name, fields))

    monkeypatch.setattr("app.outbox.publisher.log_event", capture_event)
    factory, _engine = phase6_factory
    aggregate_id = uuid4()
    seed = factory()
    event = enqueue_event(seed, _event(aggregate_id=aggregate_id, sequence=1))
    seed.commit()
    event_id = event.id
    seed.close()

    class CrashAfterBrokerReceive:
        def __init__(self) -> None:
            self.deliveries: list[OutboxEventEnvelope] = []
            self.crash_before_mark = True

        def publish(self, envelope: OutboxEventEnvelope) -> str:
            self.deliveries.append(envelope.model_copy(deep=True))
            if self.crash_before_mark:
                self.crash_before_mark = False
                raise SystemExit("simulated worker crash after broker receive")
            return "broker-message-after-retry"

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    fake_publisher = CrashAfterBrokerReceive()
    settings = Settings(
        shopmind_outbox_batch_size=1,
        shopmind_outbox_lease_seconds=1,
        shopmind_outbox_max_attempts=12,
    )
    worker = OutboxPublisher(factory, settings, publisher=fake_publisher)
    with pytest.raises(SystemExit, match="simulated worker crash"):
        worker.run_once()

    crashed = factory()
    crashed.execute(
        update(ShopMindOutboxEvent)
        .where(ShopMindOutboxEvent.id == event_id)
        .values(lease_until=datetime.now(timezone.utc) - timedelta(seconds=10))
    )
    crashed.commit()
    crashed.close()

    assert worker.run_once() == 1
    assert len(fake_publisher.deliveries) == 2
    first_delivery, second_delivery = fake_publisher.deliveries
    assert first_delivery.event_id == second_delivery.event_id
    assert first_delivery.occurred_at == second_delivery.occurred_at
    assert first_delivery.aggregate_sequence == second_delivery.aggregate_sequence
    assert first_delivery.payload == second_delivery.payload

    session = factory()
    rows = session.scalars(
        select(ShopMindOutboxEvent).where(
            ShopMindOutboxEvent.aggregate_id == aggregate_id
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].id == event_id
    assert rows[0].status == "published"
    assert rows[0].attempt_count == 2
    assert rows[0].last_error is None
    assert rows[0].broker_message_id == "broker-message-after-retry"
    publish_logs = [fields for event_name, fields in events if event_name == "outbox.publish.succeeded"]
    assert publish_logs
    assert str(publish_logs[-1]["outbox_event_id"]) == str(event_id)
    assert str(publish_logs[-1]["aggregate_id"]) == str(aggregate_id)
    assert publish_logs[-1]["aggregate_sequence"] == 1
    assert "payload" not in publish_logs[-1]
    session.close()


def test_outbox_publisher_persists_only_safe_failure_diagnostic(
    phase6_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def capture_event(event_name: str, **fields: object) -> None:
        events.append((event_name, fields))

    monkeypatch.setattr("app.outbox.publisher.log_event", capture_event)
    factory, _engine = phase6_factory
    order_id, sku_id = _seed_order(factory)

    class FailingPublisher:
        def __init__(self) -> None:
            self.publish_calls = 0

        def publish(self, envelope: OutboxEventEnvelope) -> str:
            self.publish_calls += 1
            raise RuntimeError(
                "failed for alice@example.com idempotency_key=super-secret "
                "payment_method_ref=private-ref"
            )

        def startup(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    fake_publisher = FailingPublisher()
    settings = Settings(
        shopmind_outbox_batch_size=1,
        shopmind_outbox_lease_seconds=60,
        shopmind_outbox_max_attempts=12,
        shopmind_outbox_base_backoff_seconds=1,
        shopmind_outbox_max_backoff_seconds=1,
    )
    worker = OutboxPublisher(factory, settings, publisher=fake_publisher)

    assert worker.run_once() == 1
    assert fake_publisher.publish_calls == 1

    session = factory()
    try:
        event = session.scalar(
            select(ShopMindOutboxEvent).where(
                ShopMindOutboxEvent.aggregate_id == order_id,
                ShopMindOutboxEvent.event_type == "shopmind.order.created.v1",
            )
        )
        order = session.get(ShopMindOrder, order_id)
        reservation = session.scalar(
            select(ShopMindInventoryReservation)
            .join(ShopMindOrderItem)
            .where(ShopMindOrderItem.order_id == order_id)
        )
        inventory = session.get(CatalogInventory, sku_id)
        snapshot = get_outbox_operational_snapshot(session)

        assert event is not None
        assert event.status == "pending"
        assert event.attempt_count == 1
        assert event.last_error == "RocketMQ publish failed (RuntimeError)"
        assert order is not None and order.status == "pending_payment"
        assert reservation is not None and reservation.status == "active"
        assert inventory is not None
        assert inventory.on_hand_quantity == 2
        assert inventory.reserved_quantity == 1
        assert inventory.version == 1

        persisted_text = str(event.last_error)
        observed_text = str(snapshot)
        log_text = str(events)
        for secret in (
            "alice@example.com",
            "super-secret",
            "private-ref",
        ):
            assert secret not in persisted_text
            assert secret not in observed_text
            assert secret not in log_text

        failed_logs = [
            fields for event_name, fields in events
            if event_name == "outbox.publish.failed"
        ]
        assert failed_logs
        assert failed_logs[-1]["error_code"] == "publish_failed"
        assert failed_logs[-1]["error_class"] == "RuntimeError"
        assert failed_logs[-1]["error_message"] == "RocketMQ publish failed (RuntimeError)"
    finally:
        session.close()


def test_two_workers_only_one_claims_the_same_event(phase6_factory) -> None:
    factory, _engine = phase6_factory
    event_id = uuid4()
    seed = factory()
    enqueue_event(seed, _event(aggregate_id=event_id, sequence=1))
    seed.commit()
    seed.close()

    barrier = threading.Barrier(2)
    results: list[tuple[int, UUID | None]] = []
    results_lock = threading.Lock()

    def worker() -> None:
        session = factory()
        try:
            barrier.wait(timeout=10)
            claims = claim_pending(session, batch_size=1, lease_seconds=60)
            owner = claims[0].lease_owner if claims else None
            session.commit()
            with results_lock:
                results.append((len(claims), owner))
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    assert sorted(count for count, _owner in results) == [0, 1]
    assert sum(count for count, _owner in results) == 1
    assert len({owner for _count, owner in results if owner is not None}) == 1


def test_dead_letter_blocks_and_operator_redrive_unblocks(phase6_factory) -> None:
    factory, _engine = phase6_factory
    aggregate_id = uuid4()
    session = factory()
    first_event = enqueue_event(session, _event(aggregate_id=aggregate_id, sequence=1))
    enqueue_event(session, _event(aggregate_id=aggregate_id, sequence=2, event_type="shopmind.order.cancelled.v1"))
    session.commit()
    claim = claim_pending(session, batch_size=1, lease_seconds=60)[0]
    session.commit()
    assert mark_failure(
        session,
        event_id=claim.event_id,
        lease_owner=claim.lease_owner,
        attempt_count=claim.attempt_count,
        error="permanent",
        max_attempts=1,
    )
    session.commit()
    assert claim_pending(session, batch_size=10, lease_seconds=60) == []
    assert redrive_event(session, event_id=first_event.id)
    session.commit()
    redriven = claim_pending(session, batch_size=1, lease_seconds=60)
    assert len(redriven) == 1
    assert redriven[0].event_id == first_event.id
    session.rollback()
    session.close()


def test_create_cancel_and_payment_events_are_transactional(phase6_factory) -> None:
    factory, _engine = phase6_factory
    order_id, _sku_id = _seed_order(factory)
    session = factory()
    created = session.scalars(
        select(ShopMindOutboxEvent).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.created.v1",
        )
    ).all()
    assert len(created) == 1
    created_order = session.get(ShopMindOrder, order_id)
    assert created_order is not None
    assert created[0].aggregate_sequence == created_order.version
    occurred_at = created[0].occurred_at
    session.close()

    session = factory()
    cancel_order(session, user_id="phase6-user", order_id=order_id)
    session.commit()
    cancel_order(session, user_id="phase6-user", order_id=order_id)
    session.commit()
    cancelled = session.scalars(
        select(ShopMindOutboxEvent).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.cancelled.v1",
        )
    ).all()
    cancelled_order = session.get(ShopMindOrder, order_id)
    assert len(cancelled) == 1
    assert cancelled_order is not None
    assert cancelled[0].aggregate_sequence == cancelled_order.version
    assert session.scalar(
        select(ShopMindOutboxEvent.id).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.cancelled.v1",
        )
    ) is not None
    assert session.scalar(
        select(ShopMindOutboxEvent.occurred_at).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.created.v1",
        )
    ) == occurred_at
    session.close()


def test_create_rollback_removes_business_facts_and_outbox_event(phase6_factory) -> None:
    factory, _engine = phase6_factory
    order_id, sku_id = _seed_order(
        factory,
        user_id="phase6-rollback-user",
        commit_order=False,
    )
    session = factory()
    assert session.get(ShopMindOrder, order_id) is None
    assert session.scalars(
        select(ShopMindOutboxEvent).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
        )
    ).all() == []
    assert session.scalars(select(ShopMindInventoryReservation)).all() == []
    cart_items = session.scalars(
        select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase6-rollback-user")
    ).all()
    assert len(cart_items) == 1
    assert cart_items[0].quantity == 1
    inventory = session.get(CatalogInventory, sku_id)
    assert inventory is not None
    assert inventory.reserved_quantity == 0
    assert inventory.version == 0
    session.close()


def test_payment_success_event_commits_with_business_facts(phase6_factory) -> None:
    factory, _engine = phase6_factory
    order_id, _sku_id = _seed_order(factory)
    attempt_id = _complete_provider_success(factory, user_id="phase6-user", order_id=order_id)
    session = factory()
    order = session.get(ShopMindOrder, order_id)
    attempt = session.get(ShopMindPaymentAttempt, attempt_id)
    reservation = session.scalar(select(ShopMindInventoryReservation).join(ShopMindOrderItem))
    events = session.scalars(
        select(ShopMindOutboxEvent).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.payment.succeeded.v1",
        )
    ).all()
    assert order is not None and order.status == "paid"
    assert attempt is not None and attempt.status == "succeeded"
    assert reservation is not None and reservation.status == "consumed"
    assert len(events) == 1
    assert events[0].payload["payment_attempt_id"] == str(attempt_id)
    assert events[0].aggregate_sequence == order.version
    finalize_payment(session, user_id="phase6-user", order_id=order_id, attempt_id=attempt_id)
    session.commit()
    assert len(
        session.scalars(
            select(ShopMindOutboxEvent).where(
                ShopMindOutboxEvent.aggregate_id == order_id,
                ShopMindOutboxEvent.event_type == "shopmind.payment.succeeded.v1",
            )
        ).all()
    ) == 1
    session.close()


def test_payment_finalization_failure_has_no_success_event(phase6_factory) -> None:
    factory, _engine = phase6_factory
    order_id, sku_id = _seed_order(factory)
    session = factory()
    request = PaymentAttemptRequest(provider="mock", payment_method_ref="mock-card")
    claim = claim_payment_attempt(
        session,
        user_id="phase6-user",
        order_id=order_id,
        idempotency_key=f"payment-{uuid4().hex}",
        request=request,
    )
    session.commit()
    persist_provider_outcome(
        session,
        attempt_id=claim.attempt_id,
        outcome=ProviderOutcome(
            status="succeeded",
            provider_payment_id="mock-payment",
            failure_code=None,
            result_at=datetime.now(timezone.utc),
        ),
    )
    session.commit()
    session.execute(
        update(CatalogInventory)
        .where(CatalogInventory.sku_id == sku_id)
        .values(reserved_quantity=0)
    )
    session.commit()
    with pytest.raises(PaymentServiceError):
        finalize_payment(session, user_id="phase6-user", order_id=order_id, attempt_id=claim.attempt_id)
    session.rollback()
    assert session.scalar(
        select(ShopMindOutboxEvent.id).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.payment.succeeded.v1",
        )
    ) is None
    session.close()


def test_publish_failure_retries_without_mutating_business_facts(phase6_factory) -> None:
    factory, _engine = phase6_factory
    order_id, _sku_id = _seed_order(factory)
    session = factory()
    event = session.scalar(
        select(ShopMindOutboxEvent).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.created.v1",
        )
    )
    assert event is not None
    claim = claim_pending(session, batch_size=1, lease_seconds=60)[0]
    session.commit()
    assert mark_failure(
        session,
        event_id=claim.event_id,
        lease_owner=claim.lease_owner,
        attempt_count=claim.attempt_count,
        error="provider secret\x00must not leak",
        max_attempts=12,
        base_backoff_seconds=1,
        max_backoff_seconds=1,
    )
    session.commit()
    order = session.get(ShopMindOrder, order_id)
    reservation = session.scalar(select(ShopMindInventoryReservation).join(ShopMindOrderItem))
    current = session.get(ShopMindOutboxEvent, event.id)
    assert order is not None and order.status == "pending_payment"
    assert reservation is not None and reservation.status == "active"
    assert current is not None and current.status == "pending"
    assert current.attempt_count == 1
    assert "\x00" not in (current.last_error or "")
    session.close()
