from pathlib import Path


def test_agent_handoff_links_current_sources_of_truth() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    for path in (
        "docs/project_status.md",
        "docs/project_introduction.md",
        "docs/frontend_implementation_plan.md",
        "PLAN.md",
        "docs/architecture.md",
        "docs/agent_runtime_design.md",
        "docs/development.md",
        ".local/retailpilot-runbook.md",
    ):
        assert path in agents


def test_closure_documentation_matches_current_release_candidate() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    introduction = Path("docs/project_introduction.md").read_text(encoding="utf-8")
    status = Path("docs/project_status.md").read_text(encoding="utf-8")
    development = Path("docs/development.md").read_text(encoding="utf-8")

    for path in (
        "docs/project_introduction.md",
        "docs/project_status.md",
        "docs/frontend_implementation_plan.md",
        "docs/architecture.md",
        "docs/interview_guide.md",
    ):
        assert path in readme
    assert "Phase 1-6B-2 accepted/closed" in status
    assert "Project Closure" in status and "implementation in progress" in status
    assert "Inbox/Consumer deferred" in status
    assert "SKU-level commerce path" in introduction
    assert "SHOPMIND_PYTHON" in development
    assert "D:\\DL\\Anaconda3" not in development
    assert "C:\\Users\\17937" not in development


def test_frontend_plan_matches_public_api_and_security_boundaries() -> None:
    plan = Path("docs/frontend_implementation_plan.md").read_text(encoding="utf-8")
    assert "Phase 1-6B-2 accepted/closed" in plan
    assert "POST /api/chat/stream" in plan
    assert "POST /api/chat/confirm" in plan
    assert "POST /api/owner-data/delete" in plan
    assert "SHOPMIND_IDENTITY_SIGNING_SECRET" in plan
    assert "fetch" in plan and "ReadableStream" in plan


def test_roadmap_covers_agent_runtime_capabilities() -> None:
    roadmap = Path("PLAN.md").read_text(encoding="utf-8")
    for capability in (
        "Agent Harness",
        "Memory And Context Management",
        "Tool Gateway And Policy Sandbox",
        "Async Streaming And Runtime Control",
        "A2A",
        "Evaluation And Production Reference",
    ):
        assert capability in roadmap


def test_machine_local_and_runtime_artifacts_are_ignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    for pattern in (
        ".local/",
        ".env.*",
        "!.env.example",
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        "*.zip",
    ):
        assert pattern in gitignore


def test_current_architecture_and_interview_material_cover_commerce() -> None:
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    interview = Path("docs/interview_guide.md").read_text(encoding="utf-8")
    for term in (
        "Current Commerce Architecture",
        "Checkout, Payment, and Outbox transaction sequence",
        "Commerce state and data relationships",
        "Provider I/O never holds a PostgreSQL transaction",
        "at-least-once rather than exactly-once",
    ):
        assert term in architecture
    for term in (
        "One-minute introduction",
        "Five-minute demo route",
        "Why SKU-level truth?",
        "Why not exactly-once?",
        "Inbox/deduplication",
    ):
        assert term in interview


def test_v6_reference_artifacts_remain_available() -> None:
    for path in (
        "evaluation/catalog/v6_evaluation_catalog.json",
        "evaluation/baselines/v6_slice3_accepted.json",
        "evaluation/baselines/v6_slice4_accepted.json",
        "evaluation/run_resilience_replay_eval.py",
        "evaluation/run_governance_lifecycle_eval.py",
        "scripts/check_production_config.py",
        "scripts/check_deployment_readiness.py",
        "scripts/check_release_operations.py",
        "examples/shopmind_reference_client.py",
        "docs/v6_release_candidate_notes.md",
    ):
        assert Path(path).is_file()
