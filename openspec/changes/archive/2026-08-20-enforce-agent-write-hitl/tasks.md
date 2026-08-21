## 1. Baseline and inventory

- [x] 1.1 Record Apply-before `git status --short`/`git diff --stat` and preserve existing dirty files.
- [x] 1.2 Add a checked-in inventory/test fixture covering active Single Agent tools, Multi-Agent allowlists, write-handoff tools, confirmation tools, and known direct repository writers.
- [x] 1.3 Confirm the implementation file set and verify that backend-regression-stability, commerce-cart, order-expiration, and chat-retry-idempotency contracts remain out of scope.

## 2. Agent/tool write boundary

- [x] 2.1 Define the read-only, write-intent preparation, deterministic confirmation, and system-owned runtime metadata classifications in the existing Tool Gateway/policy vocabulary.
- [x] 2.2 Remove `add_user_preference` and any other direct preference domain writer from the active Single Agent tool set.
- [x] 2.3 Route recognized Single Agent preference-write intent through the shared deterministic write-handoff preparation boundary.
- [x] 2.4 Ensure Multi-Agent Preference Agent remains read-only and Multi-Agent write intent continues through `write_handoff`.
- [x] 2.5 Prevent `clear_user_preferences`, legacy `clear_cart_items`, legacy Cart writers, and repository-level domain writers from being active Agent capabilities or fallback handlers.

## 3. Canonical preference preparation

- [x] 3.1 Define the versioned canonical `save_preference` PendingAction payload and typed validation model without changing the public action type.
- [x] 3.2 Implement or expose the minimal canonical preference PendingAction preparation service with owner/thread, risk, expiry, version, preview, and schema metadata.
- [x] 3.3 Make `tools.cart.prepare_save_preference` delegate to the canonical preparation service while preserving the existing tool name and typed `confirmation_required` result.
- [x] 3.4 Ensure preparation never calls `UserPreference` repository writes and rolls back on preparation failure.
- [x] 3.5 Preserve existing Action Registry and frontend editable-field compatibility for `save_preference`.

## 4. Deterministic confirmation boundary

- [x] 4.1 Route `confirm_save_preference` through the canonical deterministic confirmation service used by `/api/chat/confirm`.
- [x] 4.2 Validate persisted payload, explicit typed edits, allowed preference enum, bounded value, action status, expiry, owner, thread, and client-held expected version before mutation.
- [x] 4.3 Commit the preference mutation and PendingAction terminal resolution in one caller-owned transaction with rollback on either failure.
- [x] 4.4 Prove cancel/reject, expired, stale-version, owner/thread mismatch, invalid payload, and unsupported-schema paths perform no domain write.
- [x] 4.5 Prove successful confirmation and same-transition replay produce one logical preference mutation and a stable resolution result without LLM involvement.

## 5. Legacy and existing flow compatibility

- [x] 5.1 Make historical non-canonical preference PendingActions fail closed on confirm with `unsupported_action_schema` or the existing equivalent and require re-preparation.
- [x] 5.2 Preserve safe read/preview/cancel behavior for legacy actions where current API semantics support it, without silent migration or dynamic confirm-time conversion.
- [x] 5.3 Verify canonical ShopMind Cart preparation/confirmation remains the only formal Cart mutation path and retains existing expected-version, owner, inventory, price, and replay behavior.

## 6. Behavioral and static tests

- [x] 6.1 Add a static/tool-set test proving no active Agent can reach `add_user_preference`, `clear_user_preferences`, `clear_cart_items`, or legacy direct Cart writers.
- [x] 6.2 Add preference-intent tests for Single Agent and Multi-Agent proving preparation returns `confirmation_required` and leaves `UserPreference` unchanged.
- [x] 6.3 Add canonical PendingAction schema, owner/thread, preview, expiry, version, and editable-field tests.
- [x] 6.4 Add successful confirmation tests proving exactly one preference write and action resolution in one transaction.
- [x] 6.5 Add cancel/reject/expired/stale-version/owner-mismatch/invalid-schema tests proving no preference mutation.
- [x] 6.6 Add confirmation replay and persistence rollback tests proving no duplicate preference write.
- [x] 6.7 Add Chat JSON/SSE and chat-retry recovery tests proving the same PendingAction is recovered without a second preparation or auto-confirm.
- [x] 6.8 Add canonical Cart regression tests proving no change to the existing Cart HITL and no legacy fallback/dual write.
- [x] 6.9 Add PostgreSQL integration coverage only for transaction/concurrency behavior that SQLite cannot establish, using an isolated database/schema if required.

## 7. Final validation and readiness

- [x] 7.1 Run directly affected backend/Agent/API tests with LangSmith, Redis, RocketMQ, and external APIs disabled.
- [x] 7.2 Run the full non-integration backend regression suite with writable isolated basetemp and relevant frontend mocked tests/lint/typecheck if the public confirmation contract changes.
- [x] 7.3 Re-run the complete Agent write inventory and readiness review: no active direct write, read-only tools remain direct, confirmation is deterministic, legacy actions fail safely, and existing main capabilities are preserved.
- [x] 7.4 Run `openspec validate enforce-agent-write-hitl --type change --strict --no-interactive` and `openspec validate --specs --strict --no-interactive`, then document final scope and uncertainties.
