# ShopMind V3 API Handoff Contract

This document describes the public API contract for the V3 write handoff flow.
The read-side multi-agent graph remains read-only. When it detects a write
intent, it bridges into the native confirmation-based handoff path and returns
a pending action for the caller to confirm or cancel.

## Runtime Mode

Use V3 multi-agent mode for this flow:

```text
SHOPMIND_AGENT_MODE=multi
SHOPMIND_SUPERVISOR_ROUTER=deterministic
```

The local smoke suite sets these values automatically unless
`--preserve-agent-mode` is used.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/chat` | Handle the user message. Write intents may return a pending action. |
| `POST /api/chat/confirm` | Confirm or cancel a pending action returned by `/api/chat`. |

Both endpoints return `ChatResponse`.

## POST /api/chat

Request:

```json
{
  "message": "add to cart TECH-KEY-010 quantity 2",
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "include_debug": true
}
```

Fields:

| Field | Required | Notes |
| --- | --- | --- |
| `message` | yes | User message. Write handoff currently supports explicit product IDs or same-thread candidate selection. |
| `user_id` | write flow: yes | Required before creating pending add-to-cart actions. |
| `thread_id` | recommended | Required for same-thread candidate selection context. |
| `include_debug` | no | Set to `true` for evaluation, smoke checks, and troubleshooting. |

Explicit product response:

```json
{
  "answer": "Pending add-to-cart action created.",
  "status": "confirmation_required",
  "tool_calls": ["prepare_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "pending-action-id",
  "debug": {
    "multi_agent_handoff": {
      "from": "multi_agent_read_path",
      "to": "v3_write_handoff_path",
      "reason": "read_only_multi_agent_write_intent",
      "status": "confirmation_required"
    }
  }
}
```

Candidate clarification response:

```json
{
  "answer": "Please choose a product ID or candidate number.",
  "status": "completed",
  "tool_calls": [],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": null,
  "debug": {
    "write_handoff_debug": {
      "candidate_context": {
        "events": [
          {
            "event": "candidate_context_stored",
            "candidate_count": 3
          }
        ]
      }
    }
  }
}
```

Same-thread candidate selection request:

```json
{
  "message": "1",
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "include_debug": true
}
```

If the candidate context exists and the selection is valid, the response has
`status="confirmation_required"` and a `pending_action_id`.

## POST /api/chat/confirm

Request:

```json
{
  "user_id": "demo-user",
  "pending_action_id": "pending-action-id",
  "confirmed": true,
  "thread_id": "demo-thread",
  "include_debug": true
}
```

Fields:

| Field | Required | Notes |
| --- | --- | --- |
| `user_id` | yes | Must match the pending action owner. |
| `pending_action_id` | yes | Value returned by `/api/chat`. |
| `confirmed` | yes | `true` confirms the action; `false` cancels it. |
| `thread_id` | no | Echoed in the response for client continuity. |
| `include_debug` | no | Set to `true` to include confirmation events. |

Confirmed response:

```json
{
  "answer": "Action confirmed.",
  "status": "completed",
  "tool_calls": ["confirm_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "pending-action-id",
  "debug": {
    "confirmation": {
      "events": [
        {
          "event": "pending_action_confirmed",
          "status": "completed",
          "tool_call": "confirm_add_to_cart"
        }
      ]
    }
  }
}
```

Cancelled response:

```json
{
  "answer": "Action cancelled.",
  "status": "cancelled",
  "tool_calls": ["cancel_pending_action"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "pending-action-id",
  "debug": {
    "confirmation": {
      "events": [
        {
          "event": "pending_action_cancelled",
          "status": "cancelled",
          "tool_call": "cancel_pending_action"
        }
      ]
    }
  }
}
```

## Status Values

| Status | Meaning |
| --- | --- |
| `completed` | The request finished without requiring confirmation. This can be a read answer, clarification, or cancellation-free outcome. |
| `confirmation_required` | A write action was prepared and must be confirmed or cancelled. |
| `cancelled` | A pending action was cancelled through `/api/chat/confirm`. |
| `failed` | The API could not prepare, confirm, or cancel the requested action. |

## Expected Client Flow

1. Send the user message to `POST /api/chat`.
2. If `status` is `confirmation_required`, show `answer` and ask the user to confirm or cancel.
3. Store `pending_action_id` with the current UI state.
4. Send `POST /api/chat/confirm` with `confirmed=true` or `confirmed=false`.
5. Treat `completed` as confirmed and `cancelled` as cancelled.
6. If `status` is `failed`, show a recoverable error and let the user retry.

## Debug Events

When `include_debug=true`, callers may receive these event names:

| Event | Source | Meaning |
| --- | --- | --- |
| `candidate_context_stored` | `/api/chat` | A product candidate list was saved for same-thread selection. |
| `candidate_context_missed` | `/api/chat` | The user selected a candidate but no context was available. |
| `candidate_context_selected` | `/api/chat` | A candidate number resolved to a product ID. |
| `candidate_context_out_of_range` | `/api/chat` | The selected candidate number was outside the current list. |
| `candidate_context_cleared` | `/api/chat` | A used candidate context was cleared after selection. |
| `pending_action_confirmed` | `/api/chat/confirm` | The pending action was confirmed. |
| `pending_action_cancelled` | `/api/chat/confirm` | The pending action was cancelled. |
| `pending_action_failed` | `/api/chat/confirm` | Confirmation or cancellation failed. |

Debug payloads are for evaluation and observability. Client product behavior
should depend on stable top-level fields: `status`, `answer`, `tool_calls`, and
`pending_action_id`.

## Local Validation

Run the complete local smoke suite after Postgres is available:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts/smoke_v3_handoff.py
```

Machine-readable output:

```bash
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts/smoke_v3_handoff.py --json
```

The suite first checks PostgreSQL readiness, Alembic version, seed data,
documents, and repository searches. It then runs the public API handoff flow
through the in-process FastAPI app.

Smoke runs use fixed `API-HANDOFF-SMOKE-*` user IDs. By default, the runner
deletes runtime rows for those users from `cart_items`, `pending_actions`, and
`candidate_contexts` before and after running. Use `--preserve-runtime-state`
only when you intentionally want to inspect those rows after a smoke run.
