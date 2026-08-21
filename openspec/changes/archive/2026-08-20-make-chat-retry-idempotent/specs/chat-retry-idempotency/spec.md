## Purpose

This capability gives each logical Chat message one authoritative retry identity so network retries and duplicate requests recover the same runtime result without creating duplicate Agent executions or PendingActions.

## ADDED Requirements

### Requirement: Each logical Chat message SHALL have one stable retry identity

The first-party Chat client SHALL create one idempotency key when a new logical user message is created and SHALL reuse that key for transport retries until the authoritative result is terminal. A new message, an edited message, an intentionally repeated text submission, a new thread, or a different user identity SHALL create a new logical identity even when the visible message text is equal.

#### Scenario: New logical message receives a stable key

- **WHEN** the user submits a new Chat message
- **THEN** the client SHALL create one idempotency key associated with that logical message before the first JSON or SSE request

#### Scenario: Network retry reuses the original key

- **WHEN** the first request fails before an authoritative terminal result is received and the user retries that same logical message
- **THEN** the retry SHALL send the original idempotency key and SHALL not generate a replacement key

#### Scenario: Same text intentionally sent again is a new message

- **WHEN** the user submits the same visible text as a separate intentional message
- **THEN** the client SHALL create a new logical message and a new idempotency key rather than text-deduplicating it

#### Scenario: User or thread switching does not reuse a key

- **WHEN** the active user or Chat thread changes
- **THEN** pending retry identity from the previous user/thread SHALL not be reused for the new logical message

### Requirement: Backend Chat idempotency SHALL be authoritative and hash-bound

The backend SHALL scope Chat idempotency by effective owner scope, Chat operation, thread identity, and idempotency key, and SHALL compare a canonical request hash before deduplicating. The backend SHALL be the authority for request-hash computation and conflict classification.

#### Scenario: Same key and same request are deduplicated

- **WHEN** a request uses the same owner/operation/key and the same canonical request body as an existing Chat execution
- **THEN** the backend SHALL reuse or recover that execution and SHALL not start a second Agent Run

#### Scenario: Same key with a different body conflicts

- **WHEN** a request uses an existing owner/operation/key with a different canonical message, thread, or request body
- **THEN** the backend SHALL return the existing typed idempotency conflict and SHALL not execute the Agent

#### Scenario: Concurrent duplicate requests have one winner

- **WHEN** two requests with the same owner, operation, key, and request hash arrive concurrently
- **THEN** exactly one request SHALL claim the authoritative execution and the other SHALL observe that execution without starting a second Run

#### Scenario: Different keys are independent logical messages

- **WHEN** two requests have different idempotency keys even if their text is equal
- **THEN** they SHALL be treated as separate logical executions subject to normal runtime admission and safety rules

### Requirement: Same-key Run state semantics SHALL be deterministic

One idempotency key SHALL map to one logical execution identity across `running`, `completed`, `confirmation_required`, `failed`, and `cancelled` states. A same-key retry SHALL never silently restart a terminal execution; a user-requested new attempt SHALL use a new key.

#### Scenario: Retry while the authoritative Run is running

- **WHEN** a same-key retry arrives while the original Run is still running
- **THEN** the backend SHALL return a machine-readable in-progress outcome with the authoritative Run identity and SHALL not execute a second Run

#### Scenario: Running duplicate exposes authoritative recovery identity

- **WHEN** a same-key/same-hash retry arrives while the winner Run is still running
- **THEN** the response SHALL expose `runtime.idempotency_in_progress`, `retry_state=in_progress`, and the winner `authoritative_run_id`; the frontend SHALL retain the same logical-message key and SHALL not treat the outcome as terminal failure

#### Scenario: Retry after a completed Run

- **WHEN** a same-key retry arrives after the authoritative Run completed
- **THEN** the backend SHALL return the persisted authoritative result and original Run identity without invoking the Agent again

#### Scenario: Retry after confirmation-required preparation

- **WHEN** a same-key retry arrives after the authoritative Run created a confirmation-required result
- **THEN** the backend SHALL return the same PendingAction identity/result and SHALL not prepare another action

#### Scenario: Retry after failed or cancelled terminal Run

- **WHEN** a same-key retry arrives after the authoritative Run is terminal `failed` or `cancelled`
- **THEN** the backend SHALL replay that same terminal outcome, and a new execution SHALL require a new logical message and key

### Requirement: SSE disconnect SHALL not create a replacement execution

Loss of the HTTP/SSE connection SHALL be treated as transport loss for a request with an idempotency key. The authoritative Run SHALL be allowed to reach a persisted terminal state under existing runtime budgets/cancellation boundaries, and a retry SHALL recover its current/terminal state instead of launching a replacement execution.

#### Scenario: Disconnect before terminal result

- **WHEN** the client disconnects before receiving `run.result`
- **THEN** a later retry with the same key SHALL observe the original Run as in-progress or terminal and SHALL not create a second Run

