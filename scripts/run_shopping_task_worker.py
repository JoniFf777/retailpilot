"""Run the PostgreSQL shopping task worker.

Examples:
  conda run -n pythonLearn ... scripts/run_shopping_task_worker.py --once
  conda run -n pythonLearn ... scripts/run_shopping_task_worker.py --poll-seconds 1
"""

from __future__ import annotations

import argparse
import signal
import threading
import time
from uuid import uuid4

from app.db.session import SessionLocal
from app.shopping_tasks.worker import run_worker_once


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    worker_id = uuid4().hex
    stop = threading.Event()

    def request_stop(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    while True:
        if stop.is_set():
            return 0
        session = SessionLocal()
        try:
            worked = run_worker_once(session, worker_id=worker_id)
        finally:
            session.close()
        if args.once:
            return 0
        time.sleep(max(0.05, min(args.poll_seconds, 60.0)))


if __name__ == "__main__":
    raise SystemExit(main())
