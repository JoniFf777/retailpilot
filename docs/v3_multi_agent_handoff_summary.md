# V3.3 Multi-Agent Handoff Summary

This document summarizes the current V3 first-stage state so a future Codex thread can continue without reconstructing the whole history.

## Current status

V3 now has a working read-only multi-agent path with a guarded bridge into a native V3 confirmation-based write handoff handler.

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

If the ambiguous request includes a `thread_id`, the handler stores the candidate product IDs and requested quantity in an in-process, same-thread candidate context. A follow-up such as `选 1` or `第一个` in the same `user_id` + `thread_id` can then resolve to the selected product and create the normal confirmation-required pending action. Without matching candidate context, selection-only messages still return a clarification and do not write.

If the user selects a number outside the current candidate range, the handler returns a completed clarification such as `当前候选只有 1-2`, calls no write tools, creates no pending action, and keeps the candidate context so the user can retry.

Candidate contexts are bounded in memory: entries expire after 10 minutes, and the in-process cache keeps at most 100 contexts by pruning the oldest entries.

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
  - candidate contexts expire and prune oldest entries at the cache limit
  - missing `user_id` handling
  - ambiguous write request handling
  - native `prepare_add_to_cart` invocation
- `tests/api/test_chat_write_handoff_smoke.py`
  - `/api/chat` creates pending action through handoff
  - `/api/chat/confirm` confirms it
  - cart item is written
  - pending action stores original `thread_id`
  - missing product ID and missing `user_id` return clarifications without pending actions
  - candidate selection by number creates the normal confirmation-required action
  - out-of-range candidate selection returns a clarification without pending actions
- `tests/evaluation/test_shopmind_evaluators.py`
  - router eval includes a write-intent guardrail sample
  - debug metadata accepts expected empty routes for write handoff cases
  - pending action presence can be asserted in deterministic eval

Latest full local validation:

```text
170 passed, 4 skipped
router eval deterministic: 7/7
router eval llm-fallback: 7/7
```

## Recommended next step

V3.3 has removed the temporary dependency on the V1 single-agent write path for add-to-cart preparation by introducing and testing a native V3 write handoff handler.

Suggested shape:

- Keep V3 read agents read-only.
- Keep deterministic write handoff parsing conservative: only explicit product IDs or same-thread candidate selections may create pending actions.
- Consider moving candidate context from in-process memory to a durable store if V3 handoff needs to survive process restarts or multi-worker deployment.
- Add observability counters for clarification, candidate selection, out-of-range selection, pending action creation, and confirmation completion.
- Keep `/api/chat/confirm` unchanged.

This would make V3 own both read orchestration and confirmation preparation while preserving the same public API contract.
