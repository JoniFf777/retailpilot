"""Shared helpers for deterministic evaluation artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_artifact(payload: dict[str, Any], output_path: Path) -> None:
    """Atomically replace a JSON artifact after complete serialization."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


__all__ = ["write_json_artifact"]
