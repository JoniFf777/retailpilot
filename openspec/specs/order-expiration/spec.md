# order-expiration Specification

## Purpose

This capability gives pending-payment Orders a fixed, payment-safe expiration lifecycle so abandoned reservations are released exactly once without corrupting payment or Outbox state.

## Requirements

### Requirement: Pending-payment Orders SHALL have a fixed expiration deadline and terminal state

Every newly created `pending_payment` Order SHALL persist a UTC, timezone-aware `expires_at` deadline at creation time. The deadline SHALL remain stable across idempotent request replay. After expiration migration/backfill, the database SHALL reject `pending_payment` and `expired` rows with null `expires_at`; `paid` and `cancelled` rows MAY retain null. The Order state machine SHALL allow `pending_payment` to transition to exactly one of `paid`, `cancelled`, or `expired`; `paid` and `cancelled` SHALL never transition to `expired`.

#### Scenario: New Order gets a fixed expiration deadline

- **WHEN** a valid Checkout Preview is used to create a new Order
- **THEN** the returned and persisted Order SHALL have a non-null UTC `expires_at` derived from the configured payment TTL at creation time

#### Scenario: Idempotent create replay preserves the deadline

- **WHEN** the same owner replays a successful Order creation with the same idempotency key and request hash
- **THEN** the system SHALL return the original Order and original `expires_at` without extending the deadline or creating another reservation

#### Scenario: Existing pending Orders receive deterministic migration semantics

- **WHEN** the expiration migration encounters an existing `pending_payment` Order without `expires_at`
- **THEN** it SHALL assign a deterministic deadline using the documented compatibility default, while existing `paid` and `cancelled` Orders SHALL remain terminal and unaffected

#### Scenario: Database requires deadlines for pending and expired Orders

- **WHEN** a database write attempts to persist `pending_payment` or `expired` with a null `expires_at` after the migration/backfill
- **THEN** the database SHALL reject the write, while a `paid` or `cancelled` row with a null `expires_at` SHALL remain valid

### Requirement: Eligible unpaid Orders SHALL expire and release active reservations exactly once

When a `pending_payment` Order has reached its persisted deadline and has no active, uncertain, or inconsistent PaymentAttempt, the system SHALL transition it to `expired`, release every matching active reservation, decrement the corresponding inventory reserved quantities, and preserve all non-negative inventory constraints. The transition SHALL be idempotent.

#### Scenario: Eligible unpaid Order expires

- **WHEN** a `pending_payment` Order deadline is reached and it has no PaymentAttempt or only terminal failed attempts
- **THEN** the Order SHALL become `expired`, each active reservation SHALL become `released`, and each inventory `reserved_quantity` SHALL decrease by the reserved quantity

#### Scenario: Multiple OrderItems release all reservations

- **WHEN** an eligible Order contains multiple OrderItems and active reservations for multiple SKUs
- **THEN** expiration SHALL release every matching reservation and decrement every matching inventory row exactly once

#### Scenario: Repeated expiration is a no-op

- **WHEN** a sweeper encounters an Order that is already `expired`
- **THEN** it SHALL not change the Order version again, SHALL not release a reservation again, SHALL not decrement inventory again, and SHALL not create another expiration transition

### Requirement: Expiration SHALL be safe with PaymentAttempt states

Expiration eligibility SHALL distinguish PaymentAttempt statuses. `processing`, `unknown`, and `provider_succeeded` SHALL defer expiration and retain the reservation; `failed` attempts SHALL not by themselves prevent expiration; a `succeeded` attempt while the Order remains `pending_payment` SHALL be treated as an inconsistent state that fails closed without release or automatic repair. A genuinely new payment claim SHALL be allowed only when `now < expires_at`; an existing same-key replay/recovery/finalization path SHALL be resolved before that new-claim guard and MAY continue after the deadline. Provider finalization SHALL not be overtaken by expiration.

#### Scenario: Processing payment defers expiration

- **WHEN** a deadline is reached while an Order has an active `processing` PaymentAttempt
- **THEN** the Order SHALL remain `pending_payment`, the reservation SHALL remain active, and expiration SHALL be recorded as deferred rather than releasing inventory

#### Scenario: Unknown payment outcome defers expiration

- **WHEN** a deadline is reached while an Order has an `unknown` PaymentAttempt
- **THEN** the Order SHALL remain `pending_payment` with its reservation intact because provider outcome is uncertain

#### Scenario: Provider-succeeded payment cannot be expired underneath finalization

- **WHEN** a deadline is reached while an Order has a `provider_succeeded` PaymentAttempt awaiting local finalization
- **THEN** expiration SHALL defer, and existing finalization SHALL be able to transition the Order to `paid` and consume the reservation

