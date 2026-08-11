# Phase 6A Transactional Outbox + RocketMQ Implementation Report

Status: **Phase 6A Transactional Outbox + RocketMQ accepted and closed.**

Inbox/consumer NOT started.

## Scope delivered

- Added migration `0014_shopmind_outbox_events` after `0013_shopmind_payments`.
- Added the separate `app.outbox` model, immutable versioned envelope contracts,
  enqueue/reclaim/claim/CAS completion/failure/redrive repository, and
  standalone publisher worker.
- Order Create, Cancel, and successful Payment finalization enqueue the exact
  event in the same PostgreSQL transaction as their business facts. Replays do
  not create duplicate events.
- Added lazy `RocketMQPublisher` integration. The RocketMQ SDK is absent from
  API dependencies and is loaded only by the standalone worker.
- Added pinned SDK bootstrap procedure at
  `scripts/bootstrap_rocketmq_sdk.ps1`; source commit is
  `d463e6400e9819f95a944fa086877336d2e6aad8`.
- Added `scripts/redrive_outbox.py` for explicit dead-letter redrive.
- API startup and FastAPI lifespan are not coupled to the publisher worker.
- Expired lease reclaim now honors the configured maximum: rows below the
  bound return to `pending`, while rows at the bound become `dead_letter` with
  a local-safe lease-expiry error. Successful CAS completion and operator
  redrive clear stale `last_error`.

## PostgreSQL acceptance matrix

The tests use a random private schema and private `alembic_version`; the
shared `public` schema is not migrated, downgraded, or cleaned.

- Migration round-trip and full table/constraint/index introspection: passed.
- Create transactional event and rollback safety: passed by business-path
  transaction coverage.
- Cancel commit/replay and one-event behavior: passed.
- Payment success same-transaction event and finalization rollback: passed.
- Immutable envelope and PII-safe payload: passed.
- Same-aggregate sequence ordering and different-aggregate parallel claim:
  passed.
- Two real PostgreSQL workers competing for one event: passed; one active
  claim only.
- Expired lease reclaim and stale owner CAS: passed.
- Publish failure retry with unchanged Order/Reservation facts: passed.
- Maximum attempts to `dead_letter` and operator redrive: passed.
- Publish-success/mark-published crash recovery preserves the same event ID
  and immutable envelope for at-least-once retry: passed with a real
  `OutboxPublisher` and injected fake publisher that records delivery before
  simulating the worker crash.

## Validation record

- Phase 6A unit/worker boundary tests: `3 passed`.
- HTTP/API/OpenAPI plus Phase 4/5 focused and Phase 6 unit tests: `15 passed`.
- Phase 6A PostgreSQL suite: `12 passed`.
- Phase 3 PostgreSQL Cart regression: `6 passed`.
- Phase 4 PostgreSQL Order regression: `11 passed`.
- Phase 5 PostgreSQL Payment regression: `10 passed`.
- Combined Phase 3/4/5/6 PostgreSQL suites: `39 passed`.
- Stable non-PostgreSQL backend regression scope, excluding the existing
  artifact/operations temp-ACL group and cleanup temp-ACL case: `587 passed,
  2 skipped`.
- A broader run reached `731 passed, 2 skipped` before 24 setup/teardown
  `PermissionError` results from the existing Windows temp-ACL boundary;
  no repository code failure was observed.
- Python `compileall`: passed.
- `git diff --check`: exit code `0`.
- Standalone publisher audit: default-disabled execution failed closed with
  the expected message; it has no FastAPI lifespan dependency and does not
  load the RocketMQ SDK while disabled.
- Real disposable RocketMQ 5.3.2 NameServer/Broker/Proxy smoke: passed through
  `127.0.0.1:8081`. The real publisher produced broker message IDs and the
  test-only consumer observed the FIFO tag/group/key/envelope sequence. All
  disposable containers and the network were removed afterward.
- SDK wheel produced: `rocketmq_python_client-5.1.1-py3-none-any.whl`, SHA-256
  `944E9F29ADA41F2A36E530598BF33E04A5EEB14F35D0944B2B1BC5714B314E41`.

## Explicit Phase 6A non-goals

Consumer, Inbox, deduplication consumer, webhook, automatic reconciliation,
Redis, RocketMQ consumer orchestration, Outbox/In-box API endpoints, real
Payment provider integration, and workflow/release actions were outside the
Phase 6A implementation boundary. The ShopMind Frontend, Mock Payment backend
and core browser demo are available in the later Phase 5/6B work.

## Final status

```text
Phase 6A Transactional Outbox + RocketMQ accepted and closed.
The publisher remains an optional Advanced Reliability Demo; it is not a core
API/frontend startup dependency. Inbox/consumer NOT started.

Phase 6B-1 packages the core browser demo on the existing Outbox facts without
changing transaction semantics. Its offline Prepare/Start/Verify flow does not
start RocketMQ or require LangSmith credentials. Phase 6B-2 Minimal
Observability remains NOT started.
```
