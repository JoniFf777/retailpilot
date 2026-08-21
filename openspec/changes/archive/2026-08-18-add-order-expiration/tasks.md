## 1. Baseline and state-machine audit

- [x] 1.1 Record the Apply-before worktree status/diff and confirm the exact Order, Reservation, PaymentAttempt, Outbox, worker, migration, API, frontend, and test files that this Change may touch.
- [x] 1.2 Add a machine-readable implementation matrix for Order statuses, PaymentAttempt statuses (`processing`, `unknown`, `provider_succeeded`, `failed`, `succeeded`), exact deadline eligibility, terminal transition, reservation action, provider-call permission, and fail-closed inconsistent-state handling.

## 2. Model, configuration, and migration

- [x] 2.1 Add bounded `SHOPMIND_ORDER_PAYMENT_TTL_SECONDS` Settings/config support with a documented 1,800-second default and UTC/timezone-aware semantics.
- [x] 2.2 Add persisted nullable-compatible `ShopMindOrder.expires_at`, add `expired` to model/public status contracts and Order API error/status types, and preserve idempotent replay behavior.
- [x] 2.3 Add the next Alembic migration to extend the Order status CHECK, add/backfill `expires_at` for existing `pending_payment` rows deterministically, add the post-backfill invariant requiring `expires_at` for `pending_payment` and `expired`, and create the bounded `(status, expires_at, id)` sweep index without destructive cleanup.
- [x] 2.4 Add migration/model/settings tests for new deadlines, terminal statuses, existing pending-row backfill, paid/cancelled preservation, UTC values, and invalid TTL bounds.

## 3. Shared reservation and payment safety

- [x] 3.1 Extract the smallest shared active-reservation release helper from `cancel_order`, preserving Order-first, reservation/item, and stable-SKU inventory locking plus conditional non-negative updates; keep PaymentAttempt eligibility as a caller-owned gate outside the helper.
- [x] 3.2 Route explicit cancellation through the shared helper only after inspecting complete PaymentAttempt history, including `succeeded`; preserve `cancelled` status/event semantics for eligible orders, return a typed bounded inconsistent-payment failure with no release/event for `succeeded` plus `pending_payment`, and prove cancellation remains idempotent.
- [x] 3.3 Add the payment claim deadline guard after existing idempotency-key replay/recovery lookup and Order locking, so only a genuinely new key requires `now < expires_at` before creating `processing` or invoking Provider I/O; preserve same-key replay after the deadline.
- [x] 3.4 Add local tests for the unified payment/terminal-transition matrix: none/failed eligible, processing/unknown/provider_succeeded deferred, succeeded-plus-pending fail-closed for both expiry and cancel, paid/cancelled protected, exact `now == expires_at` rejection, pre-deadline claim protection, same-key post-deadline replay, and provider finalization not overtaken.

## 4. Expiration service and worker

- [x] 4.1 Implement an injectable-clock expiration service whose candidate query uses `pending_payment AND expires_at <= now`, stable `(expires_at, id)` ordering, and a per-invocation seek cursor so each selected Order is attempted at most once.
- [x] 4.2 Implement the unified Cancel/Expiry payment eligibility matrix: none/failed-only allow, processing/unknown/provider_succeeded block or defer, and succeeded-plus-pending fail closed; keep bounded deferred/inconsistent diagnostics without adding a new Order status for deferral.
- [x] 4.3 Implement one-Order/small-batch transaction processing with candidate selection followed by locked eligibility inspection, stable Order → PaymentAttempt → Reservation/OrderItem → Inventory lock ordering, conditional reservation release, and cursor advancement for expired/deferred/inconsistent/failed outcomes.
- [x] 4.4 Add a standalone one-shot sweep/CLI and optional polling worker following the existing Outbox worker boundary; do not attach a loop to FastAPI lifespan.
- [x] 4.5 Prove bounded batch behavior, `FOR UPDATE SKIP LOCKED`/equivalent PostgreSQL coordination, deferred/failed Orders not monopolizing one invocation, each Order attempted at most once per sweep, bounded outcome counts, one bad Order isolation, zero-eligible no-op, and repeated expiry idempotency.

## 5. Outbox, API, and frontend compatibility

- [x] 5.1 Add a versioned `shopmind.order.expired.v1` Outbox contract with bounded, PII-safe payload and aggregate sequence semantics.
- [x] 5.2 Enqueue `order.expired.v1` in the same transaction as Order status, reservation, and inventory changes; add rollback/crash-after-commit coverage at the repository/service boundary.
- [x] 5.3 Update Order/Payment API contracts and routes so expired Orders are readable, payment is rejected before Provider invocation, and repeated cancel is typed/idempotent without a second release.
- [x] 5.4 Regenerate the frontend OpenAPI contract and make the minimum Order/Payment UI changes needed to render expired status and suppress payment/cancel actions; do not redesign Checkout/Order UI.

## 6. Local and API regression tests

- [x] 6.1 Add service/unit tests for deadline persistence, idempotent create replay, eligible expiry, multiple reservations, repeated expiry, transaction rollback, and no negative inventory.
- [x] 6.2 Add API tests for expired Order reads, expired payment rejection/no Provider call, repeated cancel, `pending_payment` plus `succeeded` cancellation rejection with unchanged reservation/inventory and no cancelled Outbox event, and Checkout Preview remaining non-reserving.
- [x] 6.3 Add deterministic local worker tests for cursor advancement, bounded sweep summaries, deferred/failed Orders not blocking later candidates in the same invocation, succeeded-plus-pending fail-closed behavior, and duplicate worker no-op behavior where SQLite can prove state-machine semantics.
- [x] 6.4 Add/adjust frontend mocked tests for expired status rendering, unavailable payment/cancel controls, generated status types, loading/error/retry compatibility, and unchanged pending/paid/cancelled behavior.

## 7. Isolated PostgreSQL verification

- [x] 7.1 Add isolated PostgreSQL migration/acceptance coverage for `expires_at`, the `pending_payment`/`expired` non-null deadline CHECK, expired status/index, existing pending-row backfill, terminal-row preservation, and Outbox schema/event contract.
- [x] 7.2 Add PostgreSQL concurrency tests for payment-vs-expiry, payment-finalization-vs-cancel, payment-finalization-vs-expiry, cancel-vs-expiry, two expiry workers, per-invocation cursor advancement under deferred/failed candidates, multiple reservation release, exact-deadline claim behavior, same-key replay after deadline, and crash/rollback boundaries.
- [x] 7.3 Add PostgreSQL assertions that `paid`/`cancelled` never expire, `provider_succeeded` defers, `succeeded`-plus-pending blocks both expiry and cancel without repair or release, successful finalization consumes at most once, no path releases after success, expired payment never reaches Provider, and exactly one `order.expired` business transition/event is persisted.

## 8. Final verification and scope review

- [x] 8.1 Run the directly related focused backend tests with LangSmith disabled and no Redis/RocketMQ/external API; record zero failures and zero errors.
- [x] 8.2 Run the full non-integration backend suite with a writable isolated basetemp, plus frontend focused/full Vitest, lint, typecheck, and generated-contract checks; record results without running live external E2E.
- [x] 8.3 Review `git diff --check`, status, diff stat, migration safety, lock order, payment matrix, Outbox transaction, and scope compliance; document PostgreSQL verification separately from local results.
