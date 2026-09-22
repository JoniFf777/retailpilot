"""Print bounded task state for a private demo schema."""

from __future__ import annotations

import argparse
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, text

from app.core.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    args = parser.parse_args()
    base = get_settings().database_url
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={args.schema},public"
    engine = create_engine(
        urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    )
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select id, owner_id, status, version from shopmind_shopping_tasks order by created_at desc limit 20"
            )
        )
        for row in rows:
            print("|".join(str(value) for value in row))
        steps = connection.execute(
            text(
                "select task_id, step_key, status, attempt_count, error_code from shopmind_shopping_task_steps order by task_id, step_key"
            )
        )
        for row in steps:
            print("STEP|" + "|".join(str(value) for value in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
