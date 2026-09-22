"""Audit current trusted ShopMind shopping evidence without changing storage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.ai_platform.audit import audit_legacy_corpus


ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit ShopMind shopping evidence corpus.")
    parser.add_argument("--documents-dir", type=Path, default=ROOT / "data" / "documents")
    parser.add_argument("--overview", type=Path, default=ROOT / "data" / "documents" / "DOCUMENTS_OVERVIEW.md")
    parser.add_argument("--output-json", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = audit_legacy_corpus(args.documents_dir, args.overview)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not report["duplicate_names"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
