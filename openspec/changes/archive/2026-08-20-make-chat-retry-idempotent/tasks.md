## 1. Baseline and contract audit

- [x] 1.1 Record Apply-before `git status --short`/`git diff --stat`, identify dirty overlap, and confirm the exact Chat, SSE, Harness, runtime repository, PendingAction, frontend, and test files in scope.
- [x] 1.2 Capture current JSON/SSE public response shapes, runtime status/error codes, request-hash behavior, existing unique constraints, and current disconnect/cancellation behavior in deterministic tests or fixtures.

## 2. Frontend logical-message identity

- [x] 2.1 Extend the Chat message state with a per-logical-message idempotency key and interrupted/terminal retry state without adding a chat-history store.
- [x] 2.2 Change `chat` and `streamChat` API calls to accept and send an explicit key; remove per-fetch key generation from the stream retry path.
- [x] 2.3 Route automatic/network retry and manual retry of the same interrupted message through the stored key, preserving the message's thread/user scope.
- [x] 2.4 Ensure edited messages, intentional duplicate text submissions, new threads, and user switches create new logical identities; terminal results clear only the matching retry marker.
- [x] 2.5 Change browser Stop/AbortController presentation to transport detach wording and preserve retry identity; do not add an authoritative cancellation API.

## 3. Backend authoritative idempotency claim

- [x] 3.1 Reuse the existing canonical runtime request hash and owner/operation/key scope; confirm the hash includes message/thread semantics and excludes only volatile request identity fields.
- [x] 3.2 Implement an atomic claim boundary that creates the `started` idempotency record and authoritative `AgentRun` identity together, using the existing database uniqueness arbitration.
- [x] 3.3 Resolve concurrent same-key claim conflicts by reading the winning record and returning typed in-progress/terminal state; never invoke a second executor after a claim race.
- [x] 3.4 Preserve typed same-key hash conflict behavior and deterministic replay for completed, confirmation-required, failed, and cancelled records, including original run and PendingAction identity.
- [x] 3.5 Remove fail-open behavior from idempotency start/finish persistence: claim or result persistence failure SHALL produce bounded typed failure and SHALL not fall through to a new Agent execution.
- [x] 3.6 Add the minimal public typed retry projection for in-progress recovery (`retry_state`, runtime error code, and authoritative winner run ID) while preserving existing Chat status compatibility.

## 4. Disconnect, recovery, and PendingAction boundary

- [x] 4.1 Adjust the Chat SSE disconnect boundary so transport loss does not authorize a replacement execution and the authoritative Run can reach its persisted terminal state under existing budgets.
- [x] 4.2 Persist/recover the authoritative PendingAction relationship sufficiently for a same-key retry after preparation to return the original action ID/version/preview without preparing a second action.
- [x] 4.3 Keep JSON and SSE on the same runtime idempotency contract, preserve existing public Chat statuses, and leave `/api/chat/confirm` and canonical PendingAction confirmation semantics unchanged.
- [x] 4.4 Split delivery-detached handling from runtime cancellation, stop enqueueing to abandoned SSE queues, safely settle detached producer tasks, consume task exceptions, and release admission without a global background-job framework.

## 5. Regression and integration tests

- [x] 5.1 Add runtime/repository unit tests for no-record claim, same-key same-hash replay, hash conflict, running state, each terminal state, and persistence failure fail-closed behavior.
- [x] 5.2 Add API JSON/SSE tests for explicit key forwarding, same-key duplicate behavior, concurrent duplicate behavior, terminal recovery, and unchanged public response compatibility.
- [x] 5.3 Add disconnect tests proving transport loss before terminal result does not create a replacement Run and that an authoritative run can still be recovered by same-key retry.
- [x] 5.4 Add PendingAction/write-handoff tests proving disconnect after preparation recovers one action ID/version and never creates P2 or auto-confirms.
- [x] 5.5 Add PostgreSQL integration tests for concurrent same-key claim, unique conflict arbitration, running duplicate, completed replay, request-hash conflict, and rollback/persistence failure boundaries when PostgreSQL is the authority.
- [x] 5.6 Add frontend Vitest coverage for one key per logical message, network/manual retry reuse, new-key behavior for edited/intentionally repeated messages, user/thread isolation, terminal cleanup, and unknown-outcome UI.
- [x] 5.7 Add or adjust existing runtime/SSE/frontend regression tests without weakening backend-regression-stability, commerce-cart, or order-expiration coverage.
- [x] 5.8 Add tests for browser Stop transport-detach semantics, in-progress public projection/winner run ID, detached queue behavior, and preservation of retry identity.

## 6. Final validation and scope review

- [x] 6.1 Run focused backend/runtime/API tests with LangSmith, Redis, RocketMQ, PostgreSQL integration, and external APIs disabled; record zero failures/errors.
- [x] 6.2 Run the full non-integration backend suite with writable isolated basetemp plus relevant frontend Vitest, lint, typecheck, and typecheck:e2e; do not run live external E2E.
- [x] 6.3 Run strict OpenSpec validation, review for no event-cursor/platform/auth/payment/PendingAction-confirmation scope creep, and document any required PostgreSQL result separately.
