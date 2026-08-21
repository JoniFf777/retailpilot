## 1. Baseline and investigation

- [x] 1.1 Record pre-change `git status --short` and `git diff --stat`, and copy every planned existing target file to the Apply-before baseline.
- [x] 1.2 Re-run the frontend build and capture the three current TypeScript failures.
- [x] 1.3 Trace readiness, Alembic head, bootstrap, pgvector extension, and current PostgreSQL role behavior.
- [x] 1.4 Trace the failing critical HITL browser test and prove whether the failure is a stale fixture or a production regression.

## 2. Canonical readiness and bootstrap

- [x] 2.1 Update the existing runtime migration-head source to the actual `0015_shopmind_order_expiration` revision.
- [x] 2.2 Ensure readiness and smoke/current-state tests reuse the canonical revision while preserving behind/future fail-closed behavior.
- [x] 2.3 Add explicit bootstrap prerequisite modeling for the `vector` extension without changing historical migrations.
- [x] 2.4 Implement same-target administrator provisioning through the documented bootstrap entry point with bounded fail-closed errors and no credential logging.
- [x] 2.5 Add/adjust bootstrap tests for present extension, missing admin input, mismatched target, and application-role verification.

## 3. Frontend release blockers

- [x] 3.1 Add safe user messages for every current generated action error code, including ambiguous SKU and required-version errors.
- [x] 3.2 Update the Chat retry test request fixture to include the required `include_debug` field.
- [x] 3.3 Handle null/unresolved recommendation categories without defaulting to Laptop.
- [x] 3.4 Update the critical HITL fixture to return a typed PendingAction view and assert visible cancel/confirm controls and current payload semantics.

## 4. PostgreSQL integration and active docs

- [x] 4.1 Replace fixed database-name assertions with configured isolated target derivation.
- [x] 4.2 Replace duplicated current migration literals with the canonical revision import while preserving explicit negative/legacy migration tests.
- [x] 4.3 Update affected Cart and PendingAction integration assertions to typed expected-version/replay contracts.
- [x] 4.4 Align README, active development/demo docs, AGENTS handoff, and `.env.example` with current migration/bootstrap/frontend/optional-service behavior.

## 5. Verification and lifecycle

- [x] 5.1 Run focused readiness, bootstrap, frontend, HITL, and affected integration tests with external services disabled.
- [x] 5.2 Bootstrap a brand-new isolated PostgreSQL database through the public flow, repeat seed, validate catalog, and verify schema invariants.
- [x] 5.3 Run the complete PostgreSQL integration suite and classify only optional Redis skips as skips.
- [x] 5.4 Run the full non-integration backend suite with a writable isolated basetemp.
- [x] 5.5 Run frontend Vitest, lint, typecheck, typecheck:e2e, production build, and all local Playwright tests.
- [x] 5.6 Run local backend/frontend readiness and core demo smoke flows without external APIs.
- [x] 5.7 Perform security, scope, and eight-main-spec regression checks; generate `CHANGE_ONLY.diff` from the original baseline.
- [x] 5.8 Run strict change/spec validation, sync `release-readiness`, and verify the new main spec without changing the eight existing main specs.
- [x] 5.9 Archive without duplicate sync and run archived validation.
- [x] 5.10 Produce Release Readiness Audit V2 and both final review ZIPs with truthful results and known limitations.
