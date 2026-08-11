# Phase 6B Demo Operational Readiness Plan

Status: Phase 1-6B-2 accepted/closed. Project Closure implementation in
progress. Inbox/Consumer deferred.

## Scope and boundary

Phase 6B-1 packages the existing ShopMind Catalog, PendingAction, Cart,
Checkout, Order, Mock Payment and Transactional Outbox facts into a repeatable
demo. Phase 6B-2 adds only bounded correlation, structured operational logs,
read-only Outbox inspection and optional Outbox health reporting. It does not
add Inbox/Consumer, shipping/tax/coupon features, a real Payment provider or
new transaction semantics.

The core startup contract is PostgreSQL + Backend + Frontend + ShopMind
Catalog. `offline-demo` is an explicit profile: deterministic server-owned
multi-agent routing, in-process catalog evidence, development identity,
LangSmith disabled and Outbox publisher disabled. Outbox rows remain available
for inspection; RocketMQ is an optional advanced reliability demonstration.

## Operational flow

1. `scripts/start_shopmind_demo.ps1 -Prepare` validates a loopback, marked demo
   database, checks the frontend lockfile/dependencies, upgrades Alembic and
   runs both idempotent seeders without `--clear`.
2. `-Start` launches only the Backend and Frontend, refuses occupied target
   ports instead of reusing unknown processes, proves Backend
   `profile=offline-demo` readiness, and prints health/readiness URLs. It
   never bootstraps RocketMQ.
3. `-Verify` fails closed unless health/readiness, OpenAPI, migration, catalog,
   frontend shell and the server-owned Order/Mock Payment API sequence pass.
4. `frontend/e2e/live-critical-path.spec.ts` repeats the browser path against
   the real services and verifies PostgreSQL facts through the smoke helper.

## Data safety

Preparation rejects non-loopback PostgreSQL hosts, production-looking database
names and unmarked database names. The legacy and catalog seeds use stable
identity and `merge`/managed-seed behavior; rerunning Prepare does not create
duplicate demo records. There is no implicit reset operation. Any future
destructive reset must require an explicit, separately named demo/test target
and fail closed by default.

## Acceptance evidence to record

The Phase 6B-1 acceptance report must include core Prepare/Start/Verify, live
E2E with no browser route mocks, existing Vitest and mocked Playwright
regression, backend regression, Phase 3/4/5/6 PostgreSQL regression, lint,
typecheck, E2E typecheck, build, bundle budget, Python compileall,
`git diff --check`, and a clean-room worktree snapshot verification. The
clean-room snapshot excludes `.git`, `.env`, `node_modules`, `dist`, caches and
test-results and runs only the documented setup plus Prepare/Start/Verify/live
E2E commands. It is not described as a fresh-clone verification.

## Phase 6B-2 observability boundary

HTTP requests accept or generate a bounded `X-Correlation-ID` and echo it in
the response. Order, Payment and Outbox transition logs use JSON safe fields
and existing opaque IDs; sensitive request values and full payloads are not
logged. Unexpected HTTP Order/Payment exceptions emit only a stable error code,
exception class and generic safe message. `scripts/inspect_outbox.py --json`
is read-only and bounded to ten recent failure/dead-letter records, with
diagnostic key/value fields redacted. `GET /api/health/outbox` is an optional
operational snapshot using capped counters only; it does not load recent rows
or payloads and cannot make core readiness fail. Disabled publishing is
reported as `disabled`.

## Explicit deferred work

Phase 6B-2 is accepted and closed. Inbox/Consumer remains deferred.
Prometheus/Grafana/ELK/OpenTelemetry Collector, external tracing,
RocketMQ SDK/Broker/Proxy/publisher setup and a monitoring dashboard remain
outside this scope; RocketMQ is an Advanced Reliability Demo and is not a
core startup dependency.
