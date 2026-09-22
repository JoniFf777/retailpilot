"""Print sanitized planner/reviewer Harness outcomes from an isolated schema."""

from __future__ import annotations

import argparse
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, select

from app.core.settings import get_settings
from app.db.models import AgentRun


def _scoped_url(base: str, schema: str) -> str:
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema},public"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    args = parser.parse_args()
    engine = create_engine(_scoped_url(get_settings().database_url, args.schema))
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(
                    AgentRun.status,
                    AgentRun.error_json,
                    AgentRun.metadata_json,
                ).order_by(AgentRun.created_at)
            ).all()
    finally:
        engine.dispose()
    safe = []
    for status, error, metadata in rows:
        metadata = metadata or {}
        role = "reviewer" if metadata.get("shopping_task_reviewer") else "planner"
        safe.append(
            {
                "role": role,
                "status": status,
                "error_code": (error or {}).get("code"),
            }
        )
    print(safe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
