from collections.abc import Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db_session
from app.dependencies.security import get_identity_boundary
from app.main import app
from app.security import IdentityBoundary, IdentityProviderName
from scripts.seed_shopmind_catalog import load_catalog_seed, seed_catalog


@pytest.fixture
def browse_session() -> Generator:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for path in sorted(Path("data/catalog").glob("*_catalog.json")):
        seed_catalog(session, load_catalog_seed(path))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def browse_overrides(browse_session):
    def override_db():
        yield browse_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = lambda: IdentityBoundary(
        IdentityProviderName.DEVELOPMENT_PAYLOAD
    )
    yield
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_identity_boundary, None)


@pytest.mark.anyio
async def test_catalog_browse_is_registry_backed_and_generic(browse_overrides) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        categories = await client.get("/api/catalog/categories")
        assert categories.status_code == 200
        assert [item["code"] for item in categories.json()["items"]] == [
            "camera", "headphones", "keyboard", "laptop", "monitor", "mouse", "phone", "router", "speaker", "tablet"
        ]

        phone = await client.get("/api/catalog/products", params={"category": "智能手机"})
        assert phone.status_code == 200
        payload = phone.json()
        assert payload["category"]["code"] == "phone"
        assert payload["total"] == 9
        assert all(item["category"]["code"] == "phone" for item in payload["items"])
        assert all(item["specifications"] for item in payload["items"])
        assert any(not item["skus"][0]["availability"]["in_stock"] for item in payload["items"])

        keyboard = await client.get("/api/catalog/products", params={"category": "keyboard"})
        router = await client.get("/api/catalog/products", params={"category": "router"})
        assert keyboard.status_code == router.status_code == 200
        assert keyboard.json()["items"][0]["specifications"]
        assert router.json()["items"][0]["specifications"]

        product_code = payload["items"][0]["product_code"]
        detail = await client.get(f"/api/catalog/products/{product_code}")
        assert detail.status_code == 200
        assert detail.json()["product_code"] == product_code
        assert detail.json()["description"]


@pytest.mark.anyio
async def test_catalog_browse_safe_errors_and_canonical_hitl(browse_overrides) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unsupported = await client.get("/api/catalog/products", params={"category": "printer"})
        assert unsupported.status_code == 404
        assert unsupported.json() == {
            "code": "unsupported_category",
            "message": "This Catalog category is not supported.",
        }

        products = (await client.get("/api/catalog/products", params={"category": "router"})).json()["items"]
        sku = next(item["skus"][0] for item in products if item["skus"][0]["availability"]["in_stock"])
        prepared = await client.post(
            "/api/pending-actions/catalog-add-to-cart",
            json={"user_id": "browse-user", "thread_id": "browse-thread", "sku_id": sku["sku_id"], "quantity": 1},
        )
        assert prepared.status_code == 201
        action = prepared.json()
        assert action["preview"]["sku_id"] == sku["sku_id"]

        cart_before = await client.get("/api/cart", params={"user_id": "browse-user"})
        assert cart_before.status_code == 200
        assert cart_before.json()["items"] == []

        confirmed = await client.post(
            f"/api/pending-actions/{action['pending_action_id']}/confirm",
            json={"user_id": "browse-user", "thread_id": "browse-thread", "expected_version": action["version"]},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["cart_item"]["sku_id"] == sku["sku_id"]

        missing = await client.get("/api/catalog/products/NO-SUCH-PRODUCT")
        assert missing.status_code == 404
        assert missing.json()["code"] == "catalog_not_found"
