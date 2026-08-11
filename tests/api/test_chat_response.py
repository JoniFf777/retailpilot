from app.api.chat_response import PROJECTION_CORRUPTION_CODE, build_chat_response
from app.runtime import RunResult, RunStatus


def _run(recommendation):
    return RunResult(
        run_id="run", runtime_thread_id="thread", trace_id="trace", request_id="request",
        status=RunStatus.COMPLETED, answer="ok", output_data={"recommendation": recommendation},
    )


def test_response_builder_projects_valid_recommendation() -> None:
    recommendation = {
        "outcome": "no_match", "ranking_policy_version": "v1", "request_summary": "x",
        "structured_constraints": {}, "no_match_reason": "none",
    }
    response = build_chat_response(_run(recommendation), user_id="u", thread_id="t", include_debug=False)
    assert response.recommendation is not None
    assert response.recommendation_context.source_run_id == "run"
    assert response.projection_error is None


def test_response_builder_reports_corrupt_persisted_recommendation_without_rewriting_run(caplog) -> None:
    caplog.set_level("WARNING", logger="shopmind.audit")
    response = build_chat_response(_run({"outcome": "recommended"}), user_id="u", thread_id="t", include_debug=False)
    assert response.status == RunStatus.COMPLETED
    assert response.recommendation is None
    assert response.projection_error is not None
    assert response.projection_error.code == PROJECTION_CORRUPTION_CODE
    record = next(record for record in caplog.records if record.message == PROJECTION_CORRUPTION_CODE)
    assert record.event == "recommendation_projection_corrupt"
    assert record.run_id == "run"
    assert record.trace_id == "trace"
    assert "outcome" not in record.getMessage()
    assert "recommended" not in record.getMessage()
