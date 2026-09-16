"""Capture live provider retrieval without exposing document bodies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.recommendation.rag import SqlAlchemyRecommendationEvidenceProvider
from evaluation.json_artifacts import write_json_artifact
from evaluation.retrieval_capture import capture_retrieval_cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture ShopMind retrieval facts.")
    parser.add_argument("input", type=Path, help="JSON file containing cases with message and top_k candidates")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--code-version", default="workspace")
    parser.add_argument("--model-version")
    parser.add_argument("--prompt-version")
    parser.add_argument("--config-version")
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise SystemExit("retrieval capture requires a non-empty cases list")
    report = capture_retrieval_cases(
        SqlAlchemyRecommendationEvidenceProvider(),
        cases,
        code_version=args.code_version,
        model_version=args.model_version,
        prompt_version=args.prompt_version,
        config_version=args.config_version,
    )
    write_json_artifact(report, args.output_json)
    print(json.dumps({"schema_version": report["schema_version"], "case_count": report["case_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
