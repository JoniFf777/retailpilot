"""Remove only explicitly named private shopping-task acceptance schemas."""

from __future__ import annotations

import argparse
import re

from sqlalchemy import create_engine, text

from app.core.settings import get_settings


ALLOWED = re.compile(r"^shopmind_model_accept_[a-z0-9_]+$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", action="append", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-private-test-data", action="store_true")
    args = parser.parse_args()
    names = tuple(dict.fromkeys(args.schema))
    if any(not ALLOWED.fullmatch(name) for name in names):
        raise SystemExit("only shopmind_model_accept_* schemas are allowed")
    if not (args.execute and args.confirm_private_test_data):
        print({"planned": list(names), "executed": False})
        return 0

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    removed: list[str] = []
    try:
        with engine.begin() as connection:
            existing = {
                row[0]
                for row in connection.execute(
                    text(
                        "select schema_name from information_schema.schemata "
                        "where schema_name = any(:names)"
                    ),
                    {"names": list(names)},
                ).all()
            }
            for name in names:
                if name in existing:
                    connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
                    removed.append(name)
    finally:
        engine.dispose()
    print({"removed": removed, "executed": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
