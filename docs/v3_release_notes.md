# ShopMind V3.0.0 Release Notes

Release date: 2026-07-13

Tag: `v3.0.0`

## Overview

ShopMind V3 moves the project from a single-agent workshop extension to a PostgreSQL-backed multi-agent shopping backend with an explicit human-confirmation boundary for writes. The public endpoints remain:

- `POST /api/chat`
- `POST /api/chat/confirm`

The detailed caller contract is documented in [v3_api_handoff_contract.md](v3_api_handoff_contract.md).

## Highlights

- A LangGraph supervisor routes read requests to Product, RAG, and Preference agents before the Decision agent composes the response.
- Deterministic routing is the default; structured-output LLM routing has deterministic fallback.
- Read agents remain read-only. Add-to-cart requests cross a guarded handoff and create a `pending_action` before any cart mutation.
- Ambiguous product requests can store PostgreSQL-backed candidate contexts and resolve same-thread numeric selections.
- Candidate contexts expire after 10 minutes and are bounded to 100 retained rows.
- PostgreSQL and pgvector store structured business data, runtime state, and indexed documents.
- Stable candidate-context and confirmation events feed metrics, health reports, CI artifacts, job summaries, and PR dashboards.
- FastAPI OpenAPI examples cover explicit add-to-cart, candidate selection, confirmation, and cancellation.

## Safety Contract

- Product reads, document retrieval, and preference reads are isolated from write tools.
- Explicit product IDs or a valid same-thread candidate selection are required before preparing an add-to-cart action.
- Cart mutation occurs only through `/api/chat/confirm` with a valid pending action.
- Smoke and LangSmith evaluation users are cleaned before and after execution.
- `/api/chat/confirm` remains backward compatible with the existing client contract.

## Runtime Configuration

```env
SHOPMIND_AGENT_MODE="multi"
SHOPMIND_SUPERVISOR_ROUTER="deterministic"
DATABASE_URL="postgresql+psycopg://..."
```

For LangSmith evaluation:

```env
LANGSMITH_API_KEY="..."
LANGSMITH_TRACING="true"
LANGSMITH_PROJECT="shopmind-v3"
```

The LangSmith CLIs load `.env` with `override=False`, so process-level environment variables retain precedence.

## Validation Record

- Full local suite: `227 passed, 4 skipped`.
- Deterministic router eval: `7/7` exact matches.
- LLM fallback router eval: `7/7` exact matches.
- PostgreSQL integration tests: `10/10` passed against `0003_candidate_contexts`.
- Combined PostgreSQL and API handoff smoke: passed.
- API handoff cases: `3/3` passed.
- GitHub PostgreSQL Integration workflow: passed on Ubuntu with pgvector PostgreSQL 16.
- LangSmith dataset: `shopmind-v3-handoff-eval`, 2 examples.
- LangSmith experiment: `shopmind-v3-handoff-ef66ba2f`, 2 root runs, 0 errors.
- LangSmith feedback: 6/6 deterministic evaluator scores equal to `1.0`.
- Post-experiment cart, pending-action, and candidate-context rows: all zero.

## Verification Commands

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts/smoke_v3_handoff.py --json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/create_shopmind_dataset.py --target v3-handoff
```

```powershell
$env:SHOPMIND_EVAL_TARGET = "v3-handoff"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_langsmith_eval.py
```

## Known Boundaries

- V3 prepares and confirms add-to-cart actions only.
- Quantity updates, single-item removal, clear cart, checkout, and preference writes are not part of this release.
- Real LLM router behavior depends on the configured provider and model; deterministic routing remains the release baseline.
- The repository still contains the original workshop modules alongside the ShopMind backend.

## Next Release Line

V4 will extend the same confirmation and evaluation architecture to the remaining cart lifecycle operations before adding checkout or other higher-risk writes.