#### Scenario: Disconnect after PendingAction preparation

- **WHEN** the authoritative Run has created PendingAction P and the client disconnects before receiving the terminal result
- **THEN** a same-key retry SHALL recover P and its existing version/preview through the authoritative result or existing scoped read path, SHALL not create P2, and SHALL not auto-confirm P

#### Scenario: Manual stream stop is transport detach

- **WHEN** the first-party client intentionally aborts the current SSE transport
- **THEN** current delivery SHALL stop, the authoritative Run identity SHALL remain authoritative, the logical-message retry identity SHALL remain recoverable, no second execution SHALL be created, and the UI SHALL NOT represent transport detach as authoritative Agent cancellation

#### Scenario: Explicit action confirmation remains separate

- **WHEN** a recovered Chat result contains a PendingAction and the user has not confirmed it
- **THEN** retry recovery SHALL not confirm, cancel, edit, or otherwise mutate the PendingAction

### Requirement: Frontend retry state SHALL end only on authoritative terminal outcome

The client SHALL retain the original key while a logical message is interrupted or has an unknown transport outcome. It SHALL clear the pending-retry marker only after a valid terminal Chat result or typed terminal failure has been received, without clearing or recreating unrelated user/thread state.

#### Scenario: Network failure preserves retry identity

- **WHEN** a request fails before a valid terminal response
- **THEN** the logical message SHALL remain retryable with its original key and SHALL not immediately create a new key

#### Scenario: Terminal result ends the retry lifecycle

- **WHEN** a valid completed, confirmation-required, failed, or cancelled result is received for the logical message
- **THEN** the client SHALL stop treating that message as an interrupted pending retry while preserving any returned PendingAction data for the existing confirmation UI

#### Scenario: Page refresh is not falsely advertised as recovery

- **WHEN** the browser is refreshed before a terminal result
- **THEN** this capability SHALL not promise automatic recovery from React-memory-only state; page-refresh recovery SHALL remain an explicitly separate future capability

### Requirement: Idempotency persistence failure SHALL fail closed

The backend SHALL not invoke Agent execution when it cannot atomically establish or read the authoritative idempotency claim. A database/record failure SHALL produce a bounded typed runtime failure and SHALL not be swallowed into a second execution path.

#### Scenario: Initial claim storage fails

- **WHEN** the idempotency claim or its authoritative Run record cannot be committed
- **THEN** the request SHALL fail closed before Agent execution and SHALL not create a second fallback Run

#### Scenario: Terminal result persistence fails

- **WHEN** a Run result cannot update its authoritative runtime/idempotency record
- **THEN** the system SHALL report bounded persistence failure and SHALL not allow a same-key retry to start an unverified second execution

### Requirement: Retry recovery SHALL use current authoritative state without requiring full event replay

JSON and SSE Chat requests SHALL share the same idempotency and terminal projection contract. Same-key recovery SHALL return the persisted current/terminal result and may emit a replay marker, but this capability SHALL not require replaying every historical intermediate SSE event or implementing a sequence cursor.

#### Scenario: JSON and SSE share one execution identity

- **WHEN** JSON and SSE requests use the same owner/thread/key/hash
- **THEN** they SHALL resolve the same authoritative Run rather than creating transport-specific executions

#### Scenario: Terminal recovery does not require intermediate event replay

- **WHEN** a client retries after missing intermediate SSE events
- **THEN** it SHALL receive the current/terminal authoritative result, while exact historical progress-event replay remains outside this capability

#### Scenario: Existing persisted events remain inspectable

- **WHEN** an owner uses the existing runtime inspection boundary for a recovered Run
- **THEN** persisted client events MAY be inspected under existing ownership/retention rules without changing the public Chat retry contract

### Requirement: Retry idempotency SHALL preserve existing commerce and runtime safety contracts

The retry boundary SHALL not weaken existing Chat thread/session isolation, RAG failure semantics, canonical Cart confirmation, PendingAction owner/thread/version checks, or Order expiration/payment safety. It SHALL provide deterministic local and database-backed regression protection.

#### Scenario: Recovered PendingAction keeps canonical confirmation semantics

- **WHEN** a same-key retry recovers an add-to-cart PendingAction
- **THEN** the existing owner/thread/expiry/expected-version confirmation boundary SHALL remain authoritative and no automatic Cart mutation SHALL occur

#### Scenario: Existing runtime thread/session boundary remains intact

- **WHEN** Chat retry/deduplication is exercised through JSON or SSE
- **THEN** synchronous Agent work SHALL retain its existing thread/session ownership behavior and SHALL not introduce a shared live Session across execution contexts

#### Scenario: Regression validation covers duplicate execution prevention

- **WHEN** focused backend/runtime/API/frontend tests and the full non-integration backend suite are run with external services disabled, plus isolated PostgreSQL claim tests when required
- **THEN** the suites SHALL report zero failures and zero errors for the relevant capability without changing the three existing main capability contracts
