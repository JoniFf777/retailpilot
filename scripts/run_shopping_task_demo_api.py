"""Run the API against a private task-demo schema without exposing its URL."""

from __future__ import annotations

import argparse
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import uvicorn

from app.core.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--task-mode", choices=("offline", "agent"), default="offline")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    base = get_settings().database_url
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={args.schema},public"
    os.environ["DATABASE_URL"] = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    os.environ["SHOPMIND_DEPLOYMENT_PROFILE"] = "development"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["SHOPMIND_SHOPPING_TASKS_ENABLED"] = "true"
    os.environ["SHOPMIND_SHOPPING_TASK_MODE"] = args.task_mode
    if args.model:
        os.environ["WORKSHOP_MODEL"] = args.model
    get_settings.cache_clear()
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
