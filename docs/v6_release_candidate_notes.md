# ShopMind V6 Release-Candidate Notes

Date: 2026-07-26

## Status

ShopMind V4, V5, and V6 implementation scope is complete. The first immutable
implementation candidate is commit
`908b91888795f4d3d35096d6daf0592c840acdc3`.

This commit was checked out into a fresh detached Git worktree. Git status was
empty before validation and remained empty afterward; generated artifacts and
Python caches were ignored. The checkout contained no `.env`. Required
database values were injected into test processes from the protected local
environment without copying or printing the file.

This is a release-candidate validation record, not a published release. The
latest published tag remains `v3.0.0` until release packaging, review, push, and
tagging are explicitly requested.

## Clean Validation Matrix

- Default model-independent suite: `668 passed, 6 skipped`.
- PostgreSQL-only integration: `23 passed, 2 Redis tests skipped`.
- Combined PostgreSQL/Redis integration: `25 passed`.
- PostgreSQL smoke: passed at `0007_governance_audit`.
- V3 API handoff smoke: `3/3`.
- Alembic graph: one linear head, `0007_governance_audit`.
- Reference production preflight: `6/6`, status `ready`.
- V6 evaluation catalog: `8/8` suites, `61/61` cases, `488/488`
  suite checks, and `48/48` accepted-baseline comparisons.
- Release operations: `7/7` cases and `42/42` checks.
- Reference client: all five CLI subcommands loaded from the clean checkout.
- `git diff --check`: passed.

The matrix used deterministic planning,
`SHOPMIND_AGENT_TASK_MAX_ATTEMPTS=1`, no real LLM, and no remote A2A/HTTP
specialist. It did not seed, rebuild the document index, run destructive
bootstrap, or execute an Alembic downgrade.

## Completed Scope

- V4: Harness, runtime contracts and persistence, memory/context, SSE/runtime
  control, Tool Gateway and policy.
- V5: typed Agent adapters, canonical planning, bounded parallel execution,
  budgets, deterministic retry trajectories, remote-RAG policy selection, and
  restart-safe generic editable HITL.
- V6: closed evaluation catalog, deterministic resilience replay, local/Redis
  coordination, signed ingress identity, PII-safe audit and owner-data
  lifecycle, retention/deletion, production preflight/readiness, service
  metrics/SLOs, release-operation checks, and the compact public-API reference
  client with exact-owner run/trace inspection.

## Remaining Release Work

No V6 implementation slice remains. Publishing is an operator/repository
workflow outside the implementation completion criterion:

1. review the release-candidate commits and release notes;
2. push the branch and open/merge a pull request when authorized;
3. choose the next semantic version and create a signed or annotated tag;
4. execute deployment through the trusted platform and operations runbook.

None of those external actions is performed automatically by the validation
process.
