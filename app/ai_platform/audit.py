"""Static audits for the trusted ShopMind shopping-evidence corpus."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.ai_platform.ingestion import load_legacy_sources


def audit_legacy_corpus(documents_dir: Path, overview_path: Path | None = None) -> dict[str, Any]:
    product_paths = sorted((documents_dir / "products").glob("*.md"))
    policy_paths = sorted((documents_dir / "policies").glob("*.md"))
    duplicate_names = [path.name for path in product_paths + policy_paths if path.name.count("/") > 1]
    expected_product = expected_policy = None
    if overview_path and overview_path.exists():
        overview = overview_path.read_text(encoding="utf-8")
        product_match = re.search(r"Product Documents（(\d+) 个文件", overview)
        policy_match = re.search(r"Policy Documents（(\d+) 个文件", overview)
        expected_product = int(product_match.group(1)) if product_match else None
        expected_policy = int(policy_match.group(1)) if policy_match else None
    return {
        "product_count": len(product_paths),
        "policy_count": len(policy_paths),
        "total_count": len(product_paths) + len(policy_paths),
        "expected_product_count": expected_product,
        "expected_policy_count": expected_policy,
        "overview_drift": (
            expected_product is not None
            and expected_policy is not None
            and (expected_product != len(product_paths) or expected_policy != len(policy_paths))
        ),
        "duplicate_names": sorted(set(duplicate_names)),
        "business_types": sorted({descriptor.evidence_type for descriptor, _ in load_legacy_sources(documents_dir)}),
        "bounded": True,
    }


__all__ = ["audit_legacy_corpus"]