#### Scenario: New payment at or after deadline is rejected before provider I/O

- **WHEN** a client starts payment at or after `expires_at` with a genuinely new idempotency key and the Order has no active PaymentAttempt
- **THEN** the API SHALL return a typed `order_expired`/equivalent non-success, SHALL create no valid new processing attempt, SHALL not call the Provider, and SHALL not reserve inventory

#### Scenario: Payment claimed before the deadline remains protected

- **WHEN** a genuinely new payment claim creates `processing` while `now < expires_at` and the Provider operation remains unresolved when the deadline is reached
- **THEN** expiration SHALL defer, retain the active reservation, and SHALL not overtake that payment operation

#### Scenario: Existing same-key payment replay remains available after the deadline

- **WHEN** a client retries an existing payment idempotency key after `expires_at` and the existing attempt requires replay, recovery, or finalization
- **THEN** the system SHALL resolve the existing attempt according to the payment contract before applying the genuinely-new-claim deadline guard, without creating a second attempt or incorrectly rejecting the existing lifecycle solely because the deadline passed

#### Scenario: Succeeded attempt with pending Order fails closed

- **WHEN** a deadline-reached `pending_payment` Order has a `succeeded` PaymentAttempt but has not transitioned to `paid`
- **THEN** expiration SHALL report a bounded inconsistent-state outcome, SHALL not release inventory, SHALL not mark the Order `paid`, and SHALL not automatically repair the Order or PaymentAttempt

#### Scenario: Paid or cancelled Orders never expire

- **WHEN** a sweep encounters an Order with status `paid` or `cancelled`, regardless of deadline or PaymentAttempt history
- **THEN** it SHALL perform no expiration or reservation mutation

### Requirement: Cancel and expiration SHALL have one concurrency-safe reservation lifecycle

Explicit cancellation and automatic expiration SHALL share the same payment-safety gate and reservation release invariants while retaining distinct terminal statuses and events. For a `pending_payment` Order, the payment gate SHALL inspect the complete PaymentAttempt history before any reservation or inventory mutation: none or failed-only permits release, active/uncertain states block or defer, and `succeeded` is an inconsistent fail-closed state. The shared reservation-release helper SHALL enforce only reservation/inventory invariants and SHALL not hide or decide PaymentAttempt eligibility. Order ownership locks and stable reservation/inventory ordering SHALL ensure that only one terminal transition can release a reservation.

#### Scenario: Explicit cancel races with expiration

- **WHEN** cancellation and expiration concurrently target the same eligible `pending_payment` Order
- **THEN** exactly one transition SHALL win the Order lock, the final status SHALL be either `cancelled` or `expired`, and inventory SHALL be released at most once

#### Scenario: Succeeded payment inconsistency blocks cancellation

- **WHEN** a `pending_payment` Order has a `succeeded` PaymentAttempt and the user requests cancellation
- **THEN** the system SHALL fail closed with a bounded machine-readable inconsistent-payment outcome, SHALL leave the Order `pending_payment`, SHALL retain all active reservations, SHALL leave inventory unchanged, SHALL emit no `order.cancelled` event, and SHALL NOT automatically repair the PaymentAttempt or Order state

#### Scenario: Payment finalization serializes with cancel and expiration

- **WHEN** Payment finalization, explicit cancellation, and expiration concurrently target the same Order
- **THEN** all paths SHALL serialize through the Order lock; if finalization wins and sets the Order `paid` after consuming the reservation, later Cancel/Expiry SHALL observe `paid` and perform no release, while if Cancel/Expiry wins they SHALL pass the complete payment-safety gate before any release, so no normal race path SHALL release a reservation after a successful payment state

#### Scenario: Two expiry workers target the same Order

- **WHEN** two expiry workers sweep the same deadline-reached Order concurrently
- **THEN** only one worker SHALL perform the transition and reservation release; the other SHALL skip, observe the terminal state, or otherwise complete without a second decrement

### Requirement: Expiration facts and `order.expired` Outbox event SHALL commit atomically

The Order status transition, reservation release, inventory decrement, and versioned `order.expired` Outbox enqueue SHALL be part of one caller-owned database transaction. The event SHALL contain bounded order/deadline/reason facts and follow existing aggregate sequencing. A crash before commit SHALL roll back all of them; a crash after commit SHALL be recoverable by the existing Outbox publisher without a second business transition.

#### Scenario: Expiration writes Outbox in the same transaction

- **WHEN** an eligible Order is successfully expired
- **THEN** the database transaction SHALL contain the `expired` Order, released reservations, updated inventory, and one `shopmind.order.expired.v1` event before commit

