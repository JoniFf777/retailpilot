"""Run the task worker against a private demo schema."""

from __future__ import annotations

import argparse
import os
import signal
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from app.core.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.2)
    args = parser.parse_args()
    base = get_settings().database_url
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={args.schema},public"
    os.environ["DATABASE_URL"] = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    os.environ["LANGSMITH_TRACING"] = "false"
    get_settings.cache_clear()
    from app.db.session import SessionLocal
    from app.shopping_tasks.worker import run_worker_once

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    worker_id = uuid4().hex
    while not stop.is_set():
        session = SessionLocal()
        try:
            run_worker_once(session, worker_id=worker_id)
        finally:
            session.close()
        time.sleep(max(0.05, min(args.poll_seconds, 5.0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
