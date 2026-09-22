"""Authorized real-model acceptance for the three shopping task kinds.

The caller supplies a private migrated/seeded schema. This runner never prints
connection values or credentials and keeps LangSmith tracing disabled.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4


def _scoped_url(base: str, schema: str) -> str:
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema},public"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real-model shopping task acceptance.")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument(
        "--reevaluate-json",
        type=Path,
        help="Re-evaluate an existing sanitized real-model report without new provider calls.",
    )
    args = parser.parse_args(argv)
    if not args.schema.replace("_", "").isalnum():
        raise SystemExit("invalid schema")

    if args.reevaluate_json is not None:
        report = json.loads(args.reevaluate_json.read_text(encoding="utf-8"))
        trajectories = report.get("trajectories") or []
        for row in trajectories:
            reasons = row.get("plan_reasons") or []
            provider_plan = any("structured_gateway_plan" in str(reason) for reason in reasons)
            row["provider_plan_succeeded"] = provider_plan
            row["passed"] = row.get("status") in {"succeeded", "waiting_input"} and provider_plan
        reviewer_observed = any(bool(row.get("reviewer_used")) for row in trajectories)
        report["reviewer_observed"] = reviewer_observed
        report["passed"] = (
            len(trajectories) == 3
            and all(bool(row.get("passed")) for row in trajectories)
            and bool(report.get("repair_observed"))
            and reviewer_observed
        )
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "passed": report["passed"],
                    "task_count": len(trajectories),
                    "repair_observed": report.get("repair_observed"),
                    "reviewer_observed": reviewer_observed,
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["passed"] else 1

    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["SHOPMIND_SHOPPING_TASKS_ENABLED"] = "true"
    os.environ["SHOPMIND_SHOPPING_TASK_MODE"] = "agent"

    from app.core.settings import get_settings

    base = get_settings().database_url
    os.environ["DATABASE_URL"] = _scoped_url(base, args.schema)
    get_settings.cache_clear()

    from sqlalchemy import select

    from app.db.models import Customer, Order
    from app.db.session import SessionLocal
    from app.shopping_tasks.contracts import Fact, ShoppingTaskRequest, SourceRef
    from app.shopping_tasks.model_gateway import plan_with_gateway
    from app.shopping_tasks.models import ShoppingTask, ShoppingTaskPlan, ShoppingTaskStep
    from app.shopping_tasks.repository import create_task
    from app.shopping_tasks.worker import run_worker_once
    import app.shopping_tasks.worker as worker_module

    settings = get_settings()
    owner = f"model-acceptance-{uuid4().hex[:12]}"
    session = SessionLocal()
    try:
        customer = Customer(
            customer_id=owner,
            email=f"{owner}@example.com",
            name="Model Acceptance",
            city="Shanghai",
            state="Shanghai",
            segment="Consumer",
        )
        order = Order(
            order_id=f"MODEL-{uuid4().hex[:12]}",
            customer=customer,
            order_date=date.today(),
            status="Delivered",
            total_amount=100,
        )
        session.add_all([customer, order])
        session.commit()

        request_rows = [
            ShoppingTaskRequest(
                kind="bundle_selection",
                goal_text="预算 12000 元，选择笔记本、显示器和扩展坞",
                known_facts=[
                    Fact(
                        key="budget",
                        value=12000,
                        source_ref=SourceRef(
                            source="user_reported",
                            source_id="model-budget",
                            verified=False,
                        ),
                    ),
                    Fact(
                        key="currency",
                        value="CNY",
                        source_ref=SourceRef(
                            source="user_reported",
                            source_id="model-currency",
                            verified=False,
                        ),
                    ),
                ],
            ),
            ShoppingTaskRequest(
                kind="compatibility_diagnosis",
                goal_text="扩展坞连接显示器后没有画面",
                known_facts=[
                    Fact(
                        key="device",
                        value="扩展坞与显示器",
                        source_ref=SourceRef(
                            source="user_reported",
                            source_id="model-device",
                            verified=False,
                        ),
                    ),
                    Fact(
                        key="symptom",
                        value="没有画面",
                        source_ref=SourceRef(
                            source="user_reported",
                            source_id="model-symptom",
                            verified=False,
                        ),
                    ),
                ],
            ),
            ShoppingTaskRequest(
                kind="after_sales_assessment",
                goal_text="分析本人订单的退货条件并准备本地草稿",
                known_facts=[
                    Fact(
                        key="order_id",
                        value=order.order_id,
                        source_ref=SourceRef(
                            source="user_reported",
                            source_id="model-order",
                            verified=False,
                        ),
                    )
                ],
            ),
        ]

        original_retrieve = worker_module.retrieve_task_evidence
        injected = {"done": False}

        def unavailable_once(spec, **kwargs):
            if not injected["done"]:
                from app.shopping_tasks.evidence import TaskEvidenceResult

                injected["done"] = True
                return TaskEvidenceResult(
                    status="unavailable",
                    channel_statuses={"controlled_fault": "unavailable"},
                )
            return original_retrieve(spec, **kwargs)

        worker_module.retrieve_task_evidence = unavailable_once
        task_ids = []
        for index, request in enumerate(request_rows, start=1):
            task = create_task(
                session,
                owner_id=owner,
                request=request,
                idempotency_key=f"real-model-{index}",
                mode="agent",
                plan_builder=lambda goal: plan_with_gateway(
                    goal,
                    settings=settings,
                    owner_id=owner,
                ),
            )
            session.commit()
            task_ids.append(task.id)

        for _ in range(120):
            worked = run_worker_once(session, worker_id="real-model-acceptance")
            session.expire_all()
            states = [session.get(ShoppingTask, task_id).status for task_id in task_ids]
            if all(state in {"succeeded", "waiting_input", "failed"} for state in states):
                break
            if not worked:
                continue
        worker_module.retrieve_task_evidence = original_retrieve

        trajectories = []
        passed = True
        for task_id in task_ids:
            task = session.get(ShoppingTask, task_id)
            plans = list(
                session.scalars(
                    select(ShoppingTaskPlan)
                    .where(ShoppingTaskPlan.task_id == task_id)
                    .order_by(ShoppingTaskPlan.revision)
                ).all()
            )
            verify_steps = list(
                session.scalars(
                    select(ShoppingTaskStep).where(
                        ShoppingTaskStep.task_id == task_id,
                        ShoppingTaskStep.capability == "verify_result",
                    )
                ).all()
            )
            reviewer_used = any(
                isinstance(step.output_json, dict)
                and (step.output_json.get("verification_report") or {}).get("reviewer_used")
                for step in verify_steps
            )
            plan_reasons = [plan.reason for plan in plans]
            structured_plan = any(
                "structured_gateway_plan" in reason for reason in plan_reasons
            )
            outcome = (task.output_json or {}).get("outcome")
            row_passed = task.status in {"succeeded", "waiting_input"} and structured_plan
            passed = passed and row_passed
            trajectories.append(
                {
                    "task_id": str(task.id),
                    "kind": task.kind,
                    "status": task.status,
                    "mode": task.mode,
                    "outcome": outcome,
                    "plan_revisions": len(plans),
                    "plan_reasons": plan_reasons,
                    "reviewer_used": reviewer_used,
                    "provider_plan_succeeded": structured_plan,
                    "model_attempts": (task.budget_json or {}).get("model_attempts"),
                    "passed": row_passed,
                }
            )
        bundle = next(item for item in trajectories if item["kind"] == "bundle_selection")
        repair_observed = bundle["plan_revisions"] >= 2
        reviewer_observed = any(item["reviewer_used"] for item in trajectories)
        passed = passed and repair_observed and reviewer_observed
        report = {
            "schema_version": "shopmind.shopping-task-real-model-acceptance.v1",
            "model": settings.workshop_model,
            "passed": passed,
            "repair_observed": repair_observed,
            "reviewer_observed": reviewer_observed,
            "trajectories": trajectories,
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "passed": passed,
                    "task_count": len(trajectories),
                    "repair_observed": repair_observed,
                },
                ensure_ascii=False,
            )
        )
        return 0 if passed else 1
    finally:
        worker_module.retrieve_task_evidence = original_retrieve if "original_retrieve" in locals() else worker_module.retrieve_task_evidence
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
