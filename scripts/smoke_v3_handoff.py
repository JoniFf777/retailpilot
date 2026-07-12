"""Run the full local ShopMind V3 handoff smoke suite.

Usage:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe scripts/smoke_v3_handoff.py

Optional:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe scripts/smoke_v3_handoff.py --json
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe scripts/smoke_v3_handoff.py --include-tool-smoke
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
from typing import Any, Callable, Sequence

from evaluation.shopmind_api_handoff_smoke import (
    format_api_handoff_smoke_summary,
    run_with_asgi_app,
)
from scripts.smoke_postgres import SmokeReport, run_smoke


PostgresSmokeFn = Callable[..., SmokeReport]
ApiSmokeFn = Callable[..., Any]


def _status_from_failures(failures: list[dict[str, Any]]) -> str:
    return "pass" if not failures else "fail"


def build_v3_handoff_smoke_summary(
    *,
    postgres_report: SmokeReport | None = None,
    postgres_error: str | None = None,
    api_summary: dict[str, Any] | None = None,
    api_error: str | None = None,
) -> dict[str, Any]:
    """Build a compact aggregate summary for the V3 handoff smoke suite."""
    api_failures = list(api_summary.get("failures") or []) if api_summary else []
    status = (
        "fail"
        if postgres_error or api_error or api_failures
        else "pass"
    )
    postgres_summary: dict[str, Any] = {
        "status": "fail" if postgres_error else "pass",
        "error": postgres_error,
    }
    if postgres_report is not None:
        postgres_summary.update(
            {
                "database_url": postgres_report.database_url,
                "database_name": postgres_report.database_name,
                "database_user": postgres_report.database_user,
                "alembic_version": postgres_report.alembic_version,
                "table_counts": postgres_report.table_counts,
                "document_counts": postgres_report.document_counts,
                "product_search_count": postgres_report.product_search_count,
                "product_document_count": postgres_report.product_document_count,
                "policy_document_count": postgres_report.policy_document_count,
            }
        )

    return {
        "status": status,
        "postgres": postgres_summary,
        "api_handoff": {
            "status": "fail" if api_error or api_failures else "pass",
            "error": api_error,
            "passed_cases": api_summary["passed_cases"] if api_summary else 0,
            "total_cases": api_summary["total_cases"] if api_summary else 0,
            "pass_rate": api_summary["pass_rate"] if api_summary else 0.0,
            "event_summary": api_summary["event_summary"] if api_summary else {},
            "failures": api_failures,
        },
    }


def format_v3_handoff_smoke_summary(summary: dict[str, Any]) -> str:
    """Format a human-readable aggregate V3 handoff smoke summary."""
    postgres = summary["postgres"]
    api_handoff = summary["api_handoff"]
    lines = [
        "ShopMind V3 handoff smoke suite",
        f"status: {summary['status']}",
        (
            "postgres: "
            f"{postgres['status']} "
            f"database={postgres.get('database_name', 'unknown')} "
            f"alembic={postgres.get('alembic_version', 'unknown')}"
        ),
        (
            "api handoff: "
            f"{api_handoff['status']} "
            f"cases={api_handoff['passed_cases']}/{api_handoff['total_cases']}"
        ),
    ]
    if postgres.get("error"):
        lines.append(f"postgres error: {postgres['error']}")
    if api_handoff.get("error"):
        lines.append(f"api handoff error: {api_handoff['error']}")
    if api_handoff["failures"]:
        lines.append("api failures:")
        for failure in api_handoff["failures"]:
            lines.append(f"- {failure['case']}: {failure['failures']}")
    if (
        not postgres.get("error")
        and not api_handoff.get("error")
        and not api_handoff["failures"]
    ):
        lines.append("failures: none")
    return "\n".join(lines)


def run_v3_handoff_smoke_suite(
    *,
    include_tool_smoke: bool = False,
    preserve_agent_mode: bool = False,
    preserve_runtime_state: bool = False,
    quiet: bool = False,
    postgres_smoke_fn: PostgresSmokeFn = run_smoke,
    api_smoke_fn: ApiSmokeFn = run_with_asgi_app,
) -> dict[str, Any]:
    """Run Postgres and API handoff smoke checks as one suite."""
    try:
        if quiet:
            with contextlib.redirect_stdout(io.StringIO()):
                postgres_report = postgres_smoke_fn(include_tools=include_tool_smoke)
        else:
            postgres_report = postgres_smoke_fn(include_tools=include_tool_smoke)
    except Exception as exc:
        return build_v3_handoff_smoke_summary(postgres_error=str(exc))

    try:
        if not preserve_agent_mode:
            os.environ["SHOPMIND_AGENT_MODE"] = "multi"
            os.environ["SHOPMIND_SUPERVISOR_ROUTER"] = "deterministic"
            from app.core.settings import get_settings

            get_settings.cache_clear()
        api_result = api_smoke_fn(
            cleanup_runtime_state=not preserve_runtime_state,
        )
        api_summary = (
            asyncio.run(api_result)
            if hasattr(api_result, "__await__")
            else api_result
        )
    except Exception as exc:
        return build_v3_handoff_smoke_summary(
            postgres_report=postgres_report,
            api_error=str(exc),
        )
    return build_v3_handoff_smoke_summary(
        postgres_report=postgres_report,
        api_summary=api_summary,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run local ShopMind V3 handoff checks: PostgreSQL readiness plus "
            "the in-process FastAPI chat/confirm smoke flow."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the aggregate smoke summary as JSON.",
    )
    parser.add_argument(
        "--include-tool-smoke",
        action="store_true",
        help=(
            "Include LangChain tool checks in the Postgres smoke. This may "
            "load the embedding model and take longer."
        ),
    )
    parser.add_argument(
        "--preserve-agent-mode",
        action="store_true",
        help=(
            "Do not force SHOPMIND_AGENT_MODE=multi and "
            "SHOPMIND_SUPERVISOR_ROUTER=deterministic before API smoke."
        ),
    )
    parser.add_argument(
        "--preserve-runtime-state",
        action="store_true",
        help=(
            "Do not clean smoke-owned cart, pending action, and candidate "
            "context rows before and after API smoke."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_v3_handoff_smoke_suite(
        include_tool_smoke=args.include_tool_smoke,
        preserve_agent_mode=args.preserve_agent_mode,
        preserve_runtime_state=args.preserve_runtime_state,
        quiet=args.json,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        if summary["api_handoff"]["total_cases"]:
            print(format_api_handoff_smoke_summary({
                "passed_cases": summary["api_handoff"]["passed_cases"],
                "total_cases": summary["api_handoff"]["total_cases"],
                "pass_rate": summary["api_handoff"]["pass_rate"],
                "event_summary": summary["api_handoff"]["event_summary"],
                "failures": summary["api_handoff"]["failures"],
            }))
        print(format_v3_handoff_smoke_summary(summary))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
