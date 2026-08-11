"""HTTP/ASGI acceptance coverage for the Phase 4A public boundary."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import checkout as checkout_route
from app.api.routes import orders as orders_route
from app.cart.models import ShopMindCartItem
from app.checkout.tokens import CheckoutPriceLine, build_cart_fingerprint, create_checkout_token
from app.core.settings import Settings
from app.db.base import Base
from app.db.session import get_db_session
from app.dependencies.security import get_identity_boundary
from app.main import app
from app.repositories.shopmind_cart import upsert_cart_item
from app.security import IdentityBoundary, IdentityProviderName
from tests.cart.test_phase2a_service import seed_recommendation


SECRET_SETTINGS = Settings(shopmind_checkout_signing_secret="h" * 32)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def phase4a_http_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _install_overrides(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    *,
    provider: IdentityProviderName,
    subject: str | None = None,
):
    current_subject = {"value": subject}

    def override_db():
        yield session

    def override_identity() -> IdentityBoundary:
        return IdentityBoundary(provider, trusted_subject=current_subject["value"])

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = override_identity
    monkeypatch.setattr(checkout_route, "get_settings", lambda: SECRET_SETTINGS)
    monkeypatch.setattr(orders_route, "get_settings", lambda: SECRET_SETTINGS)
    return current_subject


def _seed_cart(session: Session, *, user_id: str) -> tuple[object, object]:
    sku_id = seed_recommendation(session)
    item = upsert_cart_item(session, user_id=user_id, sku_id=sku_id, quantity=1)
    session.commit()
    return sku_id, item


@pytest.mark.anyio
async def test_orders_http_trusted_identity_full_lifecycle_and_typed_errors(
    phase4a_http_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="shopmind.observability")
    sku_id, cart_item = _seed_cart(phase4a_http_session, user_id="trusted-owner")
    current_subject = _install_overrides(
        monkeypatch,
        phase4a_http_session,
        provider=IdentityProviderName.TRUSTED_HEADER,
        subject="trusted-owner",
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            invalid = await client.post(
                "/api/orders",
                headers={"Idempotency-Key": "invalid-token"},
                json={"checkout_token": "v1.bad.bad"},
            )
            assert invalid.status_code == 409
            assert invalid.json()["code"] == "checkout_invalid"

            missing_key = await client.post("/api/orders", json={"checkout_token": "missing-key"})
            assert missing_key.status_code == 422
            assert "detail" in missing_key.json()

            body_owner = await client.post("/api/checkout/preview", json={"user_id": "other"})
            assert body_owner.status_code == 422

            body_owner_order = await client.post(
                "/api/orders",
                headers={"Idempotency-Key": "body-owner"},
                json={"checkout_token": "v1.bad.bad", "user_id": "other"},
            )
            assert body_owner_order.status_code == 422

            expired = create_checkout_token(
                user_id="trusted-owner",
                cart_fingerprint=build_cart_fingerprint(
                    [{"cart_item_id": cart_item.id, "sku_id": sku_id, "quantity": 1, "version": 1}]
                ),
                price_lines=[CheckoutPriceLine(sku_id=sku_id, unit_price_amount="5999.00", currency="CNY")],
                currency="CNY",
                subtotal_amount=Decimal("5999.00"),
                secret="h" * 32,
                ttl_seconds=1,
                now=datetime.now(timezone.utc) - timedelta(seconds=2),
            )
            expired_response = await client.post(
                "/api/orders",
                headers={"Idempotency-Key": "expired-token"},
                json={"checkout_token": expired},
            )
            assert expired_response.status_code == 410
            assert expired_response.json()["code"] == "checkout_expired"

            preview = await client.post("/api/checkout/preview", json={})
            assert preview.status_code == 200
            token = preview.json()["checkout_token"]
            assert token

            created = await client.post(
                "/api/orders",
                headers={
                    "Idempotency-Key": "http-lifecycle",
                    "X-Correlation-ID": "demo-correlation",
                },
                json={"checkout_token": token},
            )
            assert created.status_code == 201
            assert created.json()["idempotent_replay"] is False
            order_id = created.json()["order"]["order_id"]
            order_logs = [
                json.loads(record.getMessage())
                for record in caplog.records
                if record.name == "shopmind.observability"
                and json.loads(record.getMessage()).get("event")
                == "order.create.succeeded"
                and json.loads(record.getMessage()).get("order_id") == order_id
            ]
            assert order_logs
            assert order_logs[-1]["correlation_id"] == "demo-correlation"
            assert order_logs[-1]["request_id"]
            assert order_logs[-1]["trace_id"]

            replay = await client.post(
                "/api/orders",
                headers={"Idempotency-Key": "http-lifecycle"},
                json={"checkout_token": token},
            )
            assert replay.status_code == 201
            assert replay.json()["idempotent_replay"] is True

            listed = await client.get("/api/orders")
            assert listed.status_code == 200 and [row["order_id"] for row in listed.json()["items"]] == [order_id]
            detail = await client.get(f"/api/orders/{order_id}")
            assert detail.status_code == 200

            current_subject["value"] = "other-owner"
            hidden_detail = await client.get(f"/api/orders/{order_id}")
            hidden_cancel = await client.post(f"/api/orders/{order_id}/cancel")
            assert (hidden_detail.status_code, hidden_detail.json()["code"]) == (404, "order_not_found")
            assert (hidden_cancel.status_code, hidden_cancel.json()["code"]) == (404, "order_not_found")

            current_subject["value"] = "trusted-owner"
            cancelled = await client.post(f"/api/orders/{order_id}/cancel")
            assert cancelled.status_code == 200 and cancelled.json()["idempotent_replay"] is False
            cancelled_replay = await client.post(f"/api/orders/{order_id}/cancel")
            assert cancelled_replay.status_code == 200 and cancelled_replay.json()["idempotent_replay"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_checkout_http_development_query_compatibility_and_unavailable(
    phase4a_http_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_cart(phase4a_http_session, user_id="development-owner")
    _install_overrides(
        monkeypatch,
        phase4a_http_session,
        provider=IdentityProviderName.DEVELOPMENT_PAYLOAD,
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            preview = await client.post("/api/checkout/preview", params={"user_id": "development-owner"}, json={})
            assert preview.status_code == 200 and preview.json()["can_create_order"] is True
            token = preview.json()["checkout_token"]

            monkeypatch.setattr(checkout_route, "get_settings", lambda: Settings())
            unavailable = await client.post("/api/checkout/preview", params={"user_id": "development-owner"}, json={})
            assert unavailable.status_code == 503
            assert unavailable.json()["code"] == "checkout_unavailable"

            monkeypatch.setattr(orders_route, "get_settings", lambda: Settings())
            unavailable_create = await client.post(
                "/api/orders",
                params={"user_id": "development-owner"},
                headers={"Idempotency-Key": "development-unavailable"},
                json={"checkout_token": token},
            )
            assert unavailable_create.status_code == 503
            assert unavailable_create.json()["code"] == "checkout_unavailable"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_order_unexpected_exception_logs_only_generic_safe_fields(
    phase4a_http_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _install_overrides(
        monkeypatch,
        phase4a_http_session,
        provider=IdentityProviderName.TRUSTED_HEADER,
        subject="trusted-owner",
    )

    def raise_unexpected(*_args, **_kwargs):
        raise RuntimeError(
            "user_id=alice@example.com payment_method_ref=private-ref "
            "checkout_token=checkout-secret request_hash=hash-secret"
        )

    monkeypatch.setattr(orders_route, "create_order", raise_unexpected)
    caplog.set_level(logging.INFO, logger="shopmind.observability")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/orders",
                headers={
                    "Idempotency-Key": "safe-error-key",
                    "X-Correlation-ID": "safe-error-correlation",
                },
                json={"checkout_token": "checkout-secret"},
            )
        assert response.status_code == 500
        failed = [
            json.loads(record.getMessage())
            for record in caplog.records
            if record.name == "shopmind.observability"
            and json.loads(record.getMessage()).get("event") == "order.create.failed"
        ]
        assert failed
        payload = failed[-1]
        assert payload["error_class"] == "RuntimeError"
        assert payload["error_code"] == "unexpected_order_error"
        assert payload["error_message"] == "Unexpected Order service failure."
        serialized = json.dumps(payload)
        assert "alice@example.com" not in serialized
        assert "private-ref" not in serialized
        assert "checkout-secret" not in serialized
        assert "hash-secret" not in serialized
    finally:
        app.dependency_overrides.clear()
