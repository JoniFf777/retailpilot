from fastapi import FastAPI

from app.api.router import api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="RetailPilot Backend API",
        version="0.1.0",
        description="FastAPI backend skeleton for the RetailPilot / ShopMind project.",
    )
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