#### Scenario: Transaction failure rolls back expiration facts

- **WHEN** reservation release, inventory update, status transition, or Outbox enqueue fails before commit
- **THEN** the transaction SHALL roll back so the Order, reservations, inventory, and Outbox event do not present a partially expired state

#### Scenario: Worker crash after commit is idempotently recoverable

- **WHEN** a worker crashes after the expiration transaction commits but before the Outbox event is published or marked published
- **THEN** the Order SHALL remain `expired`, the reservation SHALL remain `released`, the event SHALL remain available to the Outbox delivery lifecycle, and a later sweep SHALL not create another expiration event

### Requirement: Expiration sweeping SHALL be bounded and independently runnable

Expiration SHALL be available through a standalone, optional CLI/worker boundary rather than a FastAPI in-process background loop. Each sweep SHALL use a bounded batch, stable `(expires_at, id)` ordering, database locking suitable for concurrent workers, and transaction isolation that prevents one malformed Order from permanently blocking later eligible Orders. Within one sweep invocation, each distinct selected Order SHALL be attempted at most once; the sweep SHALL advance past an Order after an expired, deferred, inconsistent, or failed outcome, while a later invocation MAY retry it.

#### Scenario: No eligible Orders is a safe no-op

- **WHEN** a sweep finds no `pending_payment` Order whose deadline has passed
- **THEN** it SHALL perform no business mutation and SHALL complete successfully

#### Scenario: One bad Order does not block future sweeps

- **WHEN** one eligible Order has inconsistent reservation data and another eligible Order is valid
- **THEN** the inconsistent Order SHALL roll back with a bounded error while the worker remains able to process the valid Order in the same or a subsequent bounded sweep

#### Scenario: Deferred Order does not monopolize one sweep

- **WHEN** an eligible Order is deferred because it has `processing`, `unknown`, or `provider_succeeded` payment state and later Orders are also eligible
- **THEN** the sweep SHALL advance beyond the deferred Order and SHALL attempt later Orders within the same bounded invocation, without selecting the deferred Order again in that invocation

#### Scenario: Failed Order does not monopolize one sweep

- **WHEN** an eligible Order fails due to malformed or inconsistent data and later Orders are also eligible
- **THEN** its transaction SHALL roll back, the failure SHALL be counted with bounded diagnostics, and the sweep SHALL attempt later Orders without selecting the failed Order again in that invocation

#### Scenario: Each Order is attempted at most once per sweep

- **WHEN** a bounded sweep processes a set of deadline-reached Orders
- **THEN** each distinct Order SHALL appear in the invocation's attempted set at most once, regardless of whether its outcome is expired, deferred, inconsistent, or failed; a future sweep MAY retry non-terminal outcomes

#### Scenario: Sweep summary is bounded and machine-readable

- **WHEN** a sweep invocation completes
- **THEN** it SHALL return or emit bounded counts for attempted, expired, deferred-payment, inconsistent, and failed outcomes without PII, item details, or unbounded exception text

### Requirement: Expired Order API and payment behavior SHALL be truthful

Order read/list responses SHALL expose `status=expired` and the persisted `expires_at`. Payment creation for an expired Order SHALL be rejected with a typed domain error and SHALL not invoke a Provider. Repeated cancellation of an expired Order SHALL not release inventory again and SHALL use the existing typed non-cancellable/idempotent boundary.

#### Scenario: Order API exposes expiration state

- **WHEN** a user reads an expired Order they own
- **THEN** the API SHALL return `status=expired`, its persisted `expires_at`, and the unchanged Order item/price snapshots

#### Scenario: Expired Order cannot start payment

- **WHEN** a client posts a new payment request for an expired Order
- **THEN** the API SHALL return typed non-success, SHALL not create a valid PaymentAttempt, SHALL not call the Provider, and SHALL not re-reserve inventory

#### Scenario: Repeated cancel of expired Order is safe

- **WHEN** a client attempts to cancel an already expired Order
- **THEN** the API SHALL return the existing typed non-cancellable or terminal-state response and SHALL not change inventory or reservation state

### Requirement: Checkout Preview SHALL remain non-reserving

Checkout Preview SHALL continue to be read-only with respect to Order, Reservation, and Inventory. Only successful Order creation SHALL create active reservations, and expiration SHALL operate only on persisted Orders.

#### Scenario: Checkout Preview does not reserve inventory

- **WHEN** a user requests or retries Checkout Preview before creating an Order
- **THEN** inventory `reserved_quantity` and Reservation rows SHALL remain unchanged
