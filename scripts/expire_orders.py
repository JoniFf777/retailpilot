"""Run one bounded ShopMind pending-Order expiration sweep."""

from __future__ import annotations

import argparse
import json

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.services.order_expiration import (
    DEFAULT_EXPIRATION_BATCH_SIZE,
    expire_orders_once,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_EXPIRATION_BATCH_SIZE,
        help="Maximum number of distinct Orders to attempt (default: 10).",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    args = parser.parse_args()
    summary = expire_orders_once(
        SessionLocal,
        get_settings(),
        batch_size=args.batch_size,
    )
    if args.json:
        print(json.dumps(summary.as_dict(), sort_keys=True))
    else:
        print(summary.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
