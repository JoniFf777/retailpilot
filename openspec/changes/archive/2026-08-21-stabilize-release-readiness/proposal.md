## Why

The final release audit found four scope-bounded blockers: the frontend production build is not type-safe, runtime readiness still expects the previous Alembic head, a fresh application-role database requires an undocumented privileged pgvector step, and the critical HITL browser fixture does not load the current pending-action contract. Related PostgreSQL integration assertions and active setup documentation have drifted from the current contracts.

## What Changes

- Make the current Alembic head a single runtime/test source of truth and make readiness distinguish current, behind, and unknown/future revisions.
- Extend the existing PostgreSQL bootstrap entry point with an explicit, fail-closed administrator provisioning phase for the `vector` extension while keeping application runtime credentials unprivileged.
- Fix the three real frontend TypeScript errors without weakening strict typing or reintroducing Laptop fallback for unresolved categories.
- Update the critical HITL browser fixture to load the current typed PendingAction view and verify the existing cancel/confirm boundary rather than bypassing it.
- Update affected PostgreSQL integration tests to derive the configured database/revision and use the current typed expected-version confirmation contract.
- Align active README/development/setup documentation with the actual `0015` migration and bootstrap sequence.

## Capabilities

### New Capabilities

- `release-readiness`: Long-term contracts for deterministic database bootstrap, readiness, build, and critical local release verification.

### Modified Capabilities

- None. The eight existing main capabilities remain unchanged; this change hardens release validation and setup around their current contracts.

## Impact

Expected implementation touches `app/db/version.py`, readiness/bootstrap scripts, selected frontend source and tests, selected PostgreSQL integration tests, and active setup documentation. No production commerce, payment, Agent, Cart, Order, RAG, Chat retry, or security contract is intentionally redesigned. The change must be validated against an isolated PostgreSQL database with LangSmith, Redis, RocketMQ, and external APIs disabled.
