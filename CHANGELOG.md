# Changelog

All notable ShopMind changes are documented in this file.

## [3.0.0] - 2026-07-13

### Added

- PostgreSQL and pgvector persistence for structured data, runtime state, and documents.
- LangGraph multi-agent read orchestration with Product, RAG, Preference, and Decision agents.
- Confirmation-based V3 add-to-cart handoff through the existing public chat API.
- Database-backed candidate selection contexts with expiration and bounded cleanup.
- Stable debug events, event metrics, health reports, dashboards, and CI artifacts.
- PostgreSQL, public API handoff, combined smoke, OpenAPI contract, and LangSmith evaluation coverage.

### Changed

- GitHub Actions now use Node.js 24-based official action versions.
- LangSmith dataset and experiment CLIs load project `.env` configuration without overriding explicit process variables.
- The Python package version is now aligned with the ShopMind V3 release.

### Validation

- Full local suite: `227 passed, 4 skipped`.
- PostgreSQL integration tests: `10/10` passed.
- API handoff smoke: `3/3` passed.
- LangSmith handoff experiment: 2 runs, 0 errors, and 6/6 evaluator scores equal to `1.0`.
- Evaluation and smoke runtime rows are cleaned after execution.

Full details: [V3.0.0 release notes](docs/v3_release_notes.md).
