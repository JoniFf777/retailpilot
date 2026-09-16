"""Export the runtime FastAPI OpenAPI schema for the generated frontend types."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app


def main() -> int:
    output = Path("frontend/openapi.json")
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
