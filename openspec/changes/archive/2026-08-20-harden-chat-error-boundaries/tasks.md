## 1. Audit and boundary inventory

- [x] 1.1 Record the Apply baseline and preserve all pre-existing dirty files; do not include them as this change's implementation.
- [x] 1.2 Add a focused inventory of Chat JSON, Chat SSE, Chat confirm, PendingAction, runtime, Tool Gateway, write-handoff, and unexpected exception projections.
- [x] 1.3 Confirm the existing five main capabilities and list their error/recovery contracts that must remain unchanged.

## 2. Public error policy

- [x] 2.1 Define the narrow Chat-boundary classification for client/auth, typed domain/runtime, recoverable runtime, and unexpected internal failures.
- [x] 2.2 Define the bounded code-to-message mapping and generic `runtime.internal_error` fallback without exposing raw exception text.
- [x] 2.3 Project `RunResult.error` safely when metadata does not already carry its stable runtime error code or message.
- [x] 2.4 Preserve authoritative Run identity and `retry_state=in_progress` for idempotency recovery results.

## 3. JSON and confirmation boundaries

- [x] 3.1 Route unexpected `/api/chat` execution exceptions through the bounded public policy while retaining existing compatibility status semantics.
- [x] 3.2 Preserve typed `/api/chat/confirm` outcomes for expected-version, schema, owner/thread, expiry, terminal, inventory, Cart, and preference failures.
- [x] 3.3 Ensure unexpected confirmation exceptions roll back at the existing service boundary, are logged safely, and never use `str(exc)` in public output.
- [x] 3.4 Verify existing validation and authorization failures retain their established status and machine-readable semantics.

## 4. SSE boundary and transport parity

- [x] 4.1 Convert stream-side unexpected exceptions before queueing so no raw exception object or raw exception string crosses the stream boundary.
- [x] 4.2 Emit a typed terminal SSE error projection with the same safe code, message semantics, and retry classification as JSON.
- [x] 4.3 Preserve in-progress/recoverable runtime projection in SSE and prevent sanitization from turning it into terminal failure.
- [x] 4.4 Keep delivery-detach/runtime-cancellation separation and avoid changing SSE retry/idempotency behavior outside error projection.

## 5. Internal diagnostics

- [x] 5.1 Reuse the existing structured logging and sanitization path for public-boundary failures.
- [x] 5.2 Retain bounded exception class, stable internal code, traceback diagnostics, and safe request/run/thread/action correlation fields internally.
- [x] 5.3 Add static/fixture checks proving secrets, tokens, provider payloads, SQL/driver details, paths, and unnecessary PII do not enter public error fields or structured error metadata.
- [x] 5.4 Apply the same bounded projection policy to `include_debug=true`; retain approved safe debug fields but exclude raw exception and traceback details from public debug.

## 6. Behavioral regression tests

- [x] 6.1 Test known typed runtime/domain codes and bounded messages across JSON and SSE.
- [x] 6.2 Test unexpected JSON execution exceptions produce safe public output and internal diagnostics.
- [x] 6.3 Test unexpected SSE execution exceptions produce safe typed terminal output with no raw exception leakage.
- [x] 6.4 Test confirmation expected-version, version-conflict, unsupported-schema, owner/thread, expiry, terminal, inventory, Cart, and preference semantics remain typed.
- [x] 6.5 Test unexpected confirmation failure rolls back and leaves no partial mutation.
- [x] 6.6 Test `runtime.idempotency_in_progress`, completed replay, failed replay, and cancelled replay retain their existing terminal/recoverable semantics and authoritative Run identity.
- [x] 6.7 Test Tool Gateway, write-handoff, RAG, and canonical Cart failures remain typed and do not become false success or legacy fallback.
- [x] 6.8 Test internal logging retains safe diagnostic context while excluding sensitive values and raw public exception details.
- [x] 6.9 Run relevant frontend mocked Chat tests and make no frontend change unless the current public schema cannot carry the required fields.
- [x] 6.10 Test `include_debug=true` for JSON, SSE, and confirmation responses to prove public debug cannot leak raw exception or internal diagnostic detail.

## 7. Validation and readiness

- [x] 7.1 Run focused backend/runtime/API tests with LangSmith, Redis, RocketMQ, PostgreSQL integration, and external APIs disabled.
- [x] 7.2 Run the full non-integration backend regression suite using a writable isolated basetemp.
- [x] 7.3 Run applicable frontend regression, lint, and type checks only if the public contract or existing consumer compatibility requires it.
- [x] 7.4 Complete readiness review for raw leaks, typed-code preservation, JSON/SSE parity, in-progress recovery, safe logging, and scope compliance.
- [x] 7.5 Run strict OpenSpec validation for this change and all main specs; record remaining uncertainties and Ready For Apply status.
