from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.ai_operations import router
from app.ai_platform.admin import AdminAuthorizer
from app.core.settings import Settings


def make_app(enabled: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.runtime_settings = Settings(
        shopmind_ai_platform_enabled=enabled,
        shopmind_ai_operations_enabled=enabled,
    )
    app.state.admin_authorizer = lambda request: True
    return app


def test_ai_operations_are_disabled_by_default():
    response = TestClient(make_app(False)).get("/api/admin/ai/health")
    assert response.status_code == 404


def test_ai_operations_require_admin_authorizer():
    app = make_app(True)
    app.state.admin_authorizer = lambda request: False
    response = TestClient(app).get("/api/admin/ai/health")
    assert response.status_code == 403


def test_default_admin_authorizer_requires_trusted_principal():
    app = make_app(True)
    app.state.admin_authorizer = AdminAuthorizer()
    response = TestClient(app).get("/api/admin/ai/health")
    assert response.status_code == 403
