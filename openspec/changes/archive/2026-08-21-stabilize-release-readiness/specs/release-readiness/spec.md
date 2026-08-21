## Purpose

This capability defines the deterministic release and local bootstrap boundaries needed to prove that ShopMind's current persisted contracts can be started, built, and exercised without hidden environment steps or stale validation assumptions.

## ADDED Requirements

### Requirement: Canonical migration readiness
The system SHALL use one canonical current Alembic revision for runtime health, readiness, smoke checks, and current-state integration assertions. Readiness SHALL report ready only when the configured database is at that revision; a behind, unknown, or future revision SHALL remain not ready with a bounded machine-readable reason.

#### Scenario: Current database is ready
- **WHEN** the configured database reports the canonical current revision and required connectivity checks pass
- **THEN** `/api/health/postgres` reports the actual revision and `/api/health/readiness` returns ready

#### Scenario: Behind database is blocked
- **WHEN** the database revision is behind the canonical current revision
- **THEN** readiness returns a non-ready migration-outdated result and does not claim the service is ready

#### Scenario: Unknown or future database is fail-closed
- **WHEN** the database reports an unknown or future revision
- **THEN** readiness returns non-ready with a bounded migration failure reason

### Requirement: Deterministic PostgreSQL bootstrap
The public bootstrap flow SHALL provision required PostgreSQL prerequisites, run Alembic exactly through the canonical head using the application connection, seed idempotently, and validate the resulting catalog without requiring an operator to interrupt the flow with hidden SQL.

#### Scenario: Empty isolated database bootstrap
- **WHEN** an operator runs the documented bootstrap flow against an empty isolated database with valid prerequisite credentials
- **THEN** required prerequisites are ensured, migrations reach the canonical head, seed and validation complete, and the process reports success

#### Scenario: Missing prerequisite credentials
- **WHEN** the required pgvector extension is absent and no valid administrator provisioning input is available
- **THEN** bootstrap fails before application migration with a bounded prerequisite error and does not grant application-role superuser access

#### Scenario: Repeat bootstrap is safe
- **WHEN** the documented idempotent preparation is run again against the same isolated database
- **THEN** it does not duplicate managed catalog rows or require a schema reset

### Requirement: Least-privilege extension provisioning
The application runtime SHALL use only its application database role. Any privileged extension provisioning SHALL be an explicit bootstrap/operator step, SHALL target the same database as the application URL, and SHALL NOT expose administrator credentials through logs, APIs, frontend artifacts, or tracked configuration.

#### Scenario: Administrator provisions vector for the application database
- **WHEN** bootstrap receives a valid administrator provisioning connection matching the application database target
- **THEN** it ensures the vector extension and then verifies it through the application connection before continuing

#### Scenario: Mismatched administrator target
- **WHEN** the administrator provisioning connection targets a different database or host than the application target
- **THEN** bootstrap fails closed without modifying the unrelated database

### Requirement: Production frontend build integrity
The first-party frontend SHALL pass strict TypeScript compilation and generate the production bundle without unsafe casts, disabled checks, or category fallbacks that change recommendation semantics.

#### Scenario: Typed action errors compile
- **WHEN** the generated public action error union contains a supported typed code
- **THEN** the frontend maps it to a bounded user message and production compilation succeeds

#### Scenario: Unresolved recommendation category is safe
- **WHEN** a recommendation category is null or unresolved
- **THEN** the frontend uses generic/unresolved rendering or safely omits category-specific controls and does not substitute Laptop

### Requirement: Current HITL browser path
The critical local browser path SHALL use the current PendingAction contract: an add-to-cart intent produces a visible confirmation surface before mutation, and confirm/cancel requests use the existing owner/thread/version boundary.

#### Scenario: Legacy Chat action is visible
- **WHEN** JSON Chat returns a confirmation-required action and its typed PendingAction view can be read
- **THEN** the UI displays confirmation and cancellation controls without writing the Cart

#### Scenario: Cancel preserves the write boundary
- **WHEN** the user cancels the visible pending action
- **THEN** the UI sends the typed cancellation request and no Cart mutation occurs

#### Scenario: Confirm uses expected version
- **WHEN** the user confirms the visible pending action
- **THEN** the UI sends the current expected version and the existing deterministic confirmation service decides whether one canonical mutation is committed

### Requirement: Configuration-derived integration verification
PostgreSQL integration tests SHALL derive database identity and current migration expectations from the configured isolated target and canonical runtime contract. They SHALL use current typed PendingAction/version semantics and SHALL not parse localized presentation text as proof of success.

#### Scenario: Isolated database identity is asserted
- **WHEN** an integration test checks PostgreSQL health
- **THEN** it compares the reported database identity to the configured isolated URL rather than a fixed local database name

#### Scenario: Current PendingAction confirmation is tested
- **WHEN** an integration test confirms or cancels an action
- **THEN** it supplies the current owner/thread/version contract and asserts typed status/mutation outcomes

#### Scenario: Cart tool result is typed
- **WHEN** an integration test exercises a Cart preparation/confirmation tool
- **THEN** it uses machine-readable action and resolution fields rather than matching presentation text

### Requirement: Active release documentation consistency
Active setup documentation and environment examples SHALL describe the actual canonical migration, explicit pgvector prerequisite, application/admin role boundary, frontend build/start commands, seed/validation flow, expiry worker, and optional services without embedding temporary audit database names or credentials.

#### Scenario: New operator follows active setup documentation
- **WHEN** a new operator follows the documented local setup on an empty isolated database
- **THEN** the operator can identify the prerequisite provisioning phase, migration/seed/validation steps, frontend build/start commands, and optional service boundaries

#### Scenario: Historical material is not treated as current setup
- **WHEN** historical release notes contain older migration facts
- **THEN** active setup/readiness checks do not use those historical values as current runtime expectations
