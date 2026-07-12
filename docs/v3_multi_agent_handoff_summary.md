# V3.18 Multi-Agent Handoff Summary

This document summarizes the current V3 first-stage state so a future Codex thread can continue without reconstructing the whole history.

## Current status

V3 now has a working read-only multi-agent path with a guarded bridge into a native V3 confirmation-based write handoff handler. Candidate selection context is database-backed through `candidate_contexts`, so same-thread selection can survive process restarts and multi-worker routing as long as the shared database is available. V3.18 aligns the production-like API handoff smoke fixture with the seeded PostgreSQL product IDs and deterministic router write-intent phrases, on top of the V3.17 smoke runner, the V3.16 LangSmith evaluation runner for the seeded API handoff dataset, same-repository PR dashboard comments, GitHub Actions job-summary publishing, uploaded CI-friendly event artifact bundles, local event health reports, Prometheus-style metric export, the dedicated API handoff evaluation target, event reporting helpers, and the V3.15 LangSmith-seedable API handoff dataset.

Runtime switches:

```text
SHOPMIND_AGENT_MODE=multi
SHOPMIND_SUPERVISOR_ROUTER=deterministic | llm
```

The public API contract remains compatible with the existing endpoints:

- `POST /api/chat`
- `POST /api/chat/confirm`

## Read path

The V3 graph lives under `agents/shopmind_multi_agent/` and includes:

- `supervisor`: creates the structured route decision.
- `product_agent`: read-only product search summary.
- `rag_agent`: read-only product docs / policy summary.
- `preference_agent`: read-only user preference summary.
- `decision_agent`: combines structured summaries into the final answer.
- `route_dispatcher`: runs selected read agents in order, then sends control to `decision_agent`.

Stable debug fields are exposed through `build_multi_agent_debug_metadata`:

- `supervisor_decision`
- `agent_steps`
- `routes`
- `executed_routes`
- `decision`
- `safety_flags`

## Router support

Router modes:

- `deterministic`: keyword-based, default, no model call.
- `llm`: LangChain structured-output router with deterministic fallback.

Router metadata can include:

- `router_type`
- `router_provider`
- `router_model`
- `fallback_reason`
- `fallback_router_type`

