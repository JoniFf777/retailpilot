from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db_session
from app.dependencies.security import get_identity_boundary
from app.main import app
from app.catalog.models import CatalogInventory, CatalogSku
from app.repositories.shopmind_cart import upsert_cart_item
from app.security import IdentityBoundary, IdentityProviderName
from tests.cart.test_phase2a_service import seed_recommendation


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def phase3a_session() -> Generator:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.mark.anyio
async def test_cart_patch_delete_and_clear_use_authenticated_owner(phase3a_session) -> None:
    sku_id = seed_recommendation(phase3a_session)
    item = upsert_cart_item(phase3a_session, user_id="user-1", sku_id=sku_id, quantity=1)
    phase3a_session.commit()

    def override_db():
        yield phase3a_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = lambda: IdentityBoundary(
        IdentityProviderName.TRUSTED_HEADER, trusted_subject="user-1"
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            updated = await client.patch(
                f"/api/cart/items/{item.id}",
                json={"expected_version": 1, "quantity": 2},
            )
            assert updated.status_code == 200
            assert updated.json()["item"]["quantity"] == 2
            assert updated.json()["cart"]["subtotal"]["amount"] == "11998.00"

            conflict = await client.patch(
                f"/api/cart/items/{item.id}",
                json={"expected_version": 1, "quantity": 3},
            )
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "cart_version_conflict"

            limit = await client.patch(
                f"/api/cart/items/{item.id}",
                json={"expected_version": 2, "quantity": 21},
            )
            assert limit.status_code == 409
            assert limit.json()["code"] == "cart_quantity_limit"

            removed = await client.delete(f"/api/cart/items/{item.id}")
            assert removed.status_code == 204
            repeated = await client.delete(f"/api/cart/items/{item.id}")
            assert repeated.status_code == 204

            cleared = await client.delete("/api/cart")
            assert cleared.status_code == 204
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_identity_boundary, None)


@pytest.mark.anyio
async def test_cart_mutation_has_no_user_id_request_field(phase3a_session) -> None:
    sku_id = seed_recommendation(phase3a_session)
    item = upsert_cart_item(phase3a_session, user_id="user-1", sku_id=sku_id, quantity=1)
    phase3a_session.commit()

    def override_db():
        yield phase3a_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = lambda: IdentityBoundary(
        IdentityProviderName.TRUSTED_HEADER, trusted_subject="user-1"
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/cart/items/{item.id}",
                json={"user_id": "user-2", "expected_version": 1, "quantity": 2},
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_identity_boundary, None)


def test_cart_openapi_contract_is_typed_and_ownerless_request() -> None:
    schema = app.openapi()
    schemas = schema["components"]["schemas"]
    assert {"CartResponse", "CartMutationResponse", "CartWarning", "CartErrorResponse"}.issubset(schemas)
    request_properties = schemas["UpdateCartItemRequest"]["properties"]
    assert set(request_properties) == {"expected_version", "quantity"}
    assert schemas["CartErrorResponse"]["properties"]["code"]["enum"]
    patch = schema["paths"]["/api/cart/items/{cart_item_id}"]["patch"]
    assert patch["responses"]["409"]["content"]["application/json"]["schema"]["$ref"].endswith("/CartErrorResponse")


@pytest.mark.anyio
async def test_cart_read_order_remains_updated_at_then_id(phase3a_session) -> None:
    first_sku = seed_recommendation(phase3a_session)
    first = phase3a_session.get(CatalogSku, first_sku)
    second = CatalogSku(
        product=first.product,
        sku_code=f"LP-ORDER-{uuid4().hex}",
        name="32GB",
        money_amount=Decimal("6999.00"),
        currency="CNY",
        sale_status="active",
        variant_attributes_json={},
    )
    phase3a_session.add_all([
        second,
        CatalogInventory(sku=second, on_hand_quantity=5, reserved_quantity=0, version=0),
    ])
    phase3a_session.flush()
    second_sku = second.id
    later = upsert_cart_item(phase3a_session, user_id="user-1", sku_id=first_sku, quantity=1)
    earlier = upsert_cart_item(phase3a_session, user_id="user-1", sku_id=second_sku, quantity=1)
    later.updated_at = datetime.now(timezone.utc)
    earlier.updated_at = later.updated_at - timedelta(seconds=1)
    phase3a_session.commit()

    def override_db():
        yield phase3a_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = lambda: IdentityBoundary(
        IdentityProviderName.TRUSTED_HEADER, trusted_subject="user-1"
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/cart")
        assert response.status_code == 200
        assert [item["cart_item_id"] for item in response.json()["items"]] == [
            str(earlier.id),
            str(later.id),
        ]
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_identity_boundary, None)
