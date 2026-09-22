"""Run sanitized live readiness against a private migrated task schema."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _scoped_url(base: str, schema: str) -> str:
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema},public"
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    if not args.schema.replace("_", "").isalnum():
        raise SystemExit("invalid schema")

    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["SHOPMIND_SHOPPING_TASKS_ENABLED"] = "true"
    os.environ["SHOPMIND_SHOPPING_TASK_MODE"] = "agent"
    os.environ["SHOPMIND_AI_PLATFORM_ENABLED"] = "true"

    from app.core.settings import get_settings

    base = get_settings().database_url
    os.environ["DATABASE_URL"] = _scoped_url(base, args.schema)
    get_settings.cache_clear()

    from app.db.session import SessionLocal
    from app.operations import evaluate_deployment_readiness
    from app.shopping_tasks.worker import run_worker_once

    session = SessionLocal()
    try:
        run_worker_once(session, worker_id="readiness-eval")
    finally:
        session.close()
    report = evaluate_deployment_readiness(
        get_settings(), session_factory=SessionLocal
    ).model_dump(mode="json")
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ready": report["ready"],
                "passed_checks": report["passed_checks"],
                "total_checks": report["total_checks"],
            }
        )
    )
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
