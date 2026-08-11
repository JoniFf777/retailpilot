# Phase 5A Mock Payment Backend Implementation Report

Status: **Phase 5A Mock Payment Backend implemented, pending independent acceptance.**

Phase 5B is not started.

## Scope

Phase 5A implements the ShopMind Mock Payment Attempt backend only. It does not
modify the frontend and does not implement real providers, webhooks,
refunds/chargebacks, automatic reconciliation, Redis, RocketMQ, Outbox or
Inbox.

## Persistence and state

Migration `0013_shopmind_payments` follows `0012_shopmind_orders` and creates
`shopmind_payment_attempts` with owner/order/request idempotency uniqueness,
provider idempotency uniqueness, active-attempt protection, provider outcome
timestamps and typed status checks. Order status is exactly
`pending_payment`, `cancelled` or `paid`. Reservation status is exactly
`active`, `released` or `consumed`; `consumed_at` is mutually exclusive with
`released_at`.

## Transaction and idempotency semantics

Payment attempt claim is committed before the provider call. The provider call
is outside the database transaction. Provider outcome is committed as
`provider_succeeded`, `failed` or `unknown` before local finalization. Same-key
same-request replay resumes the existing attempt, including local finalization,
without charging again; a same-key different request returns
`idempotency_conflict`.

Successful local finalization locks the Order, PaymentAttempt, Reservations and
Inventory in SKU order, conditionally consumes every SKU, increments each
Inventory version once, marks Reservations consumed, marks the Order paid and
marks the PaymentAttempt succeeded in one transaction. Any SKU or reservation
corruption rolls the whole local finalization back while preserving
`provider_succeeded` for retry. Cancel remains mutually exclusive with an active
payment attempt and with a paid Order.

## API

```text
POST /api/orders/{order_id}/payments
GET  /api/orders/{order_id}/payments
```

POST requires `Idempotency-Key` and accepts only `provider` and opaque
`payment_method_ref`. Amount, currency, identity and provider scenario are
server-owned. Public responses omit request hashes and provider/internal
idempotency identifiers. The OpenAPI contract declares typed 402/404/409/503
domain errors, 202 processing/unknown responses, and truthful 422 validation
responses.

## Validation record

Validation completed without modifying the shared `public` schema:

- Phase 5A unit/API/OpenAPI/HTTP focused tests: `8 passed`.
- Phase 2A/3A/4A API regression plus Phase 5A focused tests: `20 passed`.
- Phase 3 PostgreSQL Cart regression: `6 passed`.
- Phase 4 PostgreSQL Order regression: `11 passed`.
- Phase 5 PostgreSQL matrix: `10 passed`.
- PostgreSQL suites represented by the three private-schema runs: `27 passed`.
- Backend regression group without PostgreSQL/evaluation/operations: `601 passed,
  2 skipped`; one unrelated `tmp_path` setup case remains blocked by the
  machine's existing Windows ACL on `C:\Users\17937\AppData\Local\Temp\pytest-of-17937`.
- `git diff --check`: exit code `0`.

PostgreSQL acceptance uses a random private schema and private
`alembic_version`; the shared `public` schema is not modified.

Final status:

```text
Phase 5A Mock Payment Backend implemented,
pending independent acceptance.

Phase 5B NOT started.
```
