# PR Checklist

Use this checklist before opening or merging changes into `main`.

## Required

- [ ] Run the default local regression suite:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests/config tests/db tests/repositories tests/scripts tests/tools tests/api tests/agents tests/evaluation tests/integration
  ```

- [ ] Confirm `git status --short --branch` only shows intentional changes.
- [ ] Update README or docs when commands, environment variables, schemas, workflows, or developer setup steps change.
- [ ] Keep local Python commands on the existing `pythonLearn` conda environment. Do not create a new Python environment and do not use `python`, `pytest`, or `uv run` directly.

## ShopMind V3 Router / Multi-Agent Changes

- [ ] If supervisor routing, multi-agent graph behavior, route eval cases, or router documentation changed, run the deterministic router eval:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --router deterministic
  ```

- [ ] If LLM router fallback behavior or observability changed, run the no-model fallback check:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --router llm-fallback
  ```

- [ ] Only run `evaluation/run_router_eval.py --router llm` when you intentionally want a real structured model call and have configured provider credentials.

## PostgreSQL Changes

- [ ] If database schema or repository behavior changed, run the default tests above.
- [ ] If local PostgreSQL is available, run the smoke check:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts/smoke_postgres.py
  ```

- [ ] For real PostgreSQL integration tests, use an isolated test database and set `RUN_POSTGRES_INTEGRATION=1`.

## CI

- [ ] Confirm the GitHub Actions default CI passes.
- [ ] Run the manual PostgreSQL Integration workflow when database schema, repository behavior, pgvector documents, or PostgreSQL-backed API paths change.
- [ ] Keep true PostgreSQL integration out of default CI unless the workflow explicitly provisions an isolated PostgreSQL + pgvector service.
