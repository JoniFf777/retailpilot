"""Capture typed retrieval facts for later independent quality evaluation."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Iterable

from app.recommendation.rag import RecommendationEvidence
from app.schemas.catalog import CatalogSkuCandidate


def capture_retrieval_cases(
    provider: Any,
    cases: Iterable[dict[str, Any]],
    *,
    code_version: str,
    model_version: str | None = None,
    prompt_version: str | None = None,
    config_version: str | None = None,
) -> dict[str, Any]:
    """Run a provider under a fixed capture contract.

    This function records IDs, ranks, status, budget diagnostics and elapsed
    time only. Document bodies stay in the private provider/database boundary.
    Failed cases are retained with ``execution_ok=false`` instead of being
    silently removed from the denominator.
    """

    captures: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        case_id = str(case.get("case_id") or f"case-{index + 1}")
        started = perf_counter()
        try:
            top_k = [
                CatalogSkuCandidate.model_validate(item)
                for item in case.get("top_k", [])
            ]
            evidence = provider.retrieve(
                message=str(case.get("message") or ""), top_k=top_k
            )
            if not isinstance(evidence, RecommendationEvidence):
                raise TypeError("retrieval provider returned an invalid contract")
            ranked_ids = [
                item.ref
                for values in evidence.product_evidence.values()
                for item in values
                if item.ref
            ] + [item.ref for item in evidence.policy_evidence if item.ref]
            captures.append(
                {
                    "case_id": case_id,
                    "execution_ok": True,
                    "retrieved_ids": list(dict.fromkeys(ranked_ids)),
                    "diagnostics": evidence.diagnostics,
                    "latency_ms": (perf_counter() - started) * 1000,
                }
            )
        except Exception as exc:
            captures.append(
                {
                    "case_id": case_id,
                    "execution_ok": False,
                    "retrieved_ids": [],
                    "diagnostics": {
                        "error_code": "retrieval_capture_failed",
                        "exception_type": type(exc).__name__,
                    },
                    "latency_ms": (perf_counter() - started) * 1000,
                }
            )
    return {
        "schema_version": "shopmind.retrieval-capture.v1",
        "code_version": code_version,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "config_version": config_version,
        "case_count": len(captures),
        "captures": captures,
    }


__all__ = ["capture_retrieval_cases"]
