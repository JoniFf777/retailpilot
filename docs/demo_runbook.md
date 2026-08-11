# ShopMind Core Demo Runbook (Phase 6B-1 / 6B-2)

Status: Phase 1-6B-2 accepted/closed. Project Closure implementation in
progress. Inbox/Consumer deferred.

This runbook is the copyable new-developer path for the current ShopMind web
demo. It is intentionally narrower than a production deployment: PostgreSQL,
the Backend, the Frontend and the ShopMind Catalog are required. RocketMQ,
LangSmith credentials, an external tracing service and a real Payment provider
are not required.

## 1. Environment

Activate a Python environment so `python` is available, or set
`SHOPMIND_PYTHON` to the desired interpreter:

```powershell
python --version
```

Create a local `.env` from `.env.example` if needed. Set `DATABASE_URL` to an
isolated loopback PostgreSQL database whose name contains `_demo`, `_test` or
`_smoke` (for example `retailpilot_v2_smoke`). The prepare command refuses
non-loopback hosts and production-looking database names. Do not point it at a
shared or production database. Start PostgreSQL/pgvector on port 5432 and
install the frontend lockfile dependencies once:

```powershell
npm --prefix frontend ci
```

## 2. Prepare

```powershell
.\scripts\start_shopmind_demo.ps1 -Prepare
```

Prepare checks PostgreSQL reachability and frontend dependencies, upgrades
Alembic to `0014_shopmind_outbox_events`, and runs the legacy seed plus the
ShopMind catalog seed. Both seeds are idempotent and insert missing records
only. No `--clear`, table deletion or document/vector indexing is performed;
an unsafe database target fails closed before any write.

## 3. Start

```powershell
.\scripts\start_shopmind_demo.ps1 -Start
```

The command starts the Backend on `http://127.0.0.1:8000` and Frontend on
`http://127.0.0.1:5173` with the `offline-demo` profile and prints:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- Health: `http://127.0.0.1:8000/api/health`
- Readiness: `http://127.0.0.1:8000/api/health/readiness`

No RocketMQ publisher is started. Local process logs are written under the
ignored `.local/shopmind-demo/` directory.

`-Start` fails closed when either target port is occupied; it never silently
reuses an unknown process. Stop the old demo or pass a different
`-BackendPort`/`-FrontendPort`. A newly started Backend must prove
`profile=offline-demo` and readiness before Start succeeds. Start rebuilds the
production preview bundle with `VITE_SHOPMIND_DEMO_IDENTITY=true` before
serving it, so stale build state cannot disable the demo identity UI.

For an explicitly trusted local process, daily development may opt into
`.\scripts\start_shopmind_demo.ps1 -Start -ReuseExisting`; this still verifies
the existing Backend readiness and Frontend shell before returning. Clean-room
verification never passes `-ReuseExisting`.

## 4. Verify

```powershell
.\scripts\start_shopmind_demo.ps1 -Verify
```

`smoke_shopmind_demo.py` checks health/readiness, the OpenAPI core contract,
the frontend Vite shell, current migration and active catalog rows. It then
exercises the supplied development user through Recommendation -> explicit SKU ->
PendingAction confirmation -> Cart -> Checkout Preview -> Create Order ->
server-owned Mock Payment. It asserts response shapes and the paid business
state, not only HTTP status codes. A nonzero exit is a failed demo.

## 5. Browser happy path

Open `http://127.0.0.1:5173`, enter a development user id, describe a laptop
need, choose an explicit SKU, confirm the PendingAction, open Cart, review the
Checkout Preview, create the Order and click **Mock Payment**. The live browser
gate uses the real Frontend, Backend and PostgreSQL:

```powershell
npm --prefix frontend run test:e2e:live
```

It deliberately contains no `page.route`, `route.fulfill` or browser mock API.
The normal `npm --prefix frontend run e2e` suite remains mocked and does not
require a running Backend/PostgreSQL.

## 6. Advanced Reliability Demo (optional)

Transactional Outbox rows are created in PostgreSQL even when the core demo is
offline. RocketMQ is an optional advanced demo only: install the pinned SDK
with `scripts/bootstrap_rocketmq_sdk.ps1`, start a disposable RocketMQ
NameServer/Broker/Proxy, configure the publisher environment, then run
`scripts/run_outbox_publisher.py`. Inspect or redrive rows with
`scripts/redrive_outbox.py`. This path is separate from core `Prepare`/`Start`
and is never an API startup dependency.

For a bounded read-only operational snapshot, run:

```powershell
python scripts\inspect_outbox.py --json
```

The inspection output contains counts, bounded recent failure/dead-letter
facts and safe timestamps only; it never prints Outbox payloads, identities,
provider keys or request hashes. The optional Outbox status is also exposed by
`GET /api/health/outbox` and is included in readiness without changing core
Backend/PostgreSQL readiness. Health uses capped counters and does not load
recent Outbox rows. A disabled publisher is reported as `disabled`, not
unhealthy; an unavailable optional snapshot is reported separately. RocketMQ
network availability is not checked by readiness.

## Clean-room snapshot verification

The release gate uses a clean-room worktree snapshot verification: copy the
current project files to a temporary directory outside the repository without
`.git`, `.env`, `node_modules`, `dist`, caches or test-result directories, then
inject the isolated demo `DATABASE_URL` through the process environment, and
run only this document's environment setup, `Prepare`, `Start`, `Verify` and
live E2E commands. It must not reuse the original repository's `.env`, virtualenv,
Node dependencies, absolute project paths or temporary artifacts. Remove the
temporary snapshot and its logs afterward. This is not a claim that a fresh
clone has been verified; a true fresh-clone check belongs to a later release
candidate gate.
