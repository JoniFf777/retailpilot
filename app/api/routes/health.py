from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.orm import Session


router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}


def get_postgres_health_report(session_factory=None) -> dict[str, Any]:
    """Run a read-only PostgreSQL health check."""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    session: Session = session_factory()
    try:
        database_name, database_user = session.execute(
            text("select current_database(), current_user")
        ).one()
        alembic_version = session.execute(
            text("select version_num from alembic_version")
        ).scalar_one()
        return {
            "status": "ok",
            "database": database_name,
            "user": database_user,
            "alembic_version": alembic_version,
        }
    finally:
        session.close()


@router.get("/health/postgres")
async def postgres_health_check() -> dict[str, Any]:
    try:
        return await run_in_threadpool(get_postgres_health_report)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "message": "PostgreSQL health check failed",
                "error": str(exc),
            },
        ) from exc
