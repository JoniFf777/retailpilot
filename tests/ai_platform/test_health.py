from app.ai_platform.contracts import ModelCandidate, ModelHealthSnapshot, ModelOperation
from app.ai_platform.health import aggregate_ai_status


def test_disabled_ai_platform_is_not_required_for_readiness():
    assert aggregate_ai_status(enabled=False).value == "disabled"


def test_open_model_candidates_make_enabled_platform_not_ready():
    snapshot = ModelHealthSnapshot(
        candidate_id="planner",
        operation=ModelOperation.PLANNER,
        state="open",
        consecutive_failures=2,
        total_failures=2,
        total_successes=0,
    )
    assert aggregate_ai_status(enabled=True, model_health=[snapshot]).value == "not_ready"
