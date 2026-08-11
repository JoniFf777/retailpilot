from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db_session
from app.dependencies.security import get_identity_boundary
from app.main import app
from app.security import IdentityBoundary, IdentityProviderName
from tests.cart.test_phase2a_service import seed_recommendation


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def phase2a_session() -> Generator:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.mark.anyio
async def test_structured_pending_action_and_sku_cart_api(phase2a_session) -> None:
    sku_id = seed_recommendation(phase2a_session)

    def override_db():
        yield phase2a_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_identity_boundary] = lambda: IdentityBoundary(
        IdentityProviderName.DEVELOPMENT_PAYLOAD
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/pending-actions/add-to-cart",
                json={
                    "user_id": "user-1", "thread_id": "thread-1", "source_run_id": "run-1",
                    "sku_id": str(sku_id), "quantity": 2,
                },
            )
            assert created.status_code == 201
            action = created.json()
            assert action["preview"]["sku_id"] == str(sku_id)

            confirmed = await client.post(
                f"/api/pending-actions/{action['pending_action_id']}/confirm",
                json={"user_id": "user-1", "thread_id": "thread-1", "expected_version": 1},
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["cart_item"]["quantity"] == 2

            cart = await client.get("/api/cart", params={"user_id": "user-1"})
            assert cart.status_code == 200
            assert cart.json()["items"][0]["sku_id"] == str(sku_id)

            replay = await client.post(
                f"/api/pending-actions/{action['pending_action_id']}/confirm",
                json={"user_id": "user-1", "thread_id": "thread-1", "expected_version": 1},
            )
            assert replay.status_code == 200
            assert replay.json()["idempotent_replay"] is True
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_identity_boundary, None)
