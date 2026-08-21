## 1. Establish the regression baseline and safe test boundary

- [x] 1.1 Capture the focused Chat write-handoff and parallel-RAG test commands, with `LANGSMITH_TRACING=false`, integration tests excluded, and a writable isolated pytest basetemp.
- [x] 1.2 Update the Chat write-handoff SQLite fixture so each worker-side context manager creates and closes a fresh Session, while assertions use a separate test-thread inspection Session.
- [x] 1.3 Add a fixture assertion or helper that makes shared live Session reuse across the Chat worker boundary fail deterministically instead of producing teardown-only errors.
- [x] 1.4 Verify that the Chat route still executes synchronous Agent work off the event loop and that no production Session is created on one thread and consumed on another.

## 2. Define and implement truthful RAG result semantics

- [x] 2.1 Add a validated direct-RAG summary status contract covering `success` and intentional `degraded` output only for a tool that is disabled, absent, or known unavailable before invocation; include bounded reason metadata and empty citations.
- [x] 2.2 Change the RAG node so an intentionally missing/disabled tool returns typed degraded output without claiming a tool call, while an exception from an invoked tool propagates to the existing typed adapter/plan failure boundary and is never converted to degraded.
- [x] 2.3 Update the RAG adapter validation and result mapping so invalid or raised tool results cannot be promoted to `AgentTaskStatus.COMPLETED`.
- [x] 2.4 Verify bounded parallel fan-in preserves completed Product/Preference summaries, marks the RAG step failed, marks the plan partial, and omits a fabricated `rag_summary`.
- [x] 2.5 Propagate specialist failure and plan partial state into existing RAG/plan Decision/debug metadata without changing unrelated terminal Chat payload fields, RecommendationResult/API schema, recommendation evidence diagnostics, or global plan-executor semantics.

## 3. Add direct regression coverage

- [x] 3.1 Make `tests/api/test_chat_write_handoff_smoke.py` cover successful request execution, fixture teardown, and owner-thread inspection after the worker-side request completes.
- [x] 3.2 Keep `tests/agents/test_parallel_graph.py::test_parallel_graph_returns_partial_result_when_one_read_fails` asserting failed RAG step status, partial plan status, omitted RAG summary, and bounded error code.
- [x] 3.3 Add a focused test for intentional no-tool RAG degradation that asserts status, reason, empty citations, and no false tool call.
- [x] 3.4 Add or update a focused RAG adapter test asserting an actual tool exception becomes a typed failed specialist result and is not converted to degraded or completed.
- [x] 3.5 Run all directly affected Agent/API/recommendation tests and confirm zero failures and zero errors.

## 4. Suite-level validation and scope guard

- [x] 4.1 Run the complete non-integration backend suite with a writable isolated basetemp and LangSmith tracing disabled; confirm 0 failed and 0 errors.
- [x] 4.2 Verify that the writable-basetemp run has no remaining pytest-permission or assertion errors; no environment failure remains to classify.
- [x] 4.3 Run `git diff --check` and inspect the final diff for scope compliance: only the Chat/RAG session boundary, direct tests, typed semantics, and necessary test configuration may change.
- [x] 4.4 Confirm no LangSmith, Redis, RocketMQ, PostgreSQL integration, external API, workflow, staging, or deployment action was used by validation.
