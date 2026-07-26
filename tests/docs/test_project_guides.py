from pathlib import Path


def test_agent_handoff_links_current_sources_of_truth() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")

    for path in (
        "docs/project_status.md",
        "PLAN.md",
        "docs/architecture.md",
        "docs/agent_runtime_design.md",
        "docs/development.md",
        ".local/retailpilot-runbook.md",
    ):
        assert path in agents


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


def test_machine_local_runbook_is_ignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert ".local/" in gitignore


def test_slices_37_40_catalog_replay_and_v6_handoff_are_consistent() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    roadmap = Path("PLAN.md").read_text(encoding="utf-8")
    status = Path("docs/project_status.md").read_text(encoding="utf-8")
    design = Path("docs/agent_runtime_design.md").read_text(encoding="utf-8")
    development = Path("docs/development.md").read_text(encoding="utf-8")

    assert "Slice 36" in agents
    assert "thirty-second V5 slice" in roadmap
    assert "thirty-third V5 slice" in roadmap
    assert "thirty-fourth V5 slice" in roadmap
    assert "thirty-fifth V5 slice" in roadmap
    assert "thirty-sixth V5 slice" in roadmap
    assert "first four V6 slices" in roadmap
    assert "V6 Slice 3" in roadmap
    assert "IdentityBoundary" in roadmap
    assert "shopmind.governance-audit.v1" in roadmap
    assert "V4-V6 Implementation Complete" in status
    assert "shopmind.evaluation-catalog.v1" in status
    assert "shopmind.evaluation-catalog.v1" in design
    assert "shopmind.evaluation-baseline.v1" in design
    assert "evaluation\\run_catalog_eval.py" in development
    assert Path("evaluation/catalog/v6_evaluation_catalog.json").is_file()
    assert Path("evaluation/baselines/v6_slice3_accepted.json").is_file()
    assert Path("evaluation/baselines/v6_slice4_accepted.json").is_file()
    assert Path("evaluation/run_resilience_replay_eval.py").is_file()
    assert "shopmind.runtime-trajectory.v1" in design
    assert "shopmind.resilience-replay-eval.v1" in design
    assert "evaluation\\run_resilience_replay_eval.py" in development
    assert "shopmind.governance-lifecycle-eval.v1" in roadmap
    assert "evaluation\\run_governance_lifecycle_eval.py" in development
    assert Path("evaluation/run_governance_lifecycle_eval.py").is_file()
    assert "shopmind.production-preflight.v1" in roadmap
    assert "scripts\\check_production_config.py" in development
    assert Path("scripts/check_production_config.py").is_file()
    assert "shopmind.deployment-readiness.v1" in roadmap
    assert "shopmind.runtime-cleanup-evidence.v1" in design
    assert "scripts\\check_deployment_readiness.py" in development
    assert Path("scripts/check_deployment_readiness.py").is_file()
    assert "SHOPMIND_DEPLOYMENT_PROFILE" in development
    assert "/api/health/preflight" in development
    assert "/api/health/readiness" in development
    assert "shopmind.service-metrics.v1" in roadmap
    assert "shopmind.service-slo.v1" in design
    assert "/api/health/service-metrics" in development
    assert Path("app/runtime/service_monitoring.py").is_file()
    assert Path("tests/runtime/test_service_monitoring.py").is_file()
    assert "shopmind.release-operation-input.v1" in roadmap
    assert "shopmind.release-operation-check.v1" in design
    assert "scripts\\check_release_operations.py" in development
    assert "evaluation\\run_release_operations_eval.py" in development
    assert Path("scripts/check_release_operations.py").is_file()
    assert Path("evaluation/run_release_operations_eval.py").is_file()
    assert Path("docs/operations_runbook.md").is_file()
    assert "compact public-API reference client" in status
    assert "| V6 | Complete |" in roadmap
    assert "908b91888795f4d3d35096d6daf0592c840acdc3" in roadmap
    assert "All V6 implementation exit criteria are satisfied" in status
    assert Path("docs/v6_release_candidate_notes.md").is_file()
    assert "examples\\shopmind_reference_client.py" in development
    assert "/api/owner-data/runs/inspect" in development
    assert "shopmind.owner-run-inspection.v1" in design
    assert Path("examples/shopmind_reference_client.py").is_file()
    assert Path("tests/scripts/test_shopmind_reference_client.py").is_file()
    assert "RuntimeCoordinationBackend" in design
    assert "LocalRuntimeCoordinationBackend" in design
    assert "tests\\runtime\\test_coordination.py" in development
    assert "SHOPMIND_COORDINATION_BACKEND" in development
    assert "SHOPMIND_IDENTITY_PROVIDER" in development
    assert "X-ShopMind-Authenticated-User" in design
    assert "signed_header" in roadmap
    assert "X-ShopMind-Identity-Signature" in design
    assert "SHOPMIND_IDENTITY_SIGNING_SECRET" in development
    assert "remote IdP/JWKS" in design
    assert "shopmind.governance-audit-monitor.v1" in roadmap
    assert "GovernanceAuditEmissionMonitor" in design
    assert "SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD" in development
    assert "/api/health/governance-audit" in development
    assert "monitor.alert_active=true" in development
    assert "GovernanceAuditFactory" in design
    assert "shopmind.governance-audit.v1" in design
    assert "OwnerDataService" in design
    assert "/api/owner-data/delete" in development
    assert "deletion_request_id" in development
    assert "owner-data lifecycle" in roadmap
    assert "StreamAdmissionController" in design
    assert "shopmind.plan-trajectory-eval.v2" in design
    assert "13/13" in design and "195/195" in design
    assert "HTTP Adapter And Registry Selection (Implemented)" in design
    assert "plan.step.attempt.*" in development
    assert "SHOPMIND_RAG_AGENT_TRANSPORT" in development
    assert "tests\\security" in development
    assert "editable, resumable add-to-cart/save-preference HITL" in development
    assert "shopmind.action-lifecycle-eval.v2" in design
