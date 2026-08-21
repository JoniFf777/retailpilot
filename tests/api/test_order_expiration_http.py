"""HTTP boundary coverage for expired Order status and payment/cancel guards."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import checkout as checkout_route
from app.api.routes import orders as orders_route
from app.core.settings import Settings
from app.db.base import Base
from app.db.session import get_db_session
from app.dependencies.security import get_identity_boundary
from app.main import app
from app.orders.models import ShopMindOrder
from app.repositories.shopmind_cart import upsert_cart_item
from app.security import IdentityBoundary, IdentityProviderName
from app.services.order_expiration import expire_orders_once
from tests.cart.test_phase2a_service import seed_recommendation


SECRET_SETTINGS = Settings(shopmind_checkout_signing_secret="h" * 32)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def http_store() -> Generator[tuple[sessionmaker, Session, Settings], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield factory, session, SECRET_SETTINGS
    finally:
        session.close()
        engine.dispose()


@pytest.mark.anyio
async def test_expired_order_http_read_payment_and_cancel_contract(
    http_store: tuple[sessionmaker, Session, Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, session, settings = http_store
    sku_id = seed_recommendation(session)
    upsert_cart_item(session, user_id="expired-http", sku_id=sku_id, quantity=1)
    session.commit()

    def override_db():
        request_session = factory()
        try:
            yield request_session
        finally:
            request_session.close()

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = lambda: IdentityBoundary(
        IdentityProviderName.DEVELOPMENT_PAYLOAD
    )
    try:
        monkeypatch.setattr(checkout_route, "get_settings", lambda: settings)
        monkeypatch.setattr(orders_route, "get_settings", lambda: settings)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            preview = await client.post(
                "/api/checkout/preview",
                params={"user_id": "expired-http"},
                json={},
            )
            assert preview.status_code == 200
            created = await client.post(
                "/api/orders",
                params={"user_id": "expired-http"},
                headers={"Idempotency-Key": "expired-http-order"},
                json={"checkout_token": preview.json()["checkout_token"]},
            )
            assert created.status_code == 201, created.text
            order_id = created.json()["order"]["order_id"]
            now = datetime.now(timezone.utc)
            mutation = factory()
            mutation.execute(
                update(ShopMindOrder)
                .where(ShopMindOrder.id == UUID(order_id))
                .values(expires_at=now - timedelta(seconds=1))
            )
            mutation.commit()
            mutation.close()
            summary = expire_orders_once(factory, settings, now=now)
            assert summary.expired == 1

            detail = await client.get(
                f"/api/orders/{order_id}", params={"user_id": "expired-http"}
            )
            assert detail.status_code == 200
            assert detail.json()["status"] == "expired"
            assert detail.json()["expires_at"]

            payment = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "expired-http"},
                headers={"Idempotency-Key": "expired-http-payment"},
                json={"provider": "mock", "payment_method_ref": "method"},
            )
            assert payment.status_code == 409
            assert payment.json()["code"] == "order_expired"

            cancel = await client.post(
                f"/api/orders/{order_id}/cancel",
                params={"user_id": "expired-http"},
            )
            assert cancel.status_code == 409
            assert cancel.json()["code"] == "order_not_cancellable"
    finally:
        app.dependency_overrides.clear()
