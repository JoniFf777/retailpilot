from pathlib import Path


def test_v3_api_handoff_contract_covers_public_api_flow() -> None:
    contract = Path("docs/v3_api_handoff_contract.md").read_text(encoding="utf-8")

    for required_text in (
        "POST /api/chat",
        "POST /api/chat/confirm",
        "ChatResponse",
        "confirmation_required",
        "completed",
        "cancelled",
        "failed",
        "pending_action_id",
        "include_debug",
        "candidate_context_stored",
        "candidate_context_selected",
        "candidate_context_cleared",
        "pending_action_confirmed",
        "pending_action_cancelled",
        "scripts/smoke_v3_handoff.py",
        "--preserve-runtime-state",
    ):
        assert required_text in contract


def test_readme_links_v3_api_handoff_contract() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "docs/v3_api_handoff_contract.md" in readme
    assert "docs/v3_multi_agent_handoff_summary.md" in readme
