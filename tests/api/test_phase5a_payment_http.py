from collections.abc import Generator
import json
import logging
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import checkout as checkout_route
from app.api.routes import orders as orders_route
from app.api.routes import payments as payments_route
from app.catalog.models import CatalogInventory
from app.core.settings import Settings
from app.db.base import Base
from app.db.session import get_db_session
from app.dependencies.security import get_identity_boundary
from app.main import app
from app.payments.providers import MockPaymentProvider
from app.payments.models import ShopMindPaymentAttempt
from app.repositories.shopmind_cart import upsert_cart_item
from app.security import IdentityBoundary, IdentityProviderName
from tests.cart.test_phase2a_service import seed_recommendation


SECRET_SETTINGS = Settings(shopmind_checkout_signing_secret="h" * 32)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def payment_http_session() -> Generator[Session, None, None]:
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
    provider: MockPaymentProvider,
) -> None:
    def override_db():
        yield session

    def override_identity() -> IdentityBoundary:
        return IdentityBoundary(
            IdentityProviderName.DEVELOPMENT_PAYLOAD,
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = override_identity
    app.dependency_overrides[payments_route.get_payment_provider] = lambda: provider
    monkeypatch.setattr(checkout_route, "get_settings", lambda: SECRET_SETTINGS)
    monkeypatch.setattr(orders_route, "get_settings", lambda: SECRET_SETTINGS)


def _install_identity_and_db_overrides(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def override_db():
        yield session

    def override_identity() -> IdentityBoundary:
        return IdentityBoundary(
            IdentityProviderName.DEVELOPMENT_PAYLOAD,
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = override_identity
    monkeypatch.setattr(checkout_route, "get_settings", lambda: SECRET_SETTINGS)
    monkeypatch.setattr(orders_route, "get_settings", lambda: SECRET_SETTINGS)


def _seed_order(session: Session, *, user_id: str, stock: int = 2) -> tuple[str, str]:
    sku_id = seed_recommendation(session)
    inventory = session.get(CatalogInventory, sku_id)
    assert inventory is not None
    inventory.on_hand_quantity = stock
    upsert_cart_item(session, user_id=user_id, sku_id=sku_id, quantity=1)
    session.commit()
    return str(sku_id), user_id


async def _create_order(client: AsyncClient) -> str:
    preview = await client.post("/api/checkout/preview", json={}, params={"user_id": "payment-owner"})
    assert preview.status_code == 200
    created = await client.post(
        "/api/orders",
        params={"user_id": "payment-owner"},
        headers={"Idempotency-Key": "order-for-payment"},
        json={"checkout_token": preview.json()["checkout_token"]},
    )
    assert created.status_code == 201
    return created.json()["order"]["order_id"]


@pytest.mark.anyio
async def test_payment_http_success_replay_and_get(
    payment_http_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="shopmind.observability")
    _seed_order(payment_http_session, user_id="payment-owner")
    provider = MockPaymentProvider()
    _install_overrides(monkeypatch, payment_http_session, provider)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            order_id = await _create_order(client)
            first = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={
                    "Idempotency-Key": "payment-key",
                    "X-Correlation-ID": "demo-payment-correlation",
                },
                json={"provider": "mock", "payment_method_ref": "method-a"},
            )
            assert first.status_code == 200
            assert first.json()["payment_attempt"]["status"] == "succeeded"
            assert first.json()["order"]["status"] == "paid"
            assert first.json()["order"]["version"] == 2
            payment_logs = [
                json.loads(record.getMessage())
                for record in caplog.records
                if record.name == "shopmind.observability"
                and json.loads(record.getMessage()).get("correlation_id")
                == "demo-payment-correlation"
            ]
            claimed = [
                record for record in payment_logs if record.get("event") == "payment.claimed"
            ]
            finalized = [
                record
                for record in payment_logs
                if record.get("event") == "payment.finalization.succeeded"
            ]
            assert claimed and finalized
            assert claimed[-1]["order_id"] == order_id
            assert claimed[-1]["payment_attempt_id"]
            assert finalized[-1]["order_id"] == order_id
            assert finalized[-1]["payment_attempt_id"] == claimed[-1]["payment_attempt_id"]
            assert all(record.get("request_id") for record in payment_logs)
            assert all(record.get("trace_id") for record in payment_logs)

            replay = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "payment-key"},
                json={"provider": "mock", "payment_method_ref": "method-a"},
            )
            assert replay.status_code == 200
            assert replay.json()["idempotent_replay"] is True
            assert provider.charge_calls == 1

            listed = await client.get(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
            )
            assert listed.status_code == 200
            assert [item["status"] for item in listed.json()["items"]] == ["succeeded"]

            inventory = payment_http_session.scalar(select(CatalogInventory))
            assert inventory is not None
            assert (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version) == (1, 0, 2)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_payment_http_decline_unknown_reconcile_and_conflict(
    payment_http_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_order(payment_http_session, user_id="payment-owner")
    provider = MockPaymentProvider(
        scenarios_by_method={
            "decline": ("declined",),
            "unknown": ("unknown", "success"),
        }
    )
    _install_overrides(monkeypatch, payment_http_session, provider)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            order_id = await _create_order(client)
            declined = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "declined-key"},
                json={"provider": "mock", "payment_method_ref": "decline"},
            )
            assert declined.status_code == 402
            assert declined.json()["code"] == "payment_declined"

            replay = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "declined-key"},
                json={"provider": "mock", "payment_method_ref": "decline"},
            )
            assert replay.status_code == 402
            assert replay.json()["idempotent_replay"] is True

            conflict = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "declined-key"},
                json={"provider": "mock", "payment_method_ref": "other"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "idempotency_conflict"

            unknown = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "unknown-key"},
                json={"provider": "mock", "payment_method_ref": "unknown"},
            )
            assert unknown.status_code == 202
            assert unknown.json()["payment_attempt"]["status"] == "unknown"

            reconciled = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "unknown-key"},
                json={"provider": "mock", "payment_method_ref": "unknown"},
            )
            assert reconciled.status_code == 200
            assert reconciled.json()["payment_attempt"]["status"] == "succeeded"
            assert provider.charge_calls == 2
            assert provider.get_result_calls >= 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_payment_http_owner_boundary_and_body_contract(
    payment_http_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_order(payment_http_session, user_id="payment-owner")
    _install_overrides(monkeypatch, payment_http_session, MockPaymentProvider())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            order_id = await _create_order(client)
            missing_key = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                json={"provider": "mock", "payment_method_ref": "method"},
            )
            assert missing_key.status_code == 422

            body_owner = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "body-owner"},
                json={"provider": "mock", "payment_method_ref": "method", "user_id": "other"},
            )
            assert body_owner.status_code == 422

            other_owner = await client.get(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "other"},
            )
            assert other_owner.status_code == 404
            assert other_owner.json()["code"] == "order_not_found"

            missing = await client.get(
                "/api/orders/00000000-0000-0000-0000-000000000000/payments",
                params={"user_id": "payment-owner"},
            )
            assert missing.status_code == 404
            assert missing.json()["code"] == "order_not_found"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_default_payment_dependency_reuses_provider_operation_across_http_reconcile(
    payment_http_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_order(payment_http_session, user_id="payment-owner")
    provider = MockPaymentProvider(
        scenarios_by_method={"unknown": ("unknown", "success")}
    )
    monkeypatch.setattr(payments_route, "_default_payment_provider", provider)
    assert payments_route.get_payment_provider() is payments_route.get_payment_provider()
    _install_identity_and_db_overrides(payment_http_session, monkeypatch)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            order_id = await _create_order(client)
            first = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "default-provider-key"},
                json={"provider": "mock", "payment_method_ref": "unknown"},
            )
            assert first.status_code == 202

            attempt = payment_http_session.scalar(select(ShopMindPaymentAttempt))
            assert attempt is not None
            provider_key = attempt.provider_idempotency_key
            operation_id = provider._operations[provider_key].provider_payment_id

            second = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={"Idempotency-Key": "default-provider-key"},
                json={"provider": "mock", "payment_method_ref": "unknown"},
            )
            assert second.status_code == 200
            assert second.json()["payment_attempt"]["status"] == "succeeded"
            assert provider.charge_calls == 1
            assert provider.get_result_calls == 2
            assert provider._operations[provider_key].provider_payment_id == operation_id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_payment_unexpected_exception_logs_only_generic_safe_fields(
    payment_http_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _install_identity_and_db_overrides(payment_http_session, monkeypatch)

    def raise_unexpected(*_args, **_kwargs):
        raise RuntimeError(
            "user_id=alice@example.com payment_method_ref=private-ref "
            "idempotency_key=key-secret provider_idempotency_key=provider-secret"
        )

    monkeypatch.setattr(payments_route, "claim_payment_attempt", raise_unexpected)
    caplog.set_level(logging.INFO, logger="shopmind.observability")
    order_id = "00000000-0000-0000-0000-000000000001"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/orders/{order_id}/payments",
                params={"user_id": "payment-owner"},
                headers={
                    "Idempotency-Key": "safe-payment-error-key",
                    "X-Correlation-ID": "safe-payment-correlation",
                },
                json={"provider": "mock", "payment_method_ref": "private-ref"},
            )
        assert response.status_code == 500
        failed = [
            json.loads(record.getMessage())
            for record in caplog.records
            if record.name == "shopmind.observability"
            and json.loads(record.getMessage()).get("event")
            == "payment.finalization.pending_or_failed"
        ]
        assert failed
        payload = failed[-1]
        assert payload["error_class"] == "RuntimeError"
        assert payload["error_code"] == "unexpected_payment_error"
        assert payload["error_message"] == "Unexpected Payment service failure."
        serialized = json.dumps(payload)
        assert "alice@example.com" not in serialized
        assert "private-ref" not in serialized
        assert "key-secret" not in serialized
        assert "provider-secret" not in serialized
    finally:
        app.dependency_overrides.clear()
