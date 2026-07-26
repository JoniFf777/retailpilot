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

## Optional V6 Identity Binding

The released default remains `SHOPMIND_IDENTITY_PROVIDER=development_payload`,
so existing V3 request bodies and responses are unchanged. An operator may
explicitly select `trusted_header`; then a trusted ingress must remove any
caller-supplied `X-ShopMind-Authenticated-User` value and inject the
authenticated subject.

An operator may instead select `signed_header`. The trusted ingress must remove
all caller copies and inject the same subject plus
`X-ShopMind-Identity-Timestamp`, `X-ShopMind-Identity-Nonce`, and
`X-ShopMind-Identity-Signature`. The server verifies a short-lived versioned
HMAC-SHA256 assertion and atomically claims its fingerprint once through the
configured local/Redis coordination backend. Credential, expiry, replay and
backend failures share the stable HTTP 401
`ShopMindSignedHeader` challenge. The adapter makes no remote IdP/JWKS call.

In trusted-header mode, an omitted header returns HTTP 401. If a body `user_id`
is present and differs from the authenticated subject, the request returns HTTP
403 before read-Agent, write-confirmation or stream-admission execution. If the
body owner is omitted, the authenticated subject becomes the effective
`user_id`. Request bodies cannot supply roles, scopes, identity providers or
credentials.

Slice 4 also defines an internal `shopmind.governance-audit.v1` record for
authentication, tool/action, memory and deletion decisions. It stores
fingerprints and closed allowlisted metadata only. This does not add response
fields or change the V3 JSON/status/confirmation contract. The record now has
an internal PostgreSQL repository with exact-owner fingerprint inspection and
expiry enforcement. A server-owned default-off switch can emit identity,
typed-tool, closed-action and selected-memory facts through an independent
best-effort transaction. It adds no public audit-record inspection endpoint,
response field or caller-controlled policy, and audit failure cannot change V3
HTTP/action results.

The additive `GET /api/health/governance-audit` operations endpoint exposes
only a versioned process-local counter/alert snapshot; it is not an audit-record
endpoint and contains no identity, request or resource fingerprint. It remains
HTTP 200 while degraded, so it does not change V3 liveness, chat, confirmation,
streaming or action results.

## Additive V6 Owner-Data Boundary

The authenticated endpoints below are additive and do not change default
`/api/chat`, `/api/chat/confirm`, or `/api/chat/stream` payloads:

| Endpoint | Boundary |
| --- | --- |
| `POST /api/owner-data/inspect` | Bounded exact-owner inventory and memory inspection |
| `POST /api/owner-data/runs/inspect` | Payload-free exact-owner run/trace projection with bounded client-event summaries |
| `POST /api/owner-data/memory/correct` | Exact-owner active-memory replacement |
| `POST /api/owner-data/memory/delete` | Exact-owner memory hard deletion |
| `POST /api/owner-data/delete` | Explicitly confirmed transactional owner-data deletion |

Every operation requires a bound principal. Trusted-header owner mismatch still
returns 403 before storage access. Full deletion requires a UUID request ID and
literal `confirmed=true`; it excludes catalogs, inherited seed customers/orders
and independently retained fingerprint-only audit facts. A backend failure is
sanitized to HTTP 503 and does not expose an exception, URL or owner record.

Run inspection requires exactly one opaque `run_id` or `trace_id`. It returns
only closed run metadata, typed usage and ordered client-visible event
summaries; request/result JSON, content, debug/error/metadata, tool records,
idempotency records, event payloads and internal/audit events remain private.
The selector is always combined with the authenticated owner and is not an
authorization token.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/chat` | Handle the user message. Write intents may return a pending action. |
| `POST /api/chat/confirm` | Confirm or cancel a pending action returned by `/api/chat`. |

Both endpoints return `ChatResponse`.

### Optional Idempotency Header

All chat, confirmation, and streaming requests may send an `Idempotency-Key`
header. The key is scoped to the current user and operation. Repeating the same
request returns the persisted result without executing tools or adding messages;
reusing a key with different input returns `status="failed"`. Existing clients
that omit the header keep the V3 behavior unchanged.

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
| `include_debug` | no | Set to `true` for evaluation, smoke checks, troubleshooting, and opaque run/trace selectors. |

When `include_debug=true`, chat and confirmation responses may add top-level
`run_id` and `trace_id`; the terminal SSE `run.result` payload may add the same
selectors. They are omitted by default, so existing V3 clients receive the
unchanged payload. A bound owner can pass one selector to
`POST /api/owner-data/runs/inspect`; the selector alone never authorizes access.

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
| `include_debug` | no | Set to `true` to include confirmation events and opaque run/trace selectors. |

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
`pending_action_id`. Optional `run_id` and `trace_id` are correlation selectors
for authenticated inspection, not business-status fields or credentials.

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
