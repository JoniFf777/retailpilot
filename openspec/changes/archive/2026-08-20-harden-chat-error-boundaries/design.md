## Context

See `proposal.md` for motivation. The current repository already has stable typed runtime/domain errors, `ChatResponse.retry_state`, `runtime_error_code`, and `authoritative_run_id`; the problem is inconsistent projection at the route and SSE exception edges.

Confirmed current risks:

- `app/api/routes/chat_confirm.py:42-49` builds `answer` with `str(exc)` for any unexpected confirmation exception.
- `app/api/routes/chat.py` has no local exception projection around the synchronous Agent bridge.
- `app/api/routes/chat_stream.py:140-157` queues a raw exception object; the generator later emits `run.failed` with only `{"error": "runtime execution failed"}`.
- `app/api/chat_response.py:20-63` validates recommendations safely but does not consistently derive the public error code/message from `RunResult.error`.
- `app/runtime/harness.py` creates structured `RunError` objects and safe runtime codes, but the legacy dict projection does not always carry them into the public response.
- `app/core/logging.py` already provides bounded JSON logging and sensitive-value redaction; no new observability platform is needed.

## Goals / Non-Goals

**Goals:**

- One small public Chat error projection policy shared by JSON, SSE, and confirm.
- Apply the same policy to `include_debug=true`; public debug is still public and is not an internal traceback channel.
- Preserve known domain/runtime codes and safe messages.
- Convert unknown exceptions to one generic bounded public failure while retaining internal diagnostics.
- Preserve nonterminal idempotency recovery and authoritative Run identity.
- Keep frontend and public schema changes additive/minimal; expected result is no frontend implementation change.

**Non-Goals:**

- No global exception framework, auth redesign, RAG/recommendation redesign, payment/order changes, PendingAction schema redesign, Chat retry redesign, localization, or new observability platform.
- No changes to database schema, transaction ownership, Cart/HITL semantics, or Agent business behavior.

## Error Inventory

| Boundary | Error source | Current public projection | Leak risk | Final policy |
|---|---|---|---|---|
| POST `/api/chat` | Agent bridge raises after Harness execution | Framework-generated 500; no stable Chat code | Inconsistent status/code and diagnostics | Catch at public boundary; expected typed result stays typed, unknown becomes safe `runtime.internal_error` Chat failure |
| POST/SSE `/api/chat/stream` | `call_shopmind_agent` raises in `asyncio.to_thread` | Raw exception object internally becomes generic `run.failed` with no code | JSON/SSE semantic drift; no recoverability signal | Convert to same safe Chat failure projection and typed SSE payload; never serialize exception text |
| `/api/chat/confirm` | PendingAction/domain/runtime or unexpected exception | Known tool outcomes may be typed; unexpected `str(exc)` is placed in `answer` | SQL/driver/path/provider details leak | Preserve known action code; rollback/log unexpected exception and return bounded `runtime.internal_error` |
| PendingAction confirmation | `PendingActionServiceError`, version/owner/expiry/schema/inventory/preference failure | Canonical Cart outcomes are typed; legacy/adapter failures vary | Stable codes can be lost in adapter text | Preserve existing action code/details and safe message; never parse raw presentation text for classification |
| Runtime persistence/idempotency | Harness `RunError`, claim/finish persistence failure | Some metadata has `runtime_error_code`; projection can omit `RunResult.error` | Typed error may appear as blank/generic terminal response | Project stored error code/message safely; preserve `runtime.idempotency_in_progress` as nonterminal and authoritative ID |
| Tool / write-handoff | `ToolGatewayExecutionError`, adapter/tool exception | Tool record has bounded error code; outer JSON/SSE edges may lose it | Raw adapter details or inconsistent code | Map known tool/runtime codes; unknown tool exception becomes safe internal error; retain audit record |
| Unexpected internal exception | Python/SQLAlchemy/driver/provider/IO exception | Confirm currently interpolates text; JSON may be framework default; SSE generic | SQL, driver, filesystem, Python internals, secrets | Public `runtime.internal_error` with bounded message; internal sanitized logging with exception class/traceback policy |
| Validation/auth/owner/thread | FastAPI validation, identity boundary, scoped PendingAction lookup | Existing 4xx/typed action responses | Inconsistent envelope but not raw exception | Preserve existing 4xx/auth/action semantics; do not downgrade to generic internal error |
| In-progress/recoverable runtime | `runtime.idempotency_in_progress` | `ChatResponse` fields already support typed state | Could be converted to failed by generic catch | Preserve code, `retry_state=in_progress`, authoritative Run ID, and retry/recover semantics |

## Decisions

### 1. Use a small allowlisted public error policy

Introduce a narrow Chat-boundary mapping seam, not a global exception framework. The policy receives a structured `RunError`, known domain/action error, or unexpected exception and returns:

```text
public code
safe bounded message
terminal/recoverable state
optional authoritative run id
```

Known stable codes are preserved from existing runtime/action/cart/payment conventions. Unknown codes and unexpected exceptions map to `runtime.internal_error`; the original exception is never used as the public message. Messages are selected from a bounded code map, with one generic fallback.

### 2. Project existing RunResult errors before constructing ChatResponse

