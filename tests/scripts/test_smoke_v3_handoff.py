import os

from scripts.smoke_postgres import SmokeReport
from scripts.smoke_v3_handoff import (
    build_v3_handoff_smoke_summary,
    format_v3_handoff_smoke_summary,
    run_v3_handoff_smoke_suite,
)


def make_postgres_report() -> SmokeReport:
    return SmokeReport(
        database_url="postgresql+psycopg://postgres:***@127.0.0.1:5432/app",
        database_name="app",
        database_user="postgres",
        alembic_version="0003_candidate_contexts",
        table_counts={
            "customers": 50,
            "products": 25,
            "orders": 250,
            "order_items": 439,
        },
        document_counts={"policy": 39, "product": 298},
        product_search_count=2,
        product_document_count=1,
        policy_document_count=1,
    )


def make_api_summary(failures=None) -> dict:
    active_failures = failures or []
    return {
        "passed_cases": 3 if not active_failures else 2,
        "total_cases": 3,
        "pass_rate": 1.0 if not active_failures else 2 / 3,
        "event_summary": {
            "total_outputs": 7,
            "outputs_with_events": 5,
            "output_event_rate": 5 / 7,
            "total_events": 6,
            "group_counts": {"candidate_context": 3, "confirmation": 3},
            "event_counts": {"pending_action_confirmed": 2},
            "group_rates": {},
            "event_rates": {},
        },
        "failures": active_failures,
    }


def test_build_v3_handoff_smoke_summary_passes_when_both_checks_pass() -> None:
    summary = build_v3_handoff_smoke_summary(
        postgres_report=make_postgres_report(),
        api_summary=make_api_summary(),
    )

    output = format_v3_handoff_smoke_summary(summary)

    assert summary["status"] == "pass"
    assert summary["postgres"]["status"] == "pass"
    assert summary["api_handoff"]["status"] == "pass"
    assert "failures: none" in output


def test_build_v3_handoff_smoke_summary_reports_api_failures() -> None:
    summary = build_v3_handoff_smoke_summary(
        postgres_report=make_postgres_report(),
        api_summary=make_api_summary(
            failures=[{"case": "broken", "failures": ["bad status"]}]
        ),
    )

    output = format_v3_handoff_smoke_summary(summary)

    assert summary["status"] == "fail"
    assert summary["api_handoff"]["status"] == "fail"
    assert "broken" in output
    assert "bad status" in output


def test_run_v3_handoff_smoke_suite_skips_api_when_postgres_fails() -> None:
    def failing_postgres_smoke_fn(**kwargs):
        raise RuntimeError("database unavailable")

    def api_smoke_fn():
        raise AssertionError("API smoke should not run")

    summary = run_v3_handoff_smoke_suite(
        postgres_smoke_fn=failing_postgres_smoke_fn,
        api_smoke_fn=api_smoke_fn,
    )

    assert summary["status"] == "fail"
    assert summary["postgres"]["error"] == "database unavailable"
    assert summary["api_handoff"]["total_cases"] == 0


def test_run_v3_handoff_smoke_suite_runs_async_api_smoke() -> None:
    def postgres_smoke_fn(**kwargs):
        assert kwargs["include_tools"] is False
        return make_postgres_report()

    async def api_smoke_fn():
        return make_api_summary()

    summary = run_v3_handoff_smoke_suite(
        postgres_smoke_fn=postgres_smoke_fn,
        api_smoke_fn=api_smoke_fn,
    )

    assert summary["status"] == "pass"
    assert summary["api_handoff"]["passed_cases"] == 3


def test_run_v3_handoff_smoke_suite_reports_api_exception() -> None:
    def postgres_smoke_fn(**kwargs):
        return make_postgres_report()

    def api_smoke_fn():
        raise RuntimeError("api failed")

    summary = run_v3_handoff_smoke_suite(
        postgres_smoke_fn=postgres_smoke_fn,
        api_smoke_fn=api_smoke_fn,
    )

    assert summary["status"] == "fail"
    assert summary["postgres"]["status"] == "pass"
    assert summary["api_handoff"]["error"] == "api failed"


def test_run_v3_handoff_smoke_suite_forces_v3_agent_mode(monkeypatch) -> None:
    monkeypatch.delenv("SHOPMIND_AGENT_MODE", raising=False)
    monkeypatch.delenv("SHOPMIND_SUPERVISOR_ROUTER", raising=False)

    def postgres_smoke_fn(**kwargs):
        return make_postgres_report()

    def api_smoke_fn():
        assert os.environ["SHOPMIND_AGENT_MODE"] == "multi"
        assert os.environ["SHOPMIND_SUPERVISOR_ROUTER"] == "deterministic"
        return make_api_summary()

    summary = run_v3_handoff_smoke_suite(
        postgres_smoke_fn=postgres_smoke_fn,
        api_smoke_fn=api_smoke_fn,
    )

    assert summary["status"] == "pass"
