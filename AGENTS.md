# AGENTS.md

This is the primary handoff guide for coding agents in this repository. The
original TechHub workshop remains in the tree, but the active product is
**ShopMind**, an Agent Engineering reference backend for Chinese shopping
decisions.

## New-Window Read Order

Read these before changing code:

1. `AGENTS.md` - operating rules and commands.
2. `.local/retailpilot-runbook.md` - machine-specific, non-secret state.
3. `docs/project_status.md` - implemented features and known gaps.
4. `docs/project_introduction.md` - complete capability overview.
5. `PLAN.md` - completed backend roadmap and post-V6 direction.
6. `docs/frontend_implementation_plan.md` - active Web frontend plan.
7. `docs/architecture.md` - current backend architecture.
8. `docs/agent_runtime_design.md` - V4-V6 runtime design and contracts.
9. `docs/development.md` - non-secret environment and database guide.
10. `docs/v3_api_handoff_contract.md` - backward-compatible public boundary.

Machine-specific facts belong in `.local/retailpilot-runbook.md`. `.local/` is
ignored by Git. Never copy API keys or private passwords into tracked files.

## Current Baseline

- Published release/tag: `v3.0.0`, release commit `c995896`.
- V4-V6 backend and documentation are merged into `main`; creating a new
  version/tag and deploying remain separate release actions.
- V1 complete: single shopping Agent and confirmed add-to-cart.
- V2 complete: PostgreSQL/pgvector, repositories, migrations, seed/index/smoke.
- V3 complete: multi-agent read graph, guarded write handoff, candidate context,
  API/CI events, and LangSmith evaluation.
- V4 complete on `main`: runtime contracts/persistence, unified
  Harness, memory/context, SSE/runtime control, and Tool Gateway/policy slices.
- V5 is complete on `main` through Slice 36: typed local/HTTP
  Agent adapters, canonical planning, bounded parallel fan-out/fan-in, shared budgets, typed transport
  failures, failed-attempt accounting, disabled-by-default bounded specialist
  replay, deterministic retry attempt lifecycle evaluation, model-independent
  adapter equivalence, default-off remote RAG Registry selection, and an
  executable generic add-to-cart/save-preference HITL lifecycle, exact action
  edit schemas, and PostgreSQL-backed restart/resume/replay trajectories.
- Current branch: `main`. The accumulated V4-V6 implementation was materialized
  as immutable commit `908b918`, clean-checkout validation and release-candidate
  notes were completed at `690b0cb`, and the full project introduction/frontend
  plan was added at `5146329`. Preserve unrelated future changes and do not tag,
  release, or deploy without explicit instruction.
- V6 Slices 1-2 (global Slices 37-38) are complete: a closed, versioned
  evaluation catalog composes deterministic suites across ten required
  dimensions, and normalized persisted trajectories verify local fault and
  fresh-store recovery behavior.
- V6 Slice 3 (global Slice 39) is complete. Typed fingerprint-only
  coordination contracts and a bounded thread-safe local backend now define
  admission leases, fixed-window rate limits, duplicate claims and TTL/LRU
  cache behavior. A server-owned factory selects local by default; explicit
  Redis mode uses versioned same-slot keys and atomic Lua operations with
  sanitized fail-closed connection behavior. SSE admission uses renewable,
  token-specific leases. Real Redis verification covers two clients, concurrent
  atomic admission, server TTL expiry, rate limits, deduplication and cache.
- V6 is complete. Slice 4 includes authenticated owner-data inventory/memory
  inspection, exact-owner
  correction and hard deletion, explicitly confirmed full deletion, and
  PII-safe deletion request/result facts. The identity, closed audit,
  fingerprint-only PostgreSQL persistence, retention and default-off emission
  substages are also implemented. The production-facing, server-selected
  `signed_header` adapter now adds short-lived HMAC assertions and local/Redis
  one-time replay claims behind `IdentityBoundary` without changing the
  development default. Audit emission now has a thread-safe PII-free process
  monitor, configurable consecutive-failure alert/recovery logging, and an
  additive operational health snapshot. Its deterministic governance lifecycle
  gate is explicitly accepted as the eighth closed catalog suite. Immediate
  Slice 5 static production preflight is now implemented with six sanitized
  checks, fail-closed explicit production startup, health output and a CI
  artifact. The second substage adds five closed live readiness checks for
  PostgreSQL, migration head, selected coordination and recent committed
  cleanup evidence, with health/CLI/CI output. The third substage adds bounded
  PII-free per-replica service metrics and rolling success-rate/p95 SLO
  contracts at an always-200 internal health endpoint. The fourth substage adds
  offline, versioned deployment/rollback/incident checks and a seven-case CI
  gate over the existing health/readiness/coordination/audit/SLO boundaries.
  The fifth substage adds a bounded public-API reference client and exact-owner,
  payload-free run/trace inspection. Slice 5 functional scope is complete;
  immutable implementation commit `908b918` passes the full, integration,
  smoke, migration, production-preflight and evaluation matrix from a fresh
  detached worktree with clean Git status before and after. All V6
  implementation exit criteria are satisfied. Version/tag, release, and
  deployment remain separate explicitly authorized actions. The
  production/default specialist path remains in-process.
