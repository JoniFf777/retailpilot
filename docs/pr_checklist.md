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

## PostgreSQL Changes

- [ ] If database schema or repository behavior changed, run the default tests above.
- [ ] If local PostgreSQL is available, run the smoke check:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts/smoke_postgres.py
  ```

- [ ] For real PostgreSQL integration tests, use an isolated test database and set `RUN_POSTGRES_INTEGRATION=1`.

## CI

- [ ] Confirm the GitHub Actions default CI passes.
- [ ] Keep true PostgreSQL integration out of default CI unless the workflow explicitly provisions an isolated PostgreSQL + pgvector service.
