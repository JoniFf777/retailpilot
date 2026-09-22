"""Compare the released RRF behavior with the reusable retrieval helper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.recommendation.retrieval_pipeline import rrf_fuse


def _legacy_fuse(*lists: list[dict[str, object]], limit: int) -> list[str]:
    records: dict[str, dict[str, object]] = {}
    scores: dict[str, float] = {}
    for values in lists:
        for rank, document in enumerate(values, start=1):
            key = str(document.get("id"))
            records.setdefault(key, document)
            scores[key] = scores.get(key, 0.0) + 1.0 / (60.0 + rank)
    return [key for key in sorted(records, key=lambda item: (-scores[item], item))[:limit]]


def run_cases() -> dict[str, object]:
    lists = [
        [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        [{"id": "b"}, {"id": "d"}, {"id": "a"}],
    ]
    old = _legacy_fuse(*lists, limit=4)
    new = [item["id"] for item in rrf_fuse(lists, limit=4, rrf_k=60)]
    return {
        "schema_version": "shopmind.retrieval-equivalence.v1",
        "cases": {"fixed_rankings": old == new},
        "legacy_ids": old,
        "new_ids": new,
        "passed": int(old == new),
        "total": 1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare ShopMind retrieval implementations.")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    report = run_cases()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
