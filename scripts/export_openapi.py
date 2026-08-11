"""Export ShopMind's FastAPI OpenAPI document without starting any services."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="UTF-8 JSON output path")
    args = parser.parse_args()

    from app.main import app

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    components = schema.get("components", {}).get("schemas", {})
    print(f"OpenAPI exported: {output} ({len(components)} schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