- The repository includes the React/TypeScript Web frontend under
  `D:\python\retailpilot\frontend`. Keep frontend files there and use the
  committed Vite scripts for build, mocked browser tests, and live demo checks.

Current validation: `668 passed, 6 skipped`; PostgreSQL integration `23/23`;
reference-client/API/docs focused `58/58`; runtime coordination focused `12/12`;
combined PostgreSQL/Redis integration `25/25`;
PostgreSQL smoke passed at migration `0007_governance_audit`; V3 API
handoff passed `3/3`; the latest offline resilience gate passed `6/6` cases and
`72/72` checks; coordination equivalence passed `5/5` cases and `18/18` checks;
governance lifecycle passed `5/5` cases and `42/42` checks; V6 catalog
regression passed `8/8` suites, `61/61` cases, `488/488` suite checks, and
`48/48` baseline checks; release operations passed `7/7` cases and `42/42`
checks. Historical V3 validation
remains `227 passed, 4 skipped` with LangSmith evaluator scores `6/6` at `1.0`.
The post-completion project/frontend documentation tests pass `10/10`.

## First Five Minutes

From `D:\python\retailpilot`:

```powershell
git status --short --branch
Get-Content .local\retailpilot-runbook.md
Get-Content docs\frontend_implementation_plan.md -TotalCount 220
docker compose ps postgres
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
```

- Treat pre-existing worktree changes as user-owned. Never restore, overwrite,
  or stage them without explicit instruction.
- Never print `.env`, keys, passwords, or unmasked connection URLs.
- A passing read-only smoke is sufficient. Do not seed or index every session.
- Check port `5432` before starting Compose; another service/container may
  already provide the configured database.

## Python Environment

All Python commands use the existing environment and interpreter:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe <script-or--m-module>
```

Do not run raw `python`, `pytest`, or `uv run`. Do not replace the environment.

```powershell
# Full tests
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest

# Focused tests
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\agents tests\api

# API
.\scripts\start_shopmind.ps1 -Profile development -Action api -Reload

# Read-only smoke
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_v3_handoff.py --json

# Model-independent planner policy gate
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_planner_eval.py --output-json artifacts\v5-planner-policy\summary.json

# Model-independent graph trajectory replay
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_plan_trajectory_eval.py --output-json artifacts\v5-plan-trajectories\summary.json

# Model-independent local/HTTP adapter equivalence
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_adapter_equivalence_eval.py --output-json artifacts\v5-adapter-equivalence\summary.json

# Generic action lifecycle, edit, resume, and replay gate
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_action_lifecycle_eval.py --output-json artifacts\v5-action-lifecycle\summary.json

# V6 deterministic fault and restart replay gate
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_resilience_replay_eval.py --output-json artifacts\v6-resilience-replay\summary.json

# V6 governance lifecycle gate
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_governance_lifecycle_eval.py --output-json artifacts\v6-governance-lifecycle\summary.json

# V6 static production configuration preflight
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_production_config.py --output-json artifacts\v6-production-preflight\summary.json

# V6 live deployment readiness
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_deployment_readiness.py --output-json artifacts\v6-deployment-readiness\summary.json

# V6 closed catalog and accepted-baseline regression gate
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_catalog_eval.py --output-json artifacts\v6-evaluation-catalog\summary.json

# V6 deterministic deployment/rollback/incident gate
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_release_operations_eval.py --output-json artifacts\v6-release-operations\summary.json

