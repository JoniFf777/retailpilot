# ShopMind V2 Infra Upgrade PR Notes

## Summary

This PR upgrades ShopMind's data infrastructure from the V1 SQLite and
InMemoryVectorStore path to a PostgreSQL + pgvector backed V2 path, while
preserving the existing Agent and API contracts.

Major changes:

- Add centralized V2 settings in `app/core/settings.py`.
- Add PostgreSQL + pgvector local development support.
- Add SQLAlchemy models and Alembic migrations.
- Add seed, documents index, smoke, and bootstrap scripts.
- Add Repository layers for products, preferences, cart, and documents.
- Migrate structured Tools and RAG document Tools to Repository-backed access.
- Add PostgreSQL health endpoint.
- Add SQLite-backed unit tests and opt-in PostgreSQL integration tests.

Final branch commits:

- `cd68257` Add ShopMind V2 PostgreSQL infrastructure
- `58a2425` Add repository agent guidance
- `f5d79a4` Add Chinese workshop materials

## Recommended Staging Scope

Recommended V2 infra files to stage:

```bash
git add .env.example .gitignore README.md pyproject.toml docker-compose.yml
git add alembic.ini alembic
git add app/core app/db app/repositories
git add app/api/routes/health.py
git add tools/products.py tools/preferences.py tools/cart.py tools/documents.py
git add scripts
git add tests/config tests/db tests/repositories tests/scripts tests/integration
git add tests/tools/test_products.py tests/tools/test_preferences.py tests/tools/test_cart.py tests/tools/test_documents.py
git add tests/api/test_health.py tests/agents/test_shopmind_agent.py
git add docs/architecture.md docs/v2_infra_upgrade_handoff.md docs/v2_infra_upgrade_pr_notes.md
```

This staging scope was verified with `git add -n` and only includes V2
infrastructure, repository, Tool/API adapter, script, test, and documentation
changes.

Review separately before staging:

```bash
data/structured/techhub.db
```

Current `techhub.db` audit:

- `data/structured/techhub.db-journal` is not present.
- `data/structured/techhub.db` is not read-only.
- Core fixture counts remain customers `50`, products `25`, orders `250`,
  order_items `439`.
- Runtime state tables are empty: user_preferences `0`, cart_items `0`,
  pending_actions `0`.
- The SQLite file was restored after the audit and is not included in the final
  branch changes.

## Validation

Default regression, no real PostgreSQL required:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests/config tests/db tests/repositories tests/scripts tests/tools tests/api tests/agents tests/evaluation tests/integration
```

Read-only smoke check against configured `DATABASE_URL`:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
```

Real PostgreSQL integration tests:

```bash
set RUN_POSTGRES_INTEGRATION=1
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests/integration
```

Safe bootstrap plan:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\bootstrap_postgres.py
```

Bootstrap an isolated development database:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\bootstrap_postgres.py --execute --confirm-clear --skip-documents
```

## Latest Local Results

- Default regression: `90 passed, 4 skipped, 1 warning`
- PostgreSQL integration: `10 passed`
- Smoke database Alembic version: `0002_documents_pgvector`
- Seed counts: customers `50`, products `25`, orders `250`, order_items `439`
- Documents counts: product `298`, policy `39`

The remaining warning is a `langchain_community` deprecation warning from the
legacy V1 database tooling.

## Rollback Plan

Application-level rollback:

- Revert Tool imports and session helpers in `tools/products.py`,
  `tools/preferences.py`, `tools/cart.py`, and `tools/documents.py`.
- Keep the database migration files if the DB has already been provisioned, but
  stop pointing runtime `DATABASE_URL` at the V2 database.

Database-level rollback for an isolated development database:

- Drop the isolated smoke database, for example `retailpilot_v2_smoke`.
- Recreate and rerun bootstrap if needed.

Database-level rollback for shared environments:

- Do not drop the database.
- Run Alembic downgrade only after confirming no V2 runtime depends on the
  schema.
- Prefer restoring from backup or recreating an isolated V2 database.

## Known Non-Goals

This PR does not introduce:

- Redis
- Milvus
- Qdrant
- LangGraph interrupt/resume
- A new Agent contract
- A new public chat API contract

## Follow-Up Candidates

- Add CI job for default tests.
- Add optional CI/manual job for `RUN_POSTGRES_INTEGRATION=1`.
- Address `langchain_community` deprecation in the legacy V1 database tooling.
