# ShopMind V2 Infra Upgrade Handoff

This document summarizes the current V2 infrastructure upgrade state and the
files that should be reviewed before staging or opening a PR.

For a PR-ready summary, staging scope, and rollback notes, see
`docs/v2_infra_upgrade_pr_notes.md`.

## Current Database Path

Local `.env` points to an isolated PostgreSQL smoke database:

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/retailpilot_v2_smoke?connect_timeout=5
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/retailpilot_v2_smoke_test?connect_timeout=5
```

The default Docker Compose service also binds `5432:5432`. If the host already
runs PostgreSQL on port 5432, prefer using an isolated database on the existing
server instead of starting the compose service.

## V2 Files To Include

Infrastructure and configuration:

- `.env.example`
- `.gitignore`
- `docker-compose.yml`
- `pyproject.toml`
- `app/core/`

Database and migrations:

- `app/db/`
- `alembic.ini`
- `alembic/`

Repositories:

- `app/repositories/`

Scripts:

- `scripts/seed_postgres.py`
- `scripts/index_documents_pgvector.py`
- `scripts/smoke_postgres.py`
- `scripts/bootstrap_postgres.py`

Tool/API changes:

- `tools/products.py`
- `tools/preferences.py`
- `tools/cart.py`
- `tools/documents.py`
- `app/api/routes/health.py`

Tests:

- `tests/config/`
- `tests/db/`
- `tests/repositories/`
- `tests/scripts/`
- `tests/tools/test_documents.py`
- `tests/integration/`
- Modified tests under `tests/tools/`, `tests/api/`, and `tests/agents/`

Docs:

- `README.md`
- `docs/architecture.md`
- `docs/v2_infra_upgrade_handoff.md`

## Files To Review Before Staging

Do not stage these without an explicit decision:

- `data/structured/techhub.db`
  - Current audit: `techhub.db-journal` is not present, the file is not
    read-only, and the core V1 table counts still match the fixture data:
    customers `50`, products `25`, orders `250`, order_items `439`.
  - Runtime state tables are empty: user_preferences `0`, cart_items `0`,
    pending_actions `0`.
  - The file is still a binary diff with the same byte size, so keep it out of
    the V2 infra staging set unless the team explicitly wants to update the V1
    SQLite fixture. Restore it only after an explicit decision.
- `AGENTS.md`
  - Local Codex/agent instruction file, not necessarily project source.
- `workshop_modules/*_zh_CN.*`
  - Large translated workshop artifacts; review separately from the V2 infra
    upgrade.

## Verification Commands

Default test suite, no real PostgreSQL required:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests/config tests/db tests/repositories tests/scripts tests/tools tests/api tests/agents tests/evaluation tests/integration
```

Read-only PostgreSQL smoke check:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
```

Real PostgreSQL integration tests:

```bash
set RUN_POSTGRES_INTEGRATION=1
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests/integration
```

Safe bootstrap plan only:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\bootstrap_postgres.py
```

Bootstrap against an isolated development database:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\bootstrap_postgres.py --execute --confirm-clear --skip-documents
```

## Latest Known Results

- Default regression: `90 passed, 4 skipped, 1 warning`
- PostgreSQL integration: `10 passed`
- Smoke database Alembic version: `0002_documents_pgvector`
- Seed counts: customers `50`, products `25`, orders `250`, order_items `439`
- Documents counts: product `298`, policy `39`

The remaining warning is a `langchain_community` deprecation warning from the
legacy V1 database tooling.
