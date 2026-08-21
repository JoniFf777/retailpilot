"""Local Order-expiration, payment-safety, and bounded-sweep coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.core.settings import Settings
from app.db.base import Base
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder, ShopMindOrderItem
from app.outbox.models import ShopMindOutboxEvent
from app.payments.models import ShopMindPaymentAttempt
from app.repositories.shopmind_cart import upsert_cart_item
from app.schemas.orders import CreateOrderRequest
from app.schemas.payments import PaymentAttemptRequest
from app.services.checkout import preview_checkout
from app.services.order_expiration import expire_orders_once
from app.services.orders import OrderServiceError, cancel_order, create_order
from app.services.payments import PaymentServiceError, claim_payment_attempt


@pytest.fixture
def store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session: Session = factory()
    category = CatalogCategory(
        code=f"expiration-{uuid4().hex}",
        name="Expiration",
        status="active",
        managed_by_seed=False,
    )
    product = CatalogProduct(
        product_code=f"EXP-{uuid4().hex}",
        category=category,
        brand="ShopMind",
        name="Expiration Product",
        sale_status="active",
        attributes_json={},
        managed_by_seed=False,
    )
    sku = CatalogSku(
        product=product,
        sku_code=f"EXP-SKU-{uuid4().hex}",
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
            CatalogInventory(sku=sku, on_hand_quantity=20, reserved_quantity=0, version=0),
        ]
    )
    session.commit()
    settings = Settings(
        shopmind_checkout_signing_secret="e" * 32,
        shopmind_order_payment_ttl_seconds=1_800,
    )
    sku_id = sku.id
    session.close()
    yield factory, settings, sku_id
    engine.dispose()


def _create_order(factory, settings, sku_id, *, user_id: str) -> UUID:
    session: Session = factory()
    upsert_cart_item(session, user_id=user_id, sku_id=sku_id, quantity=1)
    session.commit()
    preview = preview_checkout(session, user_id=user_id, settings=settings)
    assert preview.checkout_token
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
    return order_id


def _set_expiry(factory, order_id, expires_at: datetime) -> None:
    session: Session = factory()
    session.execute(
        update(ShopMindOrder)
        .where(ShopMindOrder.id == order_id)
        .values(expires_at=expires_at)
    )
    session.commit()
    session.close()


def _add_attempt(factory, order_id, *, user_id: str, status: str) -> None:
    now = datetime.now(timezone.utc)
    session: Session = factory()
    values = {
        "id": uuid4(),
        "order_id": order_id,
        "user_id": user_id,
        "provider": "mock",
        "provider_payment_id": "provider-test-id",
        "provider_idempotency_key": f"provider-{uuid4().hex}",
        "status": status,
        "amount": Decimal("10.00"),
        "currency": "CNY",
        "idempotency_key": f"payment-{uuid4().hex}",
        "request_hash": "a" * 64,
        "failure_code": "payment_declined" if status in {"failed", "unknown"} else None,
        "created_at": now,
        "updated_at": now,
        "provider_result_at": None if status == "processing" else now,
        "completed_at": now if status in {"failed", "succeeded"} else None,
    }
    session.add(ShopMindPaymentAttempt(**values))
    session.commit()
    session.close()


def _get_order(factory, order_id):
    session: Session = factory()
    order = session.get(ShopMindOrder, order_id)
    session.expunge(order)
    session.close()
    return order


def test_create_replay_persists_fixed_timezone_aware_deadline(store) -> None:
    factory, settings, sku_id = store
    session: Session = factory()
    upsert_cart_item(session, user_id="deadline-user", sku_id=sku_id, quantity=1)
    session.commit()
    preview = preview_checkout(session, user_id="deadline-user", settings=settings)
    assert preview.checkout_token
    idempotency_key = "deadline-replay"
    created = create_order(
        session,
        user_id="deadline-user",
        idempotency_key=idempotency_key,
        request=CreateOrderRequest(checkout_token=preview.checkout_token),
        settings=settings,
    )
    session.commit()
    order_id = created.order.order_id
    session.close()
    session: Session = factory()
    order = session.get(ShopMindOrder, order_id)
    assert order is not None
    first_deadline = order.expires_at
    assert first_deadline is not None
    replay = create_order(
        session,
        user_id="deadline-user",
        idempotency_key=idempotency_key,
        request=CreateOrderRequest(checkout_token=preview.checkout_token),
        settings=Settings(shopmind_order_payment_ttl_seconds=1),
    )
    assert replay.idempotent_replay is True
    assert replay.order.expires_at == first_deadline.replace(tzinfo=timezone.utc)
    session.rollback()
    session.close()


def test_expiry_releases_reservation_and_emits_one_event(store) -> None:
    factory, settings, sku_id = store
    order_id = _create_order(factory, settings, sku_id, user_id="expiry-user")
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    _set_expiry(factory, order_id, now - timedelta(seconds=1))

    first = expire_orders_once(factory, settings, now=now, batch_size=10)
    second = expire_orders_once(factory, settings, now=now, batch_size=10)

    assert first.as_dict() == {
        "attempted": 1,
        "expired": 1,
        "deferred_payment": 0,
        "inconsistent": 0,
        "failed": 0,
    }
    assert second.as_dict() == {
        "attempted": 0,
        "expired": 0,
        "deferred_payment": 0,
        "inconsistent": 0,
        "failed": 0,
    }
    session: Session = factory()
    order = session.get(ShopMindOrder, order_id)
    reservation = session.scalar(select(ShopMindInventoryReservation))
    inventory = session.scalar(select(CatalogInventory))
    events = session.scalars(
        select(ShopMindOutboxEvent).where(
            ShopMindOutboxEvent.aggregate_id == order_id,
            ShopMindOutboxEvent.event_type == "shopmind.order.expired.v1",
        )
    ).all()
    assert order is not None and order.status == "expired" and order.version == 2
    assert reservation is not None and reservation.status == "released"
    assert inventory is not None and inventory.reserved_quantity == 0
    assert len(events) == 1
    session.close()


@pytest.mark.parametrize("payment_status", ["processing", "unknown", "provider_succeeded"])
def test_active_or_uncertain_payment_defers_cancel_and_expiry(store, payment_status: str) -> None:
    factory, settings, sku_id = store
    order_id = _create_order(factory, settings, sku_id, user_id=f"{payment_status}-user")
    _add_attempt(factory, order_id, user_id=f"{payment_status}-user", status=payment_status)
    session: Session = factory()
    with pytest.raises(OrderServiceError) as error:
        cancel_order(session, user_id=f"{payment_status}-user", order_id=order_id)
    assert error.value.code == "payment_in_progress"
    session.rollback()
    session.close()
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    _set_expiry(factory, order_id, now - timedelta(seconds=1))
    summary = expire_orders_once(factory, settings, now=now)
    assert summary.deferred_payment == 1
    assert summary.expired == 0
    assert _get_order(factory, order_id).status == "pending_payment"


def test_succeeded_pending_payment_fails_closed_for_cancel_and_expiry(store) -> None:
    factory, settings, sku_id = store
    order_id = _create_order(factory, settings, sku_id, user_id="inconsistent-user")
    _add_attempt(factory, order_id, user_id="inconsistent-user", status="succeeded")
    session: Session = factory()
    before_inventory = session.scalar(select(CatalogInventory)).reserved_quantity
    with pytest.raises(OrderServiceError) as error:
        cancel_order(session, user_id="inconsistent-user", order_id=order_id)
    assert error.value.code == "payment_state_inconsistent"
    session.rollback()
    session.close()
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    _set_expiry(factory, order_id, now - timedelta(seconds=1))
    summary = expire_orders_once(factory, settings, now=now)
    assert summary.inconsistent == 1
    assert summary.expired == 0
    session = factory()
    order = session.get(ShopMindOrder, order_id)
    inventory = session.scalar(select(CatalogInventory))
    events = session.scalars(
        select(ShopMindOutboxEvent).where(ShopMindOutboxEvent.aggregate_id == order_id)
    ).all()
    assert order is not None and order.status == "pending_payment"
    assert inventory is not None and inventory.reserved_quantity == before_inventory
    assert not [event for event in events if event.event_type == "shopmind.order.cancelled.v1"]
    assert not [event for event in events if event.event_type == "shopmind.order.expired.v1"]
    session.close()


def test_payment_deadline_exact_boundary_rejects_new_key_but_replays_existing_key(store) -> None:
    factory, settings, sku_id = store
    order_id = _create_order(factory, settings, sku_id, user_id="payment-boundary")
    _set_expiry(factory, order_id, datetime.now(timezone.utc) + timedelta(hours=1))
    session: Session = factory()
    claim = claim_payment_attempt(
        session,
        user_id="payment-boundary",
        order_id=order_id,
        idempotency_key="existing-before-deadline",
        request=PaymentAttemptRequest(provider="mock", payment_method_ref="method"),
    )
    session.commit()
    committed_attempt_id = claim.attempt_id
    _set_expiry(factory, order_id, datetime.now(timezone.utc))
    session.expire_all()
    with pytest.raises(PaymentServiceError) as error:
        claim_payment_attempt(
            session,
            user_id="payment-boundary",
            order_id=order_id,
            idempotency_key="new-after-deadline",
            request=PaymentAttemptRequest(provider="mock", payment_method_ref="method"),
        )
    assert error.value.code == "order_expired"
    session.rollback()
    replay = claim_payment_attempt(
        session,
        user_id="payment-boundary",
        order_id=order_id,
        idempotency_key="existing-before-deadline",
        request=PaymentAttemptRequest(provider="mock", payment_method_ref="method"),
    )
    assert replay.idempotent_replay is True and replay.action == "reconcile"
    assert replay.attempt_id == committed_attempt_id
    session.close()


def test_deferred_order_does_not_starve_later_expired_order(store) -> None:
    factory, settings, sku_id = store
    first_id = _create_order(factory, settings, sku_id, user_id="deferred-first")
    second_id = _create_order(factory, settings, sku_id, user_id="expired-second")
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    _set_expiry(factory, first_id, now - timedelta(seconds=20))
    _set_expiry(factory, second_id, now - timedelta(seconds=10))
    _add_attempt(factory, first_id, user_id="deferred-first", status="processing")
    summary = expire_orders_once(factory, settings, now=now, batch_size=2)
    assert summary.attempted == 2
    assert summary.deferred_payment == 1
    assert summary.expired == 1
    assert _get_order(factory, first_id).status == "pending_payment"
    assert _get_order(factory, second_id).status == "expired"


def test_failed_order_does_not_starve_later_expired_order(store) -> None:
    factory, settings, sku_id = store
    first_id = _create_order(factory, settings, sku_id, user_id="failed-first")
    second_id = _create_order(factory, settings, sku_id, user_id="valid-second")
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    _set_expiry(factory, first_id, now - timedelta(seconds=20))
    _set_expiry(factory, second_id, now - timedelta(seconds=10))
    session: Session = factory()
    reservation = session.scalar(
        select(ShopMindInventoryReservation)
        .join(ShopMindOrderItem)
        .where(ShopMindOrderItem.order_id == first_id)
    )
    assert reservation is not None
    reservation.status = "released"
    reservation.released_at = now
    session.commit()
    session.close()
    summary = expire_orders_once(factory, settings, now=now, batch_size=2)
    assert summary.attempted == 2
    assert summary.failed == 1
    assert summary.expired == 1
    assert _get_order(factory, first_id).status == "pending_payment"
    assert _get_order(factory, second_id).status == "expired"
