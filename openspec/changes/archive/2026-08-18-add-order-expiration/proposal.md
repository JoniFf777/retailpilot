## Why

ShopMind currently reserves inventory when a `pending_payment` Order is created, but only explicit user cancellation releases that reservation. The current production path has no deadline, sweeper, or automatic terminal transition for a user who closes the page and never pays. This can leave `CatalogInventory.reserved_quantity` occupied indefinitely and make a SKU appear out of stock even though no payment was completed.

The risk is visible in the actual code: `app/services/orders.py:157-170` creates a `pending_payment` Order, `:290-315` increments inventory reservations, and `:371-428` releases them only through `cancel_order`. `ShopMindOrder` currently permits only `pending_payment`, `cancelled`, and `paid` (`app/orders/models.py:17-48`).

## What Changes

- Add a persisted, timezone-aware `expires_at` deadline to new pending-payment Orders; the deadline is fixed at creation and is not recomputed during replay or sweeping.
- Add `expired` as a terminal Order status and expose `expires_at`/status through the Order API contract and the minimum required frontend status rendering.
- Add a safe, bounded expiration service/sweep that transitions only eligible `pending_payment` Orders, releases active reservations exactly once, decrements `reserved_quantity` transactionally, and emits a versioned `order.expired` Outbox event in the same transaction.
- Reuse the existing cancellation reservation-release semantics through the smallest shared helper; preserve the distinction between `cancelled` and `expired` events/statuses.
- Make Cancel and Expiry use the same payment-safety gate before any reservation-releasing terminal transition. A `pending_payment` Order with a `succeeded` PaymentAttempt is an inconsistent fail-closed state for both paths; it cannot be cancelled, expired, released, repaired, or marked paid automatically.
- Define and enforce a payment/expiry race contract. Orders with active or uncertain payment attempts (`processing`, `unknown`, `provider_succeeded`) are deferred rather than expired underneath a provider operation; a `succeeded` attempt on a still-`pending_payment` Order is an inconsistent fail-closed state; new payment claims at or after a reached deadline are rejected before Provider I/O only after existing-key replay/recovery handling.
- Provide an independently runnable, optional Order Expiry Worker/one-shot sweep following the existing standalone Outbox Worker model. Each sweep invocation advances past every selected Order, including deferred or failed attempts, so one Order is attempted at most once per invocation and can be retried by a later sweep. Do not add an in-process FastAPI background loop.
- Add a non-destructive migration/backfill strategy for existing `pending_payment` rows using the documented default TTL, while leaving already `paid`/`cancelled` rows terminal and without extending deadlines on idempotent create replay.
- Add a database invariant requiring `expires_at` for `pending_payment` and `expired` rows after the migration/backfill, while allowing terminal `paid`/`cancelled` rows to retain a null deadline.
- Add unit/local API coverage and design isolated PostgreSQL integration coverage for locking, transaction, payment/expiry races, and multi-worker behavior. PostgreSQL integration is not run during Proposal.

## Capabilities

### New Capabilities

- `order-expiration`: Defines persisted Order payment deadlines, safe expiration/reaper semantics, reservation release, payment race policy, Outbox behavior, worker execution, and expired-order API behavior.

### Modified Capabilities

- None. `backend-regression-stability` and `commerce-cart` remain independent and unchanged by this proposal.

## Impact

Expected implementation impact spans the Order model/schema/service/repository, payment claim guard, shared reservation-release helper, Settings, one Alembic migration, Outbox event contracts, a standalone expiration sweep/worker, Order/Payment API response handling, minimum frontend expired-status rendering, and directly related tests.

The project remains a mock-payment/demo commerce system. Real PSPs, webhooks, reconciliation, refunds, chargebacks, fulfillment, shipping, tax, coupons, distributed scheduler infrastructure, RocketMQ Consumer/Inbox, Redis, and metrics backends remain out of scope.

The current worker precedent is `scripts/run_outbox_publisher.py:14-25`, which is standalone, optional, and not owned by FastAPI lifespan. The recommended expiration runtime follows that boundary: an independently runnable bounded sweep that can be invoked by a local process or external scheduler, with database locking coordinating multiple workers.

## Acceptance Criteria

- New Orders persist a fixed UTC `expires_at`; idempotent create replay returns the original deadline without extending it.
- Eligible unpaid Orders transition to `expired`, release active reservations exactly once, and never reduce inventory below zero.
- `paid` and `cancelled` Orders never transition to `expired`.
- `processing`, `unknown`, and `provider_succeeded` payment attempts prevent unsafe expiry; a `succeeded` attempt while the Order is still `pending_payment` is inconsistent and fails closed; recovery/reconciliation remains explicit rather than silently releasing inventory.
- The exact boundary is `now >= expires_at`: new payment claims are rejected at or after the deadline, while an existing same-key replay/recovery/finalization path is not blocked by the new-claim guard.
- Payment/expiry and cancel/expiry races cannot produce payment success after reservation release, double release, or two terminal transitions.
- Any `succeeded` PaymentAttempt on a `pending_payment` Order blocks both Cancel and Expiry before reservation or inventory mutation; no automatic payment/Order repair or `order.cancelled` event is emitted.
- The shared reservation-release helper performs only reservation/inventory invariants; Cancel and Expiry perform their own complete PaymentAttempt safety gate before invoking it.
- Expiration, reservation release, inventory update, and `order.expired` Outbox enqueue commit atomically and roll back together on failure.
- Two workers cannot expire the same Order or release the same reservation twice; each sweep has a bounded batch and attempts each distinct Order at most once, while deferred or failed Orders remain eligible for a future sweep.
- A `pending_payment` or `expired` row cannot persist with a null `expires_at` after migration; malformed/inconsistent payment state is reported with bounded structured diagnostics without automatic repair.
- Expired Orders are visible through the Order API, cannot start a new payment, and retain truthful status/deadline information.
- Checkout Preview remains non-reserving.
- Focused local tests and the full non-integration backend suite are green; isolated PostgreSQL race/migration tests are specified for Implementation and must pass there.
