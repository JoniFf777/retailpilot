"""Prepare the repeatable, local-only ShopMind offline demo database.

This command deliberately has no destructive mode.  It refuses non-loopback or
production-looking PostgreSQL targets before running migrations and the two
idempotent seeders used by the demo.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.settings import get_settings
from app.db.version import MIGRATION_HEAD


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
REQUIRED_DATABASE_MARKERS = ("_demo", "_test", "_smoke")
BLOCKED_DATABASE_NAMES = {"retailpilot", "production", "prod", "postgres"}


class DemoPrepareError(RuntimeError):
    """A fail-closed, user-actionable preparation error."""


def _database_target(database_url: str) -> tuple[str, str]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        raise DemoPrepareError("DATABASE_URL must target PostgreSQL for the offline demo.")
    host = (parsed.hostname or "").lower()
    database = (parsed.path or "").lstrip("/").split("?", 1)[0].lower()
    if host not in LOOPBACK_HOSTS:
        raise DemoPrepareError("Refusing a non-loopback DATABASE_URL; use an isolated local demo database.")
    if not database or database in BLOCKED_DATABASE_NAMES:
        raise DemoPrepareError("Refusing a production-looking database name; use an explicit *_demo, *_test, or *_smoke database.")
    if not any(marker in database for marker in REQUIRED_DATABASE_MARKERS):
        raise DemoPrepareError("Refusing an unmarked database; its name must contain _demo, _test, or _smoke.")
    return host, database


def _upgrade() -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(config, "head")


def prepare() -> dict[str, object]:
    settings = get_settings()
    host, database = _database_target(settings.database_url)

    from app.db.session import SessionLocal
    from scripts.seed_postgres import run_seed as run_legacy_seed
    from scripts.seed_shopmind_catalog import run_seed as run_catalog_seed

    session = SessionLocal()
    try:
        session.execute(text("select 1")).scalar_one()
    except Exception as exc:  # pragma: no cover - depends on local service state
        session.close()
        raise DemoPrepareError("PostgreSQL is not reachable on the configured local demo target.") from exc
    finally:
        try:
            session.close()
        except Exception:
            pass

    _upgrade()
    # Both seeders are intentionally invoked without their destructive options.
    run_legacy_seed(clear=False)
    catalog_report = run_catalog_seed(replace_managed_seed=False, dry_run=False)

    verify_session = SessionLocal()
    try:
        version = verify_session.execute(text("select version_num from alembic_version")).scalar_one()
        if version != MIGRATION_HEAD:
            raise DemoPrepareError(f"Migration ended at {version}; expected {MIGRATION_HEAD}.")
        verify_session.execute(text("select 1")).scalar_one()
    finally:
        verify_session.close()

    return {
        "status": "prepared",
        "database_host": host,
        "database_name": database,
        "migration": version,
        "legacy_seed": "idempotent",
        "catalog_seed": "idempotent",
        "catalog_inserted": catalog_report.inserted,
        "catalog_skipped": catalog_report.skipped,
        "destructive_reset": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the local ShopMind offline demo database.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable summary.")
    args = parser.parse_args()
    try:
        report = prepare()
    except Exception as exc:
        print(f"ShopMind demo preparation failed: {exc}")
        return 1
    print(json.dumps(report, ensure_ascii=False) if args.json else "ShopMind offline demo prepared (idempotent; no reset).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
