## Why

The current brownfield worktree does not have a green non-integration backend test suite. A focused rerun on 2026-08-17 produced 5 failed tests and 3 teardown errors; the full non-integration run produced 747 passed, 8 failed, 28 errors, and 2 skipped. The failures are concentrated in the current Chat thread-pool change and the current RAG exception handling, so they need a bounded stabilization change before any further product work.

This change is needed now because the failures are not harmless test noise: the Chat route crosses a thread boundary while test fixtures inject one thread-affine SQLite Session, and RAG tool exceptions are converted into ordinary success-shaped summaries. The latter can make the parallel plan report `completed` when a specialist actually failed.

## What Changes

- Preserve the production-oriented synchronous Agent execution off the FastAPI event loop; repair the session/fixture/thread boundary so SQLite tests do not share a thread-affine Session across worker threads.
- Repair the Chat Agent/test database session ownership boundary without making production code depend on SQLite-specific behavior; add a production DI seam only if the test fixture cannot be repaired cleanly.
- Make actual RAG tool failures observable as typed specialist failure, while allowing typed degraded output only when optional RAG is known to be disabled or unavailable before invocation.
- Align parallel plan fan-in, Decision Agent behavior, persisted runtime status, and test assertions with the chosen RAG failure semantics.
- Add focused regression coverage for Chat thread isolation, actual RAG tool failure, disabled/no-tool degraded RAG behavior, partial fan-in, and the full non-integration backend suite.
- Do not change unrelated commerce, payment, inventory, identity, frontend, MQ, or product-catalog behavior.

### Acceptance Criteria

- All currently relevant regression tests pass.
- The complete non-integration backend suite reports 0 failed and 0 errors.
- A RAG tool exception cannot be reported as `completed` for that specialist step.
- Actual RAG tool invocation exceptions are failed specialist/task results and are never represented as `degraded`; Product/Preference success plus RAG failure produces a partial plan.
- RAG `degraded` is reserved for a disabled/no-tool path known before any tool invocation, with bounded reason metadata, no citations, and no claim that a tool ran.
- The production thread-isolation design remains intact; the fix does not remove thread offloading merely to satisfy SQLite tests.
- No behavior outside this change's scope is intentionally modified.
- Validation does not access LangSmith, Redis, RocketMQ, PostgreSQL integration services, or other external APIs.

## Capabilities

### New Capabilities

- `backend-regression-stability`: Defines the backend execution-boundary and specialist-failure semantics required for a green, truthful non-integration regression suite.

### Modified Capabilities

None. The repository has no existing main specs under `openspec/specs/`; this change introduces the bounded capability contract for the stabilization work.

## Impact

- Likely production-code impact: `agents/shopmind_multi_agent/rag_agent.py` and its existing typed adapter/plan boundary. `app/api/routes/chat.py` is expected to remain unchanged unless a minimal DI seam is proven necessary after the fixture-level repair is attempted.
- Likely test impact: the Chat write-handoff fixture/tests, `tests/agents/test_parallel_graph.py`, direct RAG adapter tests only where they assert the specialist failure contract, and test-run configuration only where needed to provide thread-safe session ownership.
- No RecommendationResult/API schema, post-ranking recommendation evidence diagnostics, `recommendation_nodes.py`/provider behavior, database schema, commerce state machine, payment provider, Outbox, Redis, RocketMQ, or frontend contract changes are authorized by this Change.
