from app.operations.release_checks import (
    ReleaseOperationCheckStatus,
    ReleaseOperationReason,
)


def test_release_contract_contains_closed_ai_platform_states():
    assert ReleaseOperationCheckStatus.NOT_APPLICABLE.value == "not_applicable"
    assert ReleaseOperationReason.AI_PLATFORM_DEGRADED.value == "ai_platform_degraded"
