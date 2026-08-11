# ShopMind Transactional Outbox and RocketMQ Design

Status: Phase 6A and Phase 6B-2 accepted/closed. RocketMQ remains an optional
Advanced Reliability Demo; the Core Demo does not require its SDK or broker.
Inbox/Consumer is deferred.

## Phase 6A boundary

Phase 6A implements a PostgreSQL transactional Outbox and a standalone
RocketMQ FIFO publisher. It does not implement a consumer, Inbox, webhook,
automatic reconciliation worker, Redis, RocketMQ business orchestration, or
any frontend work. Delivery is at-least-once; a future consumer must dedupe by
the immutable `event_id`.

The Apache Python SDK is not an API dependency. The worker-only adapter imports
`rocketmq` lazily during publisher startup. The pinned source is commit
`d463e6400e9819f95a944fa086877336d2e6aad8`, producing
`rocketmq-python-client==5.1.1`. `scripts/bootstrap_rocketmq_sdk.ps1` builds the
wheel with pinned grpc/protobuf/OpenTelemetry dependencies and records its
SHA-256. Development defaults keep the publisher disabled.

## Outbox facts

`shopmind_outbox_events` is a separate model/table with the following immutable
event facts and mutable delivery fields:

- `id` UUID primary key;
- `aggregate_type`, `aggregate_id`, and `aggregate_sequence`;
- `event_type`, `event_version`, JSONB `payload`, and `occurred_at`;
- `status`, `attempt_count`, `redrive_count`, `available_at`;
- nullable lease owner/expiry, sanitized `last_error`, and broker message ID;
- `created_at`, `updated_at`, and nullable `published_at`.

The table enforces positive sequence/version and non-negative counters,
aggregate sequence uniqueness, lease/status invariants, and the published
timestamp invariant. The supported event types are exactly:

- `shopmind.order.created.v1`;
- `shopmind.order.cancelled.v1`;
- `shopmind.payment.succeeded.v1`.

Every event has `aggregate_type=order`, `aggregate_id=order_id`, and uses the
Order `version` after the business transition. Create, Cancel, and successful
Payment finalization enqueue their event in the same PostgreSQL transaction as
the business facts. Replays do not enqueue a second event. Provider outcome
events are intentionally not emitted.

## Claim and delivery lifecycle

The worker first reclaims expired `publishing` leases in a short transaction.
It then claims eligible `pending` rows with `FOR UPDATE SKIP LOCKED`, a fresh
lease owner, a database-time lease expiry, and an incremented attempt count.
A lower sequence for the same aggregate blocks later events until it is
`published`; rows are selected by `created_at, id`.

The claim transaction commits before the broker call. RocketMQ receives an
immutable envelope with:

- topic `shopmind-order-events-v1`;
- FIFO `message_group=str(order_id)`;
- tag equal to `event_type`;
- message key equal to `event_id`;
- compact JSON envelope body.

Success uses a compare-and-set update on event ID, `publishing` status, and
lease owner, storing the broker message ID and database `published_at` while
clearing `last_error`. A stale worker cannot overwrite a newer lease. An
expired lease is reclaimed to `pending` while `attempt_count < max_attempts`,
or directly to `dead_letter` at the bound; it clears the lease and records
only the local-safe text `delivery lease expired before completion`, because
the broker may already have accepted the message. Publish failure clears the
lease and uses deterministic exponential backoff: 5 seconds, capped at 15
minutes; attempt 12 becomes `dead_letter`.

The operator command `scripts/redrive_outbox.py EVENT_ID` only transitions a
`dead_letter` row to `pending`, resets `attempt_count`, increments
`redrive_count`, clears delivery fields and `last_error`, and makes it
immediately available. Successful CAS completion also clears `last_error`.
It rejects `publishing` and `published` rows.

## Business transaction map

```text
Order create
  reserve inventory + consume exact Cart + create Order
  + order.created event                 -- one PostgreSQL transaction

Order cancel
  release active Reservations + update Order version
  + order.cancelled event               -- one PostgreSQL transaction

Payment success
  consume Reservations + decrement Inventory + increment versions
  + mark PaymentAttempt succeeded + Order paid
  + payment.succeeded event             -- one PostgreSQL transaction

Publisher
  claim/lease commit -> RocketMQ call -> CAS mark-published commit
```

No API request or FastAPI lifespan owns the worker loop. The standalone
publisher is enabled explicitly with `SHOPMIND_OUTBOX_ENABLED=true` and fails
closed when its endpoint, topic, credentials, or worker SDK is unavailable;
API startup remains unaffected.
