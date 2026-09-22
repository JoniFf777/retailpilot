"""Prepare a private PostgreSQL schema for the task-workbench demo.

This is intentionally additive: it creates a schema and applies migrations;
it never drops schemas, truncates tables, or prints a connection URL.
"""

from __future__ import annotations

import argparse
import re

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,62}", args.schema):
        raise SystemExit("schema must be a lowercase PostgreSQL identifier")
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{args.schema}"'))
            connection.execute(text(f'SET search_path TO "{args.schema}", public'))
            connection.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS "{args.schema}".alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'
                )
            )
            connection.commit()
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            tables = set(inspect(connection).get_table_names(schema=args.schema))
            required = {
                "shopmind_shopping_tasks",
                "shopmind_shopping_task_steps",
                "shopmind_shopping_task_actions",
            }
            missing = required - tables
            if missing:
                raise RuntimeError(f"task migration missing tables: {sorted(missing)}")
    finally:
        engine.dispose()
    print(f"prepared private task schema: {args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
