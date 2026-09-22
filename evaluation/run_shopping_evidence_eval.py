"""Offline business-contract gate for Shopping Evidence retrieval."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ai_platform.guards import catalog_authority
from app.recommendation.retrieval_pipeline import EvidenceGate, SearchRequest, rrf_fuse


def run_cases() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    product_a = {
        "id": "product-a",
        "metadata": {
            "evidence_type": "product_guide",
            "product_ids": ["A"],
            "authority": "evidence_only",
        },
    }
    product_b = {
        "id": "product-b",
        "metadata": {
            "evidence_type": "product_guide",
            "product_ids": ["B"],
            "authority": "evidence_only",
        },
    }
    expired_policy = {
        "id": "old-policy",
        "metadata": {
            "evidence_type": "store_policy",
            "policy_type": "return",
            "authority": "evidence_only",
            "valid_until": (now - timedelta(days=1)).isoformat(),
        },
    }
    cases = {
        "candidate_scope": EvidenceGate().process(
            [product_a, product_b],
            SearchRequest(query="A", evidence_type="product_guide", product_ids=("A",)),
        )
        == [product_a],
        "expired_policy": EvidenceGate().process(
            [expired_policy],
            SearchRequest(
                query="return", evidence_type="store_policy", policy_type="return"
            ),
        )
        == [],
        "catalog_authority": catalog_authority("6299", "5999") == ("6299", True),
        "rrf_deterministic": [
            item["id"] for item in rrf_fuse([[product_a], [product_a]], limit=1)
        ]
        == ["product-a"],
    }
    passed = sum(bool(value) for value in cases.values())
    return {
        "schema_version": "shopmind.shopping-evidence-eval.v1",
        "passed": passed,
        "total": len(cases),
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run offline shopping evidence contract evaluation."
    )
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