Offline eval:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --router deterministic
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --router llm-fallback
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --mode target --router deterministic
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --mode handoff
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --mode handoff --event-metrics
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --mode handoff --event-report
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --mode handoff --event-artifacts-dir artifacts/v3-handoff
```

Expected current result for deterministic and llm-fallback fixed samples:

```text
deterministic exact matches: 7/7
llm-fallback exact matches: 7/7
failures: none
```

## Write-intent guardrail

V3 read path is intentionally read-only. Write requests such as add-to-cart, checkout, cart clearing, and preference writes are blocked before any read agent runs.

Expected V3 guardrail decision:

```json
{
  "intent": "write_path_unsupported",
  "routes": [],
  "safety_flags": ["write_intent_blocked"],
  "handoff_reason": "read_only_multi_agent_write_intent"
}
```

The decision agent then returns:

```json
{
  "status": "handoff_required",
  "answer_type": "write_path_handoff",
  "followup_reason": "read_only_multi_agent_write_intent"
}
```

## API handoff bridge

In `app/dependencies/agent.py`, `call_shopmind_agent` now:

1. Runs V3 first when `SHOPMIND_AGENT_MODE=multi`.
2. Detects `decision.answer_type == "write_path_handoff"`.
3. Calls the native V3 write handoff handler.
4. Returns the handler's `confirmation_required` response when the request has an explicit product ID.
5. Preserves V3 guardrail metadata under `debug.multi_agent_handoff` and `debug.multi_agent_debug` when `include_debug=true`.

The bridge keeps the user-facing API behavior unchanged:

```json
{
  "status": "confirmation_required",
  "tool_calls": ["prepare_add_to_cart"],
  "pending_action_id": "..."
}
```

When `include_debug=true`, write handoff results can include stable candidate-context observability metadata under:

```json
{
  "debug": {
    "write_handoff_debug": {
      "candidate_context": {
        "events": [
          {"event": "candidate_context_stored"},
          {"event": "candidate_context_selected"},
          {"event": "candidate_context_cleared"}
        ]
      }
    }
  }
}
```

Current candidate-context event names:

- `candidate_context_stored`
- `candidate_context_skipped`
- `candidate_context_missed`
- `candidate_context_selected`
- `candidate_context_out_of_range`
- `candidate_context_cleared`

`/api/chat/confirm` also accepts `include_debug=true` and can expose confirmation-completion metadata:

```json
{
  "debug": {
    "confirmation": {
      "events": [
        {"event": "pending_action_confirmed"}
      ]
    }
  }
}
```

Current confirmation event names:

- `pending_action_confirmed`
- `pending_action_cancelled`
- `pending_action_failed`

## Event reporting

V3.7 added `evaluation/shopmind_event_reporting.py` for aggregating debug events from API or evaluation outputs.

Supported helpers:

- `extract_debug_events(output)`: extracts candidate-context and confirmation event records.
- `summarize_debug_events(outputs)`: returns event counts, group counts, per-output event rates, and output event coverage.
- `format_event_summary(summary)`: formats a readable report for CLI output.
- `event_summary_metric_rows(summary)`: flattens summary counters and rates into metric rows.
- `format_event_metrics(summary)`: prints Prometheus-style text samples.
- `build_event_health_report(summary)`: checks event coverage and required event/group presence.
- `format_event_health_report(report)`: renders the health report for local review or CI artifacts.
- `format_event_dashboard_markdown(report)`: renders a compact Markdown dashboard.
- `write_event_artifacts(summary, output_dir)`: writes summary JSON, metrics, health, and dashboard files.

`evaluation/run_router_eval.py --mode target` includes an `event_summary` object in its raw summary and prints a compact event section in text output. The real target mode still depends on configured data access for read-agent tools; unit tests cover the event-summary integration with fake targets.

V3.8 adds `evaluation/shopmind_handoff_eval.py`, which runs fixed API-boundary handoff cases through the same dependency functions used by `/api/chat` and `/api/chat/confirm`. `evaluation/run_router_eval.py --mode handoff` prints case pass rates plus the aggregate candidate-context and confirmation event summary. Unit tests use fake chat/confirm functions so this target is covered without requiring database connectivity.

V3.9 adds `evaluation/run_router_eval.py --mode target --event-metrics` and `--mode handoff --event-metrics` for operational export. The text output includes stable samples such as `shopmind_v3_debug_events_total`, `shopmind_v3_debug_group_events_total{group="confirmation"}`, and `shopmind_v3_debug_events_by_name_total{event="pending_action_confirmed",group="confirmation"}`.

V3.10 adds `evaluation/run_router_eval.py --mode target --event-report` and `--mode handoff --event-report`. Handoff reports require candidate-context and confirmation groups, require `candidate_context_stored` and `pending_action_confirmed`, and require at least 50% output event coverage. The report status is `pass` or `warn` so it can be stored as a CI artifact without changing existing eval exit codes.

V3.11 adds `evaluation/run_router_eval.py --mode target --event-artifacts-dir <dir>` and `--mode handoff --event-artifacts-dir <dir>`. The directory contains:

- `event_summary.json`
- `event_metrics.prom`
- `event_health.txt`
- `event_dashboard.md`

V3.12 adds `evaluation/generate_event_artifacts.py`, a deterministic sample artifact generator that requires no database or LLM access. The default `.github/workflows/ci.yml` runs it after the default test suite and uploads the `v3-event-artifacts` artifact with `actions/upload-artifact@v4`.

V3.13 also appends `artifacts/v3-events/event_dashboard.md` to `$GITHUB_STEP_SUMMARY`, so the CI run page shows the V3 event health dashboard without downloading artifacts.

V3.14 uses `actions/github-script@v7` to create or update a PR comment marked with `<!-- v3-event-summary -->`. The comment step only runs for pull requests whose head repository is the same as the base repository, avoiding write-token use for external forks.

V3.15 adds `evaluation/create_shopmind_dataset.py --target v3-handoff`, which seeds `shopmind-v3-handoff-eval` from `HANDOFF_EVAL_CASES`. Examples include `/api/chat` inputs, optional confirm intent, expected chat/confirm statuses, and expected debug events.

V3.16 adds `SHOPMIND_EVAL_TARGET=v3-handoff` support to `evaluation/run_langsmith_eval.py`. The runner executes the seeded chat/confirm examples, returns nested `chat_output` and `confirm_output`, aggregates debug events, and evaluates them with deterministic handoff status/event evaluators.

V3.17 adds `evaluation/shopmind_api_handoff_smoke.py`, an in-process FastAPI smoke runner that exercises `/api/chat` and `/api/chat/confirm` without LangSmith. It defaults to `SHOPMIND_AGENT_MODE=multi` and deterministic supervisor routing, covers explicit confirmation, explicit cancellation, and same-thread candidate selection before confirmation, and returns a non-zero exit code when smoke failures are detected.

V3.18 updates that smoke runner's explicit product fixtures to use `TECH-KEY-010`, which exists in the PostgreSQL seed data, and uses `add to cart ...` phrasing so the deterministic router reliably takes the write handoff path. Against the local configured PostgreSQL database, `scripts/smoke_postgres.py` passed and `evaluation/shopmind_api_handoff_smoke.py` passed 3/3 cases.

## Thread handling

`thread_id` is now propagated through the bridge:

- `/api/chat` receives `thread_id`.
- `call_shopmind_agent` passes it into the native V3 write handoff handler.
- `prepare_add_to_cart` receives the thread ID.
- `pending_actions.thread_id` persists it.

## Quantity handling

The native V3 write handoff handler defaults quantity to `1`. It can also parse simple explicit quantities before calling `prepare_add_to_cart`, including:

- Arabic-number patterns such as `2 个`, `quantity 3`, `x4`
- Common Chinese-number patterns such as `两个`

Ambiguous quantities are intentionally ignored for now and fall back to `1`.

The API smoke test asserts the stored pending action row keeps the original thread ID.

## Clarification handling

The native V3 write handoff handler only prepares a confirmation action when the request has both:

- a `user_id`
- an explicit product ID such as `TECH-KEY-001`

If either is missing, the handler returns a completed clarification response, calls no write tools, and does not create a pending action.

When the request has no explicit product ID but includes a recognizable product category or conservative English product keyword, the handler performs a read-only catalog lookup and includes up to three in-stock candidate product IDs in the clarification. This keeps the write path explicit: the user still has to reply with a concrete `TECH-...` ID before `prepare_add_to_cart` can run.

If the ambiguous request includes a `thread_id`, the handler stores the candidate product IDs and requested quantity in a database-backed, same-thread candidate context. A follow-up such as `选 1` or `第一个` in the same `user_id` + `thread_id` can then resolve to the selected product and create the normal confirmation-required pending action. Without matching candidate context, selection-only messages still return a clarification and do not write.

If the user selects a number outside the current candidate range, the handler returns a completed clarification such as `当前候选只有 1-2`, calls no write tools, creates no pending action, and keeps the candidate context so the user can retry.

Candidate contexts are bounded in the database: entries expire after 10 minutes, and the repository keeps at most 100 contexts by pruning the oldest entries.

Request-time pruning still runs when candidate contexts are saved. V3.5 also adds an explicit cleanup command for low-traffic environments where expired rows may not be touched often:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts/cleanup_candidate_contexts.py
```

