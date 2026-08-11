# RetailPilot / ShopMind Project Introduction

ShopMind is an Agent Engineering reference product for Chinese shopping
decisions. It combines a guarded multi-agent recommendation runtime with a
SKU-level commerce path and real PostgreSQL transaction acceptance.

## Product capability

The read path interprets a need, retrieves Catalog and policy evidence, applies
deterministic constraints and ranking, and returns structured SKU candidates.
Read agents cannot perform writes. A user must explicitly confirm a typed
PendingAction before the selected SKU enters the owner-scoped Cart.

The commerce path continues through Cart versioning, Checkout Preview, signed
snapshot token, idempotent Order creation, Inventory Reservation, Mock Payment,
paid inventory consumption, and a transactional Outbox. The React frontend
exposes this path through generated OpenAPI contracts.

## Runtime engineering

The V4-V6 runtime provides persisted Harness lifecycle, Memory/Context,
streaming control, typed tool policy, bounded specialist execution, replayable
trajectories, optional local/Redis coordination, authenticated owner-data
governance, deterministic evaluation, deployment preflight/readiness, and
bounded service health. These layers preserve the public chat/confirm boundary.

## Transaction engineering

- SKU Inventory is the source of price/availability truth.
- PostgreSQL row locks and conditional updates serialize reservation and
  consumption without oversell.
- Idempotency-Key plus request hash supports exact same-request replay and
  rejects conflicting reuse.
- Payment provider I/O occurs after claim commit and before a separate local
  finalization transaction.
- Durable `provider_succeeded` supports recovery without charging again.
- Order/Payment transitions and versioned Outbox events commit together.
- The worker publishes outside the business transaction using lease/CAS,
  bounded retry, dead-letter, and redrive semantics.

## Verification

Default tests are model-independent. Real PostgreSQL suites exercise migration
constraints, rollback, idempotency, deadlocks, Payment-versus-Cancel races, and
Outbox crash windows. Vitest and mocked Playwright cover browser state; live
Playwright verifies real React, FastAPI, PostgreSQL, Reservation, Inventory,
Payment, and Outbox facts.

## Run the project

Activate a Python environment or set `SHOPMIND_PYTHON`, then follow:

- `README.md` for Quick Start and acceptance commands;
- `docs/demo_runbook.md` for Core Demo Prepare/Start/Verify;
- `docs/architecture.md` for runtime and commerce diagrams;
- `docs/interview_guide.md` for a portfolio walkthrough;
- `docs/development.md` for detailed local verification.

No active onboarding path requires a developer-specific absolute path.

## Boundaries

The Core Demo does not require LangSmith credentials or RocketMQ. RocketMQ is
an optional publisher reliability demo. Real payment/card handling, webhook,
refund, automatic reconciliation/expiration, shipping/tax/fulfillment, Redis
commerce state, consumer, Inbox, and consumer deduplication are not implemented.
