from fastapi import FastAPI

from app.api.middleware import CorrelationIdMiddleware
from app.core.langsmith_policy import initialize_langsmith_runtime

# Resolve dotenv/profile policy before importing the API graph.  LangChain and
# LangGraph then see the fail-closed SDK environment before runtime objects are
# constructed.
initialize_langsmith_runtime()

from app.api.router import api_router
from app.core.settings import Settings, get_settings
from app.operations import assert_production_preflight


def create_app(*, settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    resolved_settings = settings or get_settings()
    preflight = assert_production_preflight(resolved_settings)
    app = FastAPI(
        title="RetailPilot Backend API",
        version="0.1.0",
        description="FastAPI backend skeleton for the RetailPilot / ShopMind project.",
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.state.production_preflight = preflight
    app.state.runtime_settings = resolved_settings
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
