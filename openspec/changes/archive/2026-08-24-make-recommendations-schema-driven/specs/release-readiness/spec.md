## MODIFIED Requirements

### Requirement: Production frontend build integrity

The first-party frontend SHALL pass strict TypeScript compilation and generate the production bundle without unsafe casts, disabled checks, category-specific fallback branches, or generated contract assumptions that change recommendation semantics. Recommendation rendering SHALL consume generic declared fields and unresolved categories SHALL remain unresolved rather than becoming Laptop.

#### Scenario: Generic category result compiles and renders
- **WHEN** a registered category result contains valid generic comparison fields
- **THEN** frontend typecheck/build SHALL succeed and the shared recommendation UI SHALL render those fields by metadata iteration

#### Scenario: Typed action errors compile
- **WHEN** the generated public action error union contains a supported typed code
- **THEN** the frontend maps it to a bounded user message and production compilation succeeds

#### Scenario: Unresolved recommendation category is safe
- **WHEN** a recommendation category is null, unknown, unsupported, or malformed
- **THEN** the frontend SHALL show generic/clarification or projection-error UI and shall not substitute Laptop

### Requirement: Active release documentation consistency

Active readiness documentation and checks SHALL identify the trusted CategoryRegistry as the category source of truth, require fail-fast definition validation, and preserve the existing migration, Catalog, frontend build, HITL, Chat retry, and safe-error checks. Historical `v3.1.0` artifacts and tags SHALL not be modified or used as mutable configuration.

#### Scenario: Readiness fails on invalid category definitions
- **WHEN** a registry definition has a duplicate alias, invalid type/operator, or dangling ranking/display reference
- **THEN** readiness SHALL be non-ready with a bounded validation reason before serving recommendation traffic

#### Scenario: Registry validation is part of readiness
- **WHEN** a registry definition has a duplicate alias, invalid type/operator, or dangling ranking/display reference
- **THEN** readiness SHALL be non-ready with a bounded validation reason before serving recommendation traffic

#### Scenario: Released tag remains immutable
- **WHEN** this Change is planned or later implemented
- **THEN** `v3.1.0` SHALL remain at its existing commit and release verification SHALL report tag/status without moving it

#### Scenario: New operator follows active setup documentation
- **WHEN** a new operator follows the documented local setup on an empty isolated database
- **THEN** the operator can identify the prerequisite provisioning phase, migration/seed/validation steps, frontend build/start commands, and optional service boundaries

#### Scenario: Historical material is not treated as current setup
- **WHEN** historical release notes contain older migration facts
- **THEN** active setup/readiness checks do not use those historical values as current runtime expectations