`build_chat_response` and the legacy dict projection should use `RunResult.error.code` as a fallback when metadata does not already contain `runtime_error_code`. A failed result with a known `RunError` gets its bounded safe message and code. This fixes the current blank/error-code omission without changing Run state or persistence.

`runtime.idempotency_in_progress` is special: it remains `retry_state=in_progress`, retains `authoritative_run_id`, and is never passed through terminal-failure mapping.

### 3. JSON and SSE share the same terminal payload semantics

For normal runtime results, JSON and SSE both use the existing `ChatResponse` projection. For a stream-side exception, the producer converts the exception to a safe typed Chat failure before enqueueing it. The SSE terminal error payload includes the same code, safe message, retry state, and safe authoritative identity fields as JSON. No raw exception object or exception string crosses the queue/projection boundary.

The existing frontend `isTerminalChatResponsePayload` already accepts failed Chat responses and `streamReducer` already distinguishes `retry_state=in_progress`; no public schema or frontend architecture change is expected. Additive event fields are only proposed if the current `ChatResponse` fields cannot carry the required projection.

### 4. Confirm preserves domain errors and sanitizes only unexpected failures

The confirm route keeps existing authentication/validation behavior. `PendingActionServiceError` and known typed tool outcomes remain machine-readable, including `expected_version_required`, `version_conflict`, `unsupported_action_schema`, ownership/not-found, expiry, terminal/replay, inventory, Cart, and preference failures.

Unexpected exceptions are caught at the public boundary after the confirmation service has rolled back its caller-owned session. The route logs a safe internal event and returns a bounded `runtime.internal_error` failed Chat response, not `str(exc)`. If rollback cannot be guaranteed by the existing service boundary, the smallest explicit rollback seam is added there; no global transaction middleware is introduced.

### 5. Internal logging retains diagnostics without becoming a data dump

Reuse `app.core.logging.log_event` and its existing sanitization. Public projection logs stable `error_code`, exception class, bounded request/run/action identifiers, and a safe message. Traceback diagnostics remain available through the existing logger configuration, but exception text/payload is sanitized and truncated before structured fields; secrets, tokens, provider payloads, and unnecessary PII are never added to the log event. No new platform or exporter is introduced.

### 6. Public debug is bounded by the same policy

`include_debug=true` is an additive public projection, not an internal diagnostics escape hatch. Existing safe debug fields and opaque correlation selectors may remain, but exception text, traceback, SQL/driver detail, filesystem paths, credentials/tokens, provider payloads, and unnecessary PII are excluded from normal response fields and public debug metadata. Full exception detail remains available only through the existing sanitized internal logging path.

### 7. Error classification is not status flattening

Expected client/auth errors retain their current HTTP/status semantics. Expected domain/runtime failures retain stable code and terminal/recoverable behavior. Unexpected internal errors use a generic safe code/message. HTTP transport status may remain the current Chat compatibility behavior for runtime results; the policy must not turn every known failure into 500 or turn a recoverable state into terminal failure.

### 8. Preserve existing contracts

The change must not modify RAG failed/partial semantics, canonical Cart typed errors, `expected_version`/`version_conflict`, Order/payment safety, HITL `unsupported_action_schema`, or Chat retry authoritative Run/replay semantics. Error mapping is a projection hardening layer only.

## Alternatives considered

### A. Add a global FastAPI exception handler

Rejected for this Change. It would affect unrelated APIs and could flatten domain-specific errors. Chat boundaries need a narrow policy while existing API-specific handlers remain authoritative.

### B. Sanitize only in the frontend

Rejected. Raw data would still cross the public boundary and non-browser clients would remain exposed.

### C. Return `str(exc)` only in debug mode

Rejected. Debug flags are client-controlled/public and do not make SQL/provider/internal details safe.

### D. Convert every error to HTTP 500

Rejected. It would break typed domain errors, idempotency recovery, and frontend retry semantics.

## Risks / Trade-offs

- **Known code lacks a message mapping** → use a bounded generic safe message while preserving the code.
- **Unexpected error occurs after an authoritative side effect** → rely on persisted Run/idempotency state; do not invent a second execution or claim terminal success.
- **SSE client compatibility** → prefer existing `ChatResponse` terminal payload; add only additive fields if validation proves necessary.
- **Internal diagnostics become over-redacted** → retain exception class, correlation/request/run/action identifiers, and controlled traceback logging without payload dumps.

## Migration Plan

1. Add static projection tests and inventory the current known-code allowlist.
2. Implement the narrow public mapping seam and route JSON/SSE/confirm through it.
3. Add rollback, parity, in-progress, domain-code, and unexpected-exception tests.
4. Run frontend compatibility tests; regenerate OpenAPI only if an additive public schema field is actually introduced.
5. Run focused and full non-integration backend validation. PostgreSQL is not initially required because this Change does not alter transaction/concurrency logic; add an isolated PG test only if rollback/claim behavior cannot be proven locally.

Rollback is application-level: disable the projection seam only through a reviewed deployment decision. Do not restore raw exception interpolation.

## Open Questions

None block the selected design. The exact allowlisted code-to-message table can be finalized from the current runtime/action code set during implementation without changing the public classification or scope.