Local router eval now includes a fixed write-intent guardrail case for a missing-product-ID add-to-cart request. The case expects:

- `routes: []`
- `intent: write_path_unsupported`
- `answer_type: write_path_handoff`
- `write_intent_blocked`
- no `pending_action_id`
- no `prepare_add_to_cart` or `confirm_add_to_cart` tool call

## Test coverage

Important tests:

- `tests/agents/test_multi_agent_routing.py`
  - read routing
  - LLM router fallback
  - write-intent guardrail
  - candidate selection messages route to write handoff instead of read agents
- `tests/api/test_chat.py`
  - multi mode response schema
  - debug metadata
  - mocked V3 handoff result
  - real V3 guardrail to handoff bridge
- `tests/agents/test_write_handoff.py`
  - explicit product ID parsing
  - simple quantity parsing
  - ambiguous product-category requests return catalog candidates
  - same-thread numeric candidate selection creates a pending action
  - out-of-range candidate selections clarify without writing
  - candidate-context debug events for store, miss, selection, and clear
  - missing `user_id` handling
  - ambiguous write request handling
  - native `prepare_add_to_cart` invocation
- `tests/repositories/test_candidate_contexts_repository.py`
  - database-backed candidate context save/read
  - expired context deletion
  - oldest-row pruning at the cache limit
  - explicit context clearing
