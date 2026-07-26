# Changelog

All notable ShopMind changes are documented in this file.

## [Unreleased]

### Added

- V4 runtime Harness, contracts, persistence, memory/context selection,
  structured events, SSE control, Tool Gateway, and policy enforcement.
- V5 canonical planning, bounded parallel execution, typed local/HTTP Agent
  adapters, shared budgets, deterministic retry trajectories, and generic
  restart-safe editable HITL for add-to-cart and save-preference.
- V6 closed evaluation catalog, resilience replay, local/Redis coordination,
  signed ingress identity, PII-safe governance/owner-data lifecycle,
  production preflight/readiness, service SLOs, rollout/rollback/incident
  checks, and a compact policy-preserving public-API reference client.

### Compatibility

- The released `/api/chat`, `/api/chat/confirm`, and `/api/chat/stream`
  behavior remains V3-compatible.
- Specialist replay and remote RAG transport remain disabled by default.
- Read Agents retain no direct write capability; sensitive actions still
  require the registered confirmation boundary.

### Validation

- Clean detached checkout of implementation commit
  `908b91888795f4d3d35096d6daf0592c840acdc3`.
- Default suite: `668 passed, 6 skipped`.
- PostgreSQL integration: `23/23`; PostgreSQL/Redis integration: `25/25`.
- V3 API handoff: `3/3`; production preflight: `6/6`.
- V6 catalog: `8/8` suites, `61/61` cases, `488/488` checks, `48/48`
  baseline comparisons.
- Release operations: `7/7` cases, `42/42` checks.

Full details: [V6 release-candidate notes](docs/v6_release_candidate_notes.md).

## [3.0.0] - 2026-07-13

### Added

- PostgreSQL and pgvector persistence for structured data, runtime state, and documents.
- LangGraph multi-agent read orchestration with Product, RAG, Preference, and Decision agents.
- Confirmation-based V3 add-to-cart handoff through the existing public chat API.
- Database-backed candidate selection contexts with expiration and bounded cleanup.
- Stable debug events, event metrics, health reports, dashboards, and CI artifacts.
- PostgreSQL, public API handoff, combined smoke, OpenAPI contract, and LangSmith evaluation coverage.

### Changed

- GitHub Actions now use Node.js 24-based official action versions.
- LangSmith dataset and experiment CLIs load project `.env` configuration without overriding explicit process variables.
- The Python package version is now aligned with the ShopMind V3 release.

### Validation

- Full local suite: `227 passed, 4 skipped`.
- PostgreSQL integration tests: `10/10` passed.
- API handoff smoke: `3/3` passed.
- LangSmith handoff experiment: 2 runs, 0 errors, and 6/6 evaluator scores equal to `1.0`.
- Evaluation and smoke runtime rows are cleaned after execution.

Full details: [V3.0.0 release notes](docs/v3_release_notes.md).
