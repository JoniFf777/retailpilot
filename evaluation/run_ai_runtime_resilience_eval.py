"""Deterministic resilience contract gate for the ShopMind AI platform."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.ai_platform.contracts import ModelCandidate, ModelFailureCode, ModelOperation
from app.ai_platform.resilience import (
    AdmissionRejected,
    ModelGateway,
    ModelGatewayError,
    ModelInvocation,
    OperationAdmission,
    SharedAIBudget,
)
from app.runtime.coordination import LocalRuntimeCoordinationBackend


def _candidate(identifier: str, priority: int, attempts: int = 1) -> ModelCandidate:
    return ModelCandidate(
        candidate_id=identifier,
        operation=ModelOperation.PLANNER,
        provider="eval",
        model=identifier,
        priority=priority,
        max_attempts=attempts,
    )


def run_cases() -> dict[str, object]:
    backend = LocalRuntimeCoordinationBackend()
    admission = OperationAdmission(backend, max_concurrency=1)
    lease = admission.acquire("eval", "owner")
    try:
        try:
            admission.acquire("eval", "owner")
        except AdmissionRejected:
            admission_case = True
        else:
            admission_case = False
    finally:
        lease.release()

    gateway = ModelGateway([_candidate("primary", 1), _candidate("backup", 2)])
    fallback = (
        gateway.execute(
            ModelOperation.PLANNER,
            lambda model: (
                (_ for _ in ()).throw(ConnectionError())
                if model.candidate_id == "primary"
                else ModelInvocation("ok")
            ),
        ).value
        == "ok"
    )
    try:
        ModelGateway([_candidate("stream", 1)]).execute(
            ModelOperation.PLANNER,
            lambda _model: (_ for _ in ()).throw(
                ModelGatewayError(ModelFailureCode.TOTAL_TIMEOUT, stream_started=True)
            ),
        )
    except ModelGatewayError as error:
        stream_case = error.stream_started
    else:
        stream_case = False
    budget = SharedAIBudget(max_total_tokens=2)
    budget_gateway = ModelGateway([_candidate("budget", 1)], budget=budget)
    try:
        budget_gateway.execute(
            ModelOperation.PLANNER,
            lambda _model: ModelInvocation(
                value="too-large", prompt_tokens=2, completion_tokens=1
            ),
        )
    except ModelGatewayError as error:
        budget_case = error.code == ModelFailureCode.BUDGET_EXCEEDED
    else:
        budget_case = False
    cancelled = ModelGateway(
        [_candidate("cancelled", 1)], cancellation_check=lambda: True
    )
    try:
        cancelled.execute(
            ModelOperation.PLANNER, lambda _model: ModelInvocation(value="bad")
        )
    except ModelGatewayError as error:
        cancellation_case = error.code == ModelFailureCode.CANCELLED
    else:
        cancellation_case = False
    report = {
        "schema_version": "shopmind.ai-runtime-resilience-eval.v1",
        "cases": {
            "admission_capacity": admission_case,
            "pre_first_token_fallback": fallback,
            "post_stream_failure_is_terminal": stream_case,
            "shared_budget": budget_case,
            "cancellation": cancellation_case,
        },
    }
    report["passed"] = sum(bool(value) for value in report["cases"].values())
    report["total"] = len(report["cases"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run ShopMind AI resilience evaluation."
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
