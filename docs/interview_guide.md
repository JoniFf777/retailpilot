# ShopMind Interview Guide

## One-minute introduction

ShopMind is a full-stack Agent Engineering reference project for shopping
decisions. A multi-agent read path converts a natural-language need into ranked
SKU candidates. Human confirmation gates every Cart write. PostgreSQL then
drives Checkout snapshots, idempotent Orders, inventory reservations, Mock
Payment recovery, and a transactional Outbox. The project is verified with
real database concurrency and a real browser/backend/database demo.

## Five-minute demo route

1. Enter a laptop need and show deterministic structured recommendations.
2. Select an explicit SKU and confirm the PendingAction.
3. Open Cart and create a Checkout Preview; point out that Preview creates no Order.
4. Confirm the Order and show `pending_payment` plus active Reservation.
5. Click Mock Payment and show paid Order, succeeded PaymentAttempt, consumed Reservation, inventory/version deltas, and Outbox facts.
6. Explain that the optional RocketMQ publisher can deliver those committed events without changing the Core Demo.

## Design questions

### Why SKU-level truth?

Inventory, price, and sale status belong to a concrete variant. Product-level
writes would make reservation and price snapshots ambiguous, so recommendation
can discuss Products but every mutation resolves a validated SKU.

### Why PostgreSQL locks instead of Redis?

The invariant spans Order, Reservation, Inventory, Payment, and Outbox rows.
Keeping locks and conditional updates in the system of record gives one atomic
truth boundary. Redis would add coordination but could not replace the database
transaction.

### Why is the provider call outside the transaction?

External latency or timeout must not hold row locks. ShopMind commits a claimed
PaymentAttempt, calls the provider, commits the provider outcome, then opens a
new transaction for local finalization. A durable `provider_succeeded` state
allows finalization recovery without charging again.

### Why a Transactional Outbox?

Direct publish after a business commit can lose an event; publish before commit
can expose a fact that rolls back. Writing the event in the same transaction as
the business fact makes the database-to-broker handoff durable.

### Why not exactly-once?

A worker may crash after the broker accepts a message but before PostgreSQL is
marked published. The lease expires and the stable event ID is republished.
That is intentional at-least-once delivery; a future consumer must deduplicate.

### How are Payment versus Cancel races handled?

Both lock the Order. A committed active PaymentAttempt makes Cancel return
`payment_in_progress`; if Cancel wins first, it releases the Reservation and a
waiting payment returns `order_not_payable` without calling the provider.

### Why does inventory not oversell?

Create locks Inventory in ascending SKU order and uses conditional reserve
updates. Payment conditionally consumes both on-hand and reserved quantities.
Any partial multi-SKU inconsistency rolls back the whole transaction.

### How does response-loss recovery work?

Order and Payment requests carry owner-scoped Idempotency-Keys and request
hashes. Same-key/same-request replay returns the same fact; same-key/different-
request returns a typed conflict. Browser recovery persists the original key
and body for unknown outcomes.

### How does the Outbox crash window recover?

Claims use a short transaction and renewable lease. Publish happens after claim
commit. If completion is lost, lease reclaim makes the same event available;
CAS completion rejects stale owners. Bounded retries end in dead-letter and an
operator can explicitly redrive.

## Hard corrections made during implementation

- Restored public Cart ordering while giving Checkout its own stable SKU lock order.
- Made Order snapshots non-null and migration/API contracts match runtime behavior.
- Separated known `503` failures from unknown-response recovery in the browser.
- Made Mock Provider state process-scoped and Payment success monotonic.
- Replaced sequential race tests with real independent PostgreSQL sessions.
- Bounded Outbox crash retry and removed raw exception persistence from logs and database diagnostics.
- Made demo startup fail closed on occupied ports and removed machine-specific executable paths.

## Test strategy

Unit/API tests fix typed contracts and recovery UX. PostgreSQL suites use random
private schemas and real transaction/thread races. Migration tests inspect
constraints and round-trip revisions. Vitest covers UI state machines; mocked
Playwright covers error paths; live Playwright exercises real React, FastAPI,
and PostgreSQL. The Closure gate additionally uses a repository snapshot with
no `.git`, `.env`, node_modules, build output, caches, or local artifacts.

## Current limitations and next step

There is no real payment provider, card collection, refund, webhook, automatic
reconciliation/expiration, fulfillment, shipping/tax, Redis commerce state,
RocketMQ consumer, or Inbox. The next reliability extension would define a
consumer-owned Inbox/deduplication contract after the producer facts and event
schema are independently accepted.
