# V3.2 Multi-Agent Handoff Summary

This document summarizes the current V3 first-stage state so a future Codex thread can continue without reconstructing the whole history.

## Current status

V3 now has a working read-only multi-agent path with a guarded bridge into the existing confirmation-based write flow.

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
exact matches: 6/6
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
3. Calls the existing single-agent write confirmation path.
4. Returns the single-agent `confirmation_required` response.
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
- `call_shopmind_agent` passes it into the single-agent write path.
- `invoke_shopmind_agent` includes thread context in the user message.
- `prepare_add_to_cart` receives the thread ID.
- `pending_actions.thread_id` persists it.

The API smoke test asserts the stored pending action row keeps the original thread ID.

## Test coverage

Important tests:

- `tests/agents/test_multi_agent_routing.py`
  - read routing
  - LLM router fallback
  - write-intent guardrail
- `tests/api/test_chat.py`
  - multi mode response schema
  - debug metadata
  - fake V3 handoff bridge
  - real V3 guardrail to handoff bridge
- `tests/api/test_chat_write_handoff_smoke.py`
  - `/api/chat` creates pending action through handoff
  - `/api/chat/confirm` confirms it
  - cart item is written
  - pending action stores original `thread_id`

Latest full local validation:

```text
147 passed, 4 skipped
router eval deterministic: 6/6
router eval llm-fallback: 6/6
```

## Recommended next step

V3.3 should remove the temporary dependency on the V1 single-agent write path by introducing a native V3 write handoff handler.

Suggested shape:

- Keep V3 read agents read-only.
- Add a small deterministic write handoff parser for explicit product IDs.
- For ambiguous write requests, return a clarification response instead of calling tools.
- For clear add-to-cart requests, call `prepare_add_to_cart` directly and return `confirmation_required`.
- Keep `/api/chat/confirm` unchanged.

This would make V3 own both read orchestration and confirmation preparation while preserving the same public API contract.
