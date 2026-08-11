from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.cart.models import ShopMindCartItem
from app.core.settings import Settings
from app.db.base import Base
from app.orders.models import ShopMindInventoryReservation, ShopMindOrder
from app.repositories.shopmind_cart import upsert_cart_item
from app.schemas.orders import CreateOrderRequest
from app.services.checkout import preview_checkout
from app.services.orders import OrderServiceError, cancel_order, create_order


def _store() -> tuple[sessionmaker, object, Settings]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    category = CatalogCategory(code=f"phase4a-{uuid4().hex}", name="Laptop", status="active", managed_by_seed=False)
    product = CatalogProduct(
        product_code=f"P4A-{uuid4().hex}",
        category=category,
        brand="ShopMind",
        name="Phase 4A Laptop",
        sale_status="active",
        attributes_json={},
        managed_by_seed=False,
    )
    sku = CatalogSku(
        product=product,
        sku_code=f"P4A-SKU-{uuid4().hex}",
        name="16GB",
        money_amount=Decimal("5999.00"),
        currency="CNY",
        sale_status="active",
        variant_attributes_json={},
        managed_by_seed=False,
    )
    inventory = CatalogInventory(sku=sku, on_hand_quantity=2, reserved_quantity=0, version=0)
    session.add_all([category, product, sku, inventory])
    session.flush()
    upsert_cart_item(session, user_id="phase4a-user", sku_id=sku.id, quantity=1)
    session.commit()
    return factory, engine, Settings(shopmind_checkout_signing_secret="s" * 32)


def test_preview_create_replay_cancel_and_owner_scoped_order_state() -> None:
    factory, engine, settings = _store()
    session: Session = factory()
    preview = preview_checkout(session, user_id="phase4a-user", settings=settings)
    assert preview.can_create_order and preview.checkout_token
    result = create_order(
        session,
        user_id="phase4a-user",
        idempotency_key="phase4a-key",
        request=CreateOrderRequest(checkout_token=preview.checkout_token),
        settings=settings,
    )
    session.commit()
    assert result.idempotent_replay is False
    assert session.scalars(select(ShopMindCartItem).where(ShopMindCartItem.user_id == "phase4a-user")).all() == []
    inventory = session.scalar(select(CatalogInventory))
    assert (inventory.reserved_quantity, inventory.version) == (1, 1)
    replay = create_order(
        session,
        user_id="phase4a-user",
        idempotency_key="phase4a-key",
        request=CreateOrderRequest(checkout_token=preview.checkout_token),
        settings=Settings(),
    )
    assert replay.idempotent_replay is True
    cancelled = cancel_order(session, user_id="phase4a-user", order_id=result.order.order_id)
    session.commit()
    assert cancelled.order.status == "cancelled"
    assert session.scalar(select(ShopMindInventoryReservation).where(ShopMindInventoryReservation.status == "released"))
    inventory = session.scalar(select(CatalogInventory))
    assert (inventory.reserved_quantity, inventory.version) == (0, 2)
    cancelled_again = cancel_order(session, user_id="phase4a-user", order_id=result.order.order_id)
    assert cancelled_again.idempotent_replay is True
    session.close()
    engine.dispose()


def test_idempotency_conflict_does_not_use_mutable_cart_validation() -> None:
    factory, engine, settings = _store()
    session: Session = factory()
    preview = preview_checkout(session, user_id="phase4a-user", settings=settings)
    first = CreateOrderRequest(checkout_token=preview.checkout_token)
    create_order(session, user_id="phase4a-user", idempotency_key="same-key", request=first, settings=settings)
    session.commit()
    with pytest.raises(OrderServiceError) as conflict:
        create_order(
            session,
            user_id="phase4a-user",
            idempotency_key="same-key",
            request=CreateOrderRequest(checkout_token=preview.checkout_token + "x"),
            settings=Settings(),
        )
    assert conflict.value.code == "idempotency_conflict"
    session.rollback()
    session.close()
    engine.dispose()


def test_preview_empty_and_create_revalidation_errors_are_typed() -> None:
    factory, engine, settings = _store()
    session: Session = factory()
    cart_item = session.scalar(select(ShopMindCartItem))
    session.delete(cart_item)
    session.commit()
    empty = preview_checkout(session, user_id="phase4a-user", settings=settings)
    assert not empty.can_create_order and empty.checkout_token is None
    session.close()
    engine.dispose()

    factory, engine, settings = _store()
    session = factory()
    preview = preview_checkout(session, user_id="phase4a-user", settings=settings)
    sku = session.scalar(select(CatalogSku))
    sku.money_amount = Decimal("6000.00")
    session.commit()
    with pytest.raises(OrderServiceError) as price_changed:
        create_order(
            session,
            user_id="phase4a-user",
            idempotency_key="price-change",
            request=CreateOrderRequest(checkout_token=preview.checkout_token),
            settings=settings,
        )
    assert price_changed.value.code == "price_changed"
    session.rollback()
    session.close()
    engine.dispose()
