# Development and Local Runtime

This tracked guide is portable and contains no machine-specific interpreter
path or credential. Machine facts belong in ignored `.local/` files.

## Prerequisites

- Python 3.11+ environment with project dependencies
- Node.js and npm
- Docker with PostgreSQL/pgvector from `docker-compose.yml`
- PowerShell for the bundled Windows launch scripts

Activate the Python environment so `python` resolves correctly, or set
`SHOPMIND_PYTHON` to an interpreter. All scripts fail clearly when Python,
Node/npm, or PostgreSQL is unavailable.

## Environment

Copy `.env.example` to ignored `.env` only when local overrides are needed.
Never put real keys in tracked files. `DATABASE_URL` selects runtime storage;
`TEST_DATABASE_URL` is reserved for isolated integration tests. LangSmith is
optional and must remain disabled for normal tests and the Core Demo.

```powershell
$env:LANGSMITH_TRACING = "false"
docker compose up -d postgres
# Set DATABASE_URL to an isolated *_demo, *_test, or *_smoke database.
# For an empty database, set POSTGRES_ADMIN_URL to an operator connection
# for the same database before running the idempotent demo preparation.
python scripts/prepare_shopmind_demo.py --json
```

`POSTGRES_ADMIN_URL` is used only by the bootstrap prerequisite step to ensure
the `vector` extension. It must target the same database as `DATABASE_URL` and
is never used by the application runtime. If `vector` is already installed,
the admin URL is not needed. Bootstrap fails closed with an actionable message
when the prerequisite is missing and no valid operator connection is given.

For the explicit full bootstrap plan (including destructive legacy seed), use
`python scripts/bootstrap_postgres.py --execute --confirm-clear --skip-documents`
only after verifying that `DATABASE_URL` targets an isolated database. The
bootstrap plan includes the ShopMind catalog seed and a document-free smoke
mode when `--skip-documents` is selected.

## Backend

```powershell
./scripts/start_shopmind.ps1 -Profile development -Action api -Reload
./scripts/start_shopmind.ps1 -Profile development -Action tests
python scripts/smoke_postgres.py
```

Destructive seed/reset actions require an explicitly isolated target and their
documented confirmation flags. Ordinary development should use read-only smoke
or idempotent demo preparation.

## Frontend

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
npm --prefix frontend run test
npm --prefix frontend run e2e
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run typecheck:e2e
npm --prefix frontend run build
npm --prefix frontend run check:budget
```

## Core Demo

```powershell
./scripts/start_shopmind_demo.ps1 -Prepare
./scripts/start_shopmind_demo.ps1 -Start
./scripts/start_shopmind_demo.ps1 -Verify
npm --prefix frontend run test:e2e:live
```

Core Demo startup sets deterministic routing, development identity,
`LANGSMITH_TRACING=false`, and `SHOPMIND_OUTBOX_ENABLED=false`. It needs no
LangSmith key or RocketMQ SDK/broker. See `docs/demo_runbook.md`.

## PostgreSQL acceptance

Integration tests create private random schemas and private Alembic version
tables; they must never alter shared `public` state.

```powershell
$env:RUN_POSTGRES_INTEGRATION = "1"
python -m pytest tests/integration/test_phase3a_postgres_cart.py -p no:cacheprovider
python -m pytest tests/integration/test_phase4_postgres_orders.py -p no:cacheprovider
python -m pytest tests/integration/test_phase5_postgres_payments.py -p no:cacheprovider
python -m pytest tests/integration/test_phase6_postgres_outbox.py -p no:cacheprovider
```

## Optional reliability and evaluation tools

```powershell
./scripts/bootstrap_rocketmq_sdk.ps1
python scripts/run_outbox_publisher.py
python scripts/inspect_outbox.py --json
python evaluation/run_catalog_eval.py --output-json artifacts/v6-evaluation-catalog/summary.json
```

The RocketMQ publisher is an optional worker process. Consumer/Inbox remains
deferred. Cloud LangSmith evaluation requires explicit authorization and the
evaluation profile.

## Release checks

The final gate combines backend regression, Catalog migration, Phase 3-6 real
PostgreSQL suites, Vitest, mocked and live Playwright, lint/typechecks/build/
budget, compileall, Core Demo Verify, `git diff --check`, and a clean-room
snapshot with no `.git`, `.env`, dependency/build/cache directories, or local
artifacts.
