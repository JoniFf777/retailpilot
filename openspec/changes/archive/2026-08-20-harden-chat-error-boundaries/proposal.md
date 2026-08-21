## Why

ShopMind has typed runtime, domain, action, and payment contracts, but the public Chat boundaries do not consistently use them. `app/api/routes/chat_confirm.py:42-49` currently interpolates `str(exc)` into a public `ChatResponse`, while `app/api/routes/chat_stream.py:140-157` turns an exception object into a generic SSE failure without the underlying stable error code. JSON Chat also lets unexpected exceptions escape the route, and `build_chat_response` does not consistently project `RunResult.error` into `runtime_error_code` and a safe message.

This creates two risks: internal SQL/driver/provider/Python details can cross the public boundary, and the same underlying typed failure can have different JSON/SSE/retry semantics. The change is needed now because Chat retry, HITL, Cart, and RAG contracts already depend on machine-readable status and error identity.

## What Changes

- Establish one bounded public Chat error policy for JSON, POST-SSE, and `/api/chat/confirm`.
- Preserve known typed domain/runtime codes and map them to safe bounded public messages.
- Map unexpected exceptions to a generic public internal-error code/message while retaining safe internal structured logging and traceback diagnostics.
- Project `RunResult.error.code`, safe message, `retry_state`, and authoritative Run identity consistently where the existing contract permits it.
- Make SSE exception/error events carry the same stable code and terminal/recoverable semantics as JSON without exposing raw exception text.
- Preserve `runtime.idempotency_in_progress` as a nonterminal recoverable state and never downgrade it to an ordinary terminal failure.
- Preserve rollback and typed PendingAction/Cart failures, including `expected_version_required`, `version_conflict`, `unsupported_action_schema`, expiry, ownership, inventory, and preference errors.
- Keep frontend changes minimal; reuse existing `ChatResponse` retry fields and current action-error parsing unless a strictly additive field is proven necessary.
- Add focused boundary, parity, rollback, logging, and regression tests without creating a global generic exception framework.

## Capabilities

### New Capabilities

- `chat-error-boundaries`: Defines safe, typed, parity-preserving public error projection for Chat JSON/SSE/confirm boundaries.

### Modified Capabilities

- None. `backend-regression-stability`, `commerce-cart`, `order-expiration`, `chat-retry-idempotency`, and `agent-write-hitl` remain independent and unchanged by this proposal.

## Impact

Expected impact is limited to Chat routes/projection, a small runtime/public-error mapping seam, existing safe logging helpers, Tool Gateway/PendingAction error adapters where required, and directly related backend/frontend tests. No schema redesign, migration, external service, authentication change, or new observability platform is planned.

## Acceptance Criteria

- No public Chat JSON/SSE/confirm response uses raw `str(exc)`, `repr(exc)`, SQL/driver details, filesystem paths, Python internals, provider payloads, secrets, or tokens.
- `include_debug=true` remains safe: public debug fields contain only approved bounded/correlation data and never raw exception or traceback detail.
- Known typed errors retain stable machine-readable codes and safe bounded messages.
- Unexpected exceptions produce a generic safe public error while internal logs retain bounded diagnostic class/context and traceback capability without sensitive payloads.
- JSON and SSE preserve equivalent code and terminal/recoverable semantics for the same underlying typed failure.
- `runtime.idempotency_in_progress` remains nonterminal, recoverable, and tied to the authoritative Run identity.
- Confirm rollback and existing Cart/HITL/RAG/Order/Chat retry contracts remain unchanged.
