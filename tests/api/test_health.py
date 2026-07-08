import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import health
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_postgres_health_check_returns_report(monkeypatch) -> None:
    def fake_report():
        return {
            "status": "ok",
            "database": "retailpilot_v2_smoke",
            "user": "postgres",
            "alembic_version": "0002_documents_pgvector",
        }

    monkeypatch.setattr(health, "get_postgres_health_report", fake_report)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/postgres")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "retailpilot_v2_smoke",
        "user": "postgres",
        "alembic_version": "0002_documents_pgvector",
    }


@pytest.mark.anyio
async def test_postgres_health_check_returns_503_on_failure(monkeypatch) -> None:
    def fail_report():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(health, "get_postgres_health_report", fail_report)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/postgres")

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "error"
    assert response.json()["detail"]["message"] == "PostgreSQL health check failed"
    assert "database unavailable" in response.json()["detail"]["error"]