# Compact public-API reference client
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py --help
```

## Database Safety

`DATABASE_URL` selects the runtime database; real integration tests use
`TEST_DATABASE_URL`. Settings load `.env` with `override=False`, so explicit
process variables win.

Safe commands:

```powershell
docker compose ps postgres
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\bootstrap_postgres.py --skip-seed --skip-documents
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
```

Bootstrap is plan-only unless `--execute` is given. Seed/index clear data and
require `--execute --confirm-clear`; use them only against an isolated database.
Current migration head: `0007_governance_audit`.

## Runtime Modes

The active V3 baseline is:

```env
SHOPMIND_AGENT_MODE="multi"
SHOPMIND_SUPERVISOR_ROUTER="deterministic"
SHOPMIND_AGENT_PLANNER="deterministic"
SHOPMIND_AGENT_TASK_MAX_ATTEMPTS="1"
SHOPMIND_GOVERNANCE_AUDIT_ENABLED="false"
SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD="3"
SHOPMIND_DEPLOYMENT_PROFILE="development"
```

- `single`: legacy V1 LangChain Agent.
- `multi`: V3 LangGraph Supervisor and specialized read agents.
- `deterministic`: reproducible release baseline.
- `llm`: structured router with deterministic fallback.
- Planner `llm` mode is separately opt-in, lazy, and validated against the
  canonical deterministic plan; empty/write plans do not call its model.
- V4.1 adds internal runtime contracts, conversation/run persistence tables,
  and a thin Harness around current V3 invocations without changing the public
  chat/confirm behavior.
- Specialist retries are server-owned, capped at three, and disabled by default
  with one attempt. Opt-in retries cover typed unavailable/timeout failures only
  and preserve task identity, idempotency, cancellation, and usage accounting.
- `rag_agent` transport defaults to `in_process`. HTTP selection is server-only,
  requires a fixed HTTPS endpoint/allowlist, and never comes from API payloads.

LangSmith is optional for local tests and required only for explicitly
authorized cloud traces or experiments. Do not block unrelated work on
LangSmith configuration.

## LangSmith Policy

- LangSmith is an optional side-channel; normal development, tests, lint,
  integration checks, and offline evaluations keep tracing disabled.
- Use `scripts\start_shopmind.ps1` as the unified startup entrypoint. Ordinary
  commands must explicitly set `LANGSMITH_TRACING=false`.
- Never read, print, commit, or place a real LangSmith Key in tracked files;
  never expose it in logs, metadata, or exceptions.
- Do not create cloud Trace or spend LangSmith quota without explicit user
  authorization. Cloud evaluation must be explicitly initiated with the
  `evaluation` profile.
- LangSmith missing, unavailable, unauthorized, rate-limited, or quota-limited
  must not interrupt the ShopMind business path.

## V3 Safety Contract

- Supervisor: route selection, no tools.
- Product Agent: product search/detail/compare reads only.
- RAG Agent: product/policy retrieval only.
- Preference Agent: preference reads only.
- Decision Agent: structured synthesis, no tools.
- Write handoff: prepares add-to-cart outside read agents.
- `/api/chat/confirm`: confirms or cancels the pending action.
- The same boundary also dispatches registered `save_preference` actions; read
  Agents still cannot write preferences directly.

Read agents cannot call write tools. A product must be explicit or resolved
from a valid same-user, same-thread candidate context. Cart mutation happens
only after confirmation. Preserve ownership, expiry, idempotency, and test-data
cleanup behavior.

## V4+ Vocabulary

- **Harness**: common execution lifecycle around every Agent run.
- **Memory**: persisted information available across runs.
- **Context**: bounded information selected for one model invocation.
- **Sandbox/policy**: capability, argument, resource, budget, and side-effect
  controls around tools. V3 has allowlists and HITL, not an OS sandbox.
- **A2A**: typed Agent-to-Agent task exchange. V3 is in-process LangGraph, not
  remote A2A; use adapters before adding network boundaries.

See `docs/agent_runtime_design.md` for target contracts.

## Code Map

- `agents/shopmind_agent.py` - legacy V1 path.
- `agents/shopmind_multi_agent/` - V3 graph, agents, permissions, events, handoff.
- `app/api/` - FastAPI routes/schemas.
- `app/dependencies/agent.py` - API bridge and confirmation boundary.
- `app/core/settings.py` - runtime settings.
- `app/db/`, `app/repositories/` - SQLAlchemy persistence.
- `tools/` - tools; preserve Agent ownership boundaries.
- `alembic/` - PostgreSQL migrations.
- `evaluation/`, `evaluators/` - local and LangSmith evaluation.
- `scripts/` - setup and smoke commands.
- `workshop_modules/` - inherited material, not the active product path.

## Engineering Rules

- Prefer existing factories, repositories, Pydantic models, and LangGraph state.
- Keep changes scoped; do not refactor workshop code unless it blocks ShopMind.
- Use structured models for Agent and tool contracts.
- Keep default tests model-independent; use PostgreSQL integration and API smoke
  for persistence/user-flow changes.
- Use `rg` first when available, otherwise PowerShell `Select-String`.
- Use `apply_patch` for manual edits.
- Use branch prefix `codex/`.
- Never revert changes you did not make.

## Documentation Ownership

- Current/released behavior: `docs/project_status.md` and API/architecture docs.
- Future scope/order: `PLAN.md`.
- Runtime design: `docs/agent_runtime_design.md`.
- Shared commands: `docs/development.md`.
- Machine-only facts: `.local/retailpilot-runbook.md`.

V2/V3 handoff and release files are historical records, not the live roadmap.