- `tests/api/test_chat_write_handoff_smoke.py`
  - `/api/chat` creates pending action through handoff
  - `/api/chat/confirm` confirms it
  - cart item is written
  - pending action stores original `thread_id`
  - missing product ID and missing `user_id` return clarifications without pending actions
  - candidate selection by number creates the normal confirmation-required action
  - write handoff debug metadata is exposed through API debug output
  - confirmation debug metadata is exposed through API debug output
  - out-of-range candidate selection returns a clarification without pending actions
- `tests/scripts/test_cleanup_candidate_contexts.py`
  - explicit cleanup deletes expired rows and oldest overflow rows
- `tests/evaluation/test_shopmind_evaluators.py`
  - router eval includes a write-intent guardrail sample
  - debug metadata accepts expected empty routes for write handoff cases
  - pending action presence can be asserted in deterministic eval
  - V3 debug event extraction and event summary aggregation
  - router target summaries include event summaries
  - API handoff eval cases aggregate chat/confirm event summaries
  - `run_router_eval.py --mode handoff` has CLI coverage with fake targets
  - event summary metric rows and Prometheus-style output are covered
  - `run_router_eval.py --mode handoff --event-metrics` has CLI coverage
  - event health reports cover pass and warning states
  - `run_router_eval.py --mode handoff --event-report` has CLI coverage
  - event dashboard Markdown and artifact file generation are covered
  - `run_router_eval.py --mode handoff --event-artifacts-dir` has CLI coverage
  - deterministic sample event artifact generation is covered
  - default CI workflow artifact upload wiring is covered
  - default CI workflow job-summary publishing is covered
  - default CI workflow same-repository PR comment wiring is covered
  - V3 handoff LangSmith dataset example generation is covered
  - V3 handoff LangSmith dataset refresh uses seed metadata
  - V3 handoff LangSmith runner config and deterministic handoff evaluators are covered
  - V3 API handoff smoke runner case flow, event checks, formatting, and case coverage are covered
  - V3 API handoff smoke explicit product fixtures are pinned to seeded product IDs and deterministic write-intent phrasing

Latest full local validation:

```text
209 passed, 4 skipped
router eval deterministic: 7/7
router eval llm-fallback: 7/7
postgres smoke: passed on local configured database
api handoff smoke: 3/3 on local configured database
```

## Recommended next step

V3.18 keeps the native V3 write handoff path confirmation-based, database-backed, observable through stable debug metadata, measurable through aggregate event reporting, exportable as operational event metrics, reviewable through local health reports, packageable as CI-friendly artifacts, uploaded from the default CI workflow, visible in the GitHub Actions job summary, surfaced as a same-repository PR comment, seedable as a LangSmith API handoff dataset, runnable through the shared LangSmith evaluation entrypoint, and smoke-testable through the public FastAPI endpoints without LangSmith.

Suggested shape:

- Keep V3 read agents read-only.
- Keep deterministic write handoff parsing conservative: only explicit product IDs or same-thread candidate selections may create pending actions.
- Run `evaluation/shopmind_api_handoff_smoke.py` in any environment with a configured application database before treating the API handoff flow as deployment-ready.
- Consider adding a richer dashboard that consumes the generated artifact bundle.
- In an environment with database and LangSmith credentials, run `SHOPMIND_EVAL_TARGET=v3-handoff` to record the handoff experiment.
- Keep `/api/chat/confirm` unchanged.

This would make V3 own both read orchestration and confirmation preparation while preserving the same public API contract.
