## Context

The current Alembic chain ends at `0015_shopmind_order_expiration`, but `app/db/version.py` still exposes `0014_shopmind_outbox_events`; readiness and several integration fixtures inherit that drift. The existing bootstrap runner performs migrations and seed/index steps but has no explicit extension-provisioning phase. The frontend errors are narrow: three missing typed error labels, one stale request fixture, and a nullable category passed to a category-specific component. The failing critical browser test returns a legacy Chat confirmation response but does not mock the follow-up typed PendingAction GET, so the UI correctly declines to invent an add-to-cart action.

## Goals / Non-Goals

**Goals:**

- Establish one canonical expected Alembic revision and reuse it in runtime probes, readiness tests, smoke tests, and integration assertions.
- Make fresh local PostgreSQL setup deterministic and user-visible: an operator/admin connection ensures `vector`, then the application connection runs Alembic and idempotent seed/validation.
- Keep admin credentials confined to the bootstrap process; the application role never gains superuser or extension-install privileges.
- Make the existing frontend build and critical HITL browser path pass without changing public business semantics.
- Align only active setup documentation and directly affected tests.

**Non-Goals:**

- No historical migration rewrite, schema redesign, new extension, CORS/auth change, workspace cleanup, real payment, Redis/RocketMQ requirement, new category, or new product behavior.
- No bypass of PendingAction, expected-version checks, canonical Cart, Chat retry, error-boundary, order-expiration, or Agent HITL contracts.
- No modification of the eight existing main capability specs.

## Decisions

### 1. Canonical migration head

Update the existing `app.db.version.MIGRATION_HEAD` to the actual `0015_shopmind_order_expiration`. Runtime readiness and tests continue importing that symbol. Tests that need to exercise behind/future states may insert explicit synthetic revisions, but must not duplicate the current revision literal. Readiness remains fail-closed: current is ready, known behind is `migration_outdated`, and unknown/future is not ready with a bounded reason.

Alternative rejected: mechanically changing every copy of `0014` to `0015` without a canonical import. Historical release notes and migration-history documents remain historical; active setup/readiness docs are updated.

### 2. Privileged pgvector prerequisite

Extend `scripts/bootstrap_postgres.py` with an explicit prerequisite step. It first verifies the configured application database target, then uses `POSTGRES_ADMIN_URL` when the extension is absent to connect to the same database and execute only `CREATE EXTENSION IF NOT EXISTS vector`; it then verifies the extension through the application connection before running Alembic. If the extension is absent and no admin URL is configured, it fails before migration with a bounded actionable message. If an admin URL targets another database, the step fails closed rather than provisioning the wrong target.

The admin URL is process-local bootstrap input only. It is never stored in application settings, emitted in logs, returned by APIs, or bundled into frontend artifacts. Existing `0002_create_documents_pgvector_table.py` remains unchanged: prerequisite ownership belongs to bootstrap/operator provisioning, while migrations own application schema.

Alternative rejected: granting the application role superuser or adding a privilege-swallowing migration hack. Both hide deployment configuration errors and weaken runtime least privilege.

### 3. Frontend build and category safety

Add bounded user messages for all current generated `ActionErrorResponse.code` values. Update the retry test request fixture with the required `include_debug` field. For nullable recommendation category, render `StructuredConstraintsPanel` only when a resolved category is present; unresolved/unknown results continue through the generic outcome/error path and never default to Laptop.

Alternative rejected: `any`, unsafe casts, disabling strict TypeScript, or `category ?? "laptop"`.

### 4. HITL browser fixture

Update the legacy JSON Chat browser fixture to mock the follow-up `GET /api/pending-actions/{id}` with a typed pending action view, and exercise the existing cancel path plus the confirm payload contract where practical. The production `ActionDrawer` and confirmation API remain the authority. The test must prove the drawer is visible before mutation and that confirm/cancel use the existing expected-version boundary; it must not write Cart directly.

### 5. Integration contract alignment

Affected PostgreSQL tests derive the expected database name from the configured isolated URL and import the canonical migration revision. Confirmation tests provide the current owner/thread/expected-version fields and inspect typed response/action state rather than presentation text. Cart tool tests use typed pending-action results. Tests remain isolated and do not alter production semantics.

### 6. Documentation ownership

Update README, active development/demo setup documentation, `.env.example`, and the repository handoff only where they state current migration/bootstrap/frontend behavior. Historical reports retain their historical facts. The public flow is documented as: admin prerequisite provisioning through the bootstrap command, application-role migration, idempotent seed, catalog validation, and optional document indexing.

## Risks / Trade-offs

- **[Risk] Admin URL is unavailable in a deployment.** → Fail before migration with a clear prerequisite error; do not grant app-role privilege or continue partially.
- **[Risk] Admin URL points at the wrong database.** → Compare normalized host/database target to the application URL and refuse mismatch.
- **[Risk] Existing tests intentionally use synthetic old revisions.** → Keep those fixtures explicit for negative tests and use the canonical symbol for current-state tests.
- **[Risk] Legacy browser test masks a production regression.** → Require the current typed PendingAction GET and assert visible HITL controls before any transition; do not make the UI infer a write action from text alone.
- **[Risk] Documentation changes accidentally rewrite history.** → Limit edits to active setup instructions and leave historical reports untouched.

## Migration Plan

No database migration is added or changed. Run the bootstrap prerequisite against a new isolated database, then Alembic head, seed, repeat seed, validator, smoke, and integration tests. Rollback is source-level: revert the scoped code/docs/test changes; no destructive database rollback is required.
