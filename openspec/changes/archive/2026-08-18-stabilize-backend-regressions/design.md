## Context

The proposal describes the motivation and bounded scope. The current code has two distinct failure mechanisms:

1. `app/api/routes/chat.py` uses `run_in_threadpool`, which is appropriate because `call_shopmind_agent` is synchronous and may perform database and model work. The failing Chat write-handoff tests monkeypatch both tool session context managers to yield one in-memory SQLite `Session` created on the pytest thread (`tests/api/test_chat_write_handoff_smoke.py:25-53`). The route then uses that same Session from the worker thread, causing SQLite thread-affinity errors and teardown failures. This is a session ownership defect in the test seam, not evidence that production thread offloading should be removed.
2. The current RAG node catches every tool exception and returns a normal-looking summary (`agents/shopmind_multi_agent/rag_agent.py:94-107`). The local RAG adapter then unconditionally converts every valid node result into `AgentTaskStatus.COMPLETED` (`agents/shopmind_multi_agent/rag_adapter.py:77-98`). As a result, the plan executor cannot produce the existing `failed` step / `partial` plan semantics expected by `tests/agents/test_parallel_graph.py:196-214`.

The full non-integration run also contains environment-level pytest temporary-directory errors because the default Windows pytest root is not accessible in this session. Those errors are not treated as production Chat/RAG causes; validation must use a writable, isolated basetemp and report any remaining test errors separately.

## Goals / Non-Goals

**Goals:**

- Keep synchronous Chat Agent execution outside the FastAPI event loop.
- Ensure every test-created database Session is owned, opened, used, and closed within the thread that executes it.
- Make actual RAG tool invocation failures observable as failed specialist steps and partial plans when independent read steps succeed.
- Represent intentionally unavailable optional RAG specialist execution as a typed `degraded` RAG summary, not as a successful tool result.
- Preserve the existing bounded plan executor, fan-in, decision, runtime persistence, and public Chat compatibility semantics wherever possible.
- Add focused tests that distinguish session/thread failures, intentional disabled/no-tool degraded RAG, actual RAG tool failure, and partial fan-in.

**Non-Goals:**

- No legacy Cart migration, Order expiry, inventory release worker, Chat/SSE retry idempotency, Single Agent HITL redesign, localization, multi-category recommendation, catalog expansion, RocketMQ Consumer/Inbox, real payments, formal authentication, frontend work, or unrelated refactoring.
- No PostgreSQL schema or external service changes.

## Decisions

### 1. Preserve the production thread boundary

`run_in_threadpool` remains in `chat.py`. The test fixture will stop yielding a shared Session across the boundary. It will own the SQLite engine and expose a Session factory/context manager that creates and closes a fresh Session for each worker-side database operation. If an in-memory database must be shared between those Sessions, the test-only engine may use a shared connection configuration with SQLite thread checking disabled; the Session object itself must never be shared across threads. Assertions will use a separate owner-thread inspection Session and refresh/reopen it after the request commits.

This keeps production behavior based on normal per-operation `SessionLocal` ownership and prevents a SQLite-only setting from masking unsafe Session sharing.

### 2. Separate intentional degradation from invocation failure

The RAG contract will use two levels of status:

- An intentional no-tool/disabled optional path returns a validated RAG summary with `status: degraded`, a bounded reason code such as `rag_disabled` or `embedding_unavailable`, no fabricated citations, and no claim that a tool ran.
- An exception from an actual RAG tool invocation is not converted to a summary. It propagates through the existing typed adapter/policy boundary so the plan executor records a failed step. A bounded parallel plan with other completed read steps becomes `partial`; a plan with no usable completed step remains failed/insufficient according to the existing runtime contract.

The adapter-side output model will validate the direct RAG summary status. The current broad catch in `rag_agent.py` will not be retained for actual tool calls. Existing post-ranking recommendation evidence behavior and diagnostics, including `evidence_unavailable`, are out of scope and must not be redesigned by this Change.

### 3. Reuse existing plan and fan-in semantics

The general `BoundedPlanExecutor` already maps exceptions to failed step results and aggregates independent successes as a partial plan. The change will make RAG reach that boundary instead of bypassing it. `merge_parallel_step_results` will continue to merge only completed step output, so a failed RAG step cannot leave a fake `rag_summary` in state. The Decision Agent may produce a usable response from remaining summaries, but its existing specialist/plan metadata must identify the partial result; the failed RAG specialist itself must never be marked completed. This Change does not alter structured recommendation evidence behavior.

This avoids changing global executor behavior or discarding valid Product/Preference summaries merely because optional RAG failed.

### 4. Keep the public Chat contract stable

No new endpoint or database migration is required. Existing terminal Chat response values remain compatible. Truthful specialist/plan status is carried through the existing runtime debug and parallel execution metadata, while intentional pre-invocation degraded RAG is represented in the validated direct summary. Existing clients that only consume the final answer continue to work; diagnostic and regression tests can distinguish specialist success, task failure, plan partial, and pre-invocation degraded RAG states.

### Alternatives considered

- **Remove `run_in_threadpool`:** rejected because synchronous Agent/database work would block the Uvicorn event loop and regress the newly added responsiveness guarantee.
- **Set SQLite `check_same_thread=False` on production sessions or add a global test lock:** rejected because it hides shared-Session ownership errors and does not model production lifecycle correctly.
- **Keep swallowing every RAG exception:** rejected because it produces a false completed specialist and prevents retry/failure accounting.
- **Mark the entire multi-read run failed for every RAG error:** rejected because the existing bounded parallel contract intentionally supports partial results from independent read agents.
- **Add a new global runtime `DEGRADED` task status:** rejected for this change; intentional optional degradation can be expressed in the typed RAG summary, while actual tool failures use existing step `failed` and plan `partial` statuses.

## Risks / Trade-offs

- **[Risk]** A shared in-memory SQLite fixture may still leak a connection across threads if only the Session wrapper is changed. **Mitigation:** create a fresh Session per context, close it in the worker, and use a separate inspection Session; add an explicit thread-identity regression test.
- **[Risk]** Partial RAG results may be misunderstood as fully successful specialist execution. **Mitigation:** require explicit plan partial metadata, omit a fabricated `rag_summary`, and preserve the existing safe-summary language.
- **[Risk]** Existing tests or consumers may assume every direct RAG summary lacks a status field. **Mitigation:** add the field only to the direct RAG specialist summary with a deterministic success/degraded contract, and update only direct RAG/parallel assertions.
- **[Risk]** Environment pytest errors may obscure the code regression. **Mitigation:** run the suite with an explicitly writable basetemp and report environment failures separately from test assertion failures.

## Migration Plan

No database or deployment migration is required. Implementation should be applied in this order: repair the test Session factory/fixture, add typed direct-RAG disabled/failure semantics, update direct regression tests, run the focused tests, then run the full non-integration suite with LangSmith disabled and a writable basetemp. Rollback is a code-only revert of the change artifacts' implementation tasks; do not remove the production thread offload.
