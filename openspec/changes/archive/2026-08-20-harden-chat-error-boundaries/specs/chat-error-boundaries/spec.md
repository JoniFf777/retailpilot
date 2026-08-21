## Purpose

This capability defines a bounded, typed public error boundary for ShopMind Chat JSON, SSE, and confirmation responses while preserving domain, runtime recovery, and internal diagnostic semantics.

## ADDED Requirements

### Requirement: Public Chat errors SHALL be classified and typed

The public Chat boundary SHALL distinguish expected client/authentication errors, expected domain/runtime failures, recoverable runtime states, and unexpected internal exceptions. Known stable codes SHALL be preserved, while public messages SHALL be selected from bounded safe messages rather than raw exception text.

#### Scenario: Known domain failure preserves its stable code

- **WHEN** a Chat or confirmation operation produces a known typed domain failure
- **THEN** the public response SHALL preserve its machine-readable code and expose only its bounded safe message

#### Scenario: Validation and authorization failures preserve their boundary semantics

- **WHEN** request validation, authentication, owner, or thread scope checks reject a request
- **THEN** the API SHALL retain the existing appropriate status and typed semantics rather than converting the failure to an unrelated internal error

#### Scenario: Unknown failure uses a bounded generic classification

- **WHEN** the public boundary receives an exception or error code that is not in the approved typed mapping
- **THEN** it SHALL expose a stable generic internal-error code and bounded message without exposing the original exception text

### Requirement: Unexpected exceptions SHALL never cross the public Chat boundary

Unexpected Python, database, driver, filesystem, provider, or adapter exceptions SHALL be converted before they become JSON fields, SSE payloads, queued stream values, or user-facing confirmation text. The original exception SHALL remain available only to safe internal diagnostics.

#### Scenario: JSON execution exception is safely projected

- **WHEN** synchronous Agent execution raises an unexpected exception while serving Chat JSON
- **THEN** the response SHALL contain a bounded machine-readable internal error and SHALL not contain the exception text, traceback, SQL, driver detail, path, or provider payload

#### Scenario: SSE execution exception is safely projected

- **WHEN** Agent execution raises an unexpected exception during a Chat stream
- **THEN** the stream SHALL emit a safe typed terminal error representation and SHALL never enqueue or serialize the raw exception object or its text

#### Scenario: Confirmation exception is safely projected

- **WHEN** `/api/chat/confirm` encounters an unexpected exception after entering confirmation handling
- **THEN** the service boundary SHALL roll back as required, log safe diagnostics, and return a bounded internal error rather than interpolating the exception into the public answer

### Requirement: JSON and SSE error projections SHALL be semantically aligned

For the same underlying typed runtime or domain failure, JSON and SSE SHALL preserve the same stable error code, safe message semantics, and terminal or recoverable classification. Transport-specific envelopes MAY differ, but transport choice SHALL not change error meaning.

#### Scenario: Typed failure has parity across transports

- **WHEN** the same typed runtime or domain failure is returned through JSON and SSE
- **THEN** both projections SHALL expose the same stable code and equivalent safe message and lifecycle classification

#### Scenario: Persisted RunError is included in ChatResponse

- **WHEN** a completed authoritative RunResult contains a typed error that is not duplicated in metadata
- **THEN** ChatResponse construction SHALL project the safe error code and message without changing the Run state or persistence semantics

#### Scenario: Stream failure does not degrade into an untyped error

- **WHEN** a stream-side failure is converted into a terminal error event
- **THEN** the event SHALL carry the same typed public error fields used by the corresponding JSON projection and SHALL not fall back to a raw string-only error

### Requirement: Confirmation and PendingAction errors SHALL preserve existing domain contracts

Chat confirmation SHALL retain machine-readable semantics for expected-version requirements, version conflicts, unsupported action schemas, ownership/thread mismatch, expiry, terminal/replay states, inventory failures, Cart failures, and preference failures. Error sanitization SHALL not bypass or reinterpret deterministic confirmation validation.

#### Scenario: Version and schema errors remain typed

- **WHEN** confirmation is missing the required expected version, supplies a stale version, or presents an unsupported action schema
- **THEN** the response SHALL preserve the existing corresponding typed code and SHALL perform no domain mutation

#### Scenario: Scope and lifecycle failures remain non-success

- **WHEN** a PendingAction belongs to another owner/thread or is expired, cancelled, or already terminal
- **THEN** confirmation SHALL return the existing safe typed outcome, SHALL not claim a new mutation, and SHALL not leak persistence details

#### Scenario: Confirmation domain failure rolls back

- **WHEN** a deterministic confirmation service fails during a preference or Cart domain mutation
- **THEN** the caller-owned transaction SHALL roll back and the public response SHALL retain the typed domain failure without exposing internal exception details

### Requirement: Runtime retry and recovery semantics SHALL survive error sanitization

The public error boundary SHALL preserve authoritative Chat idempotency and recovery semantics. In-progress execution SHALL remain nonterminal and recoverable; terminal replay SHALL remain terminal; sanitization SHALL not create a replacement Run or hide the authoritative Run identity.

#### Scenario: Idempotency in-progress remains recoverable

- **WHEN** a same-key request observes an authoritative Run that is still running
- **THEN** the response SHALL preserve `runtime.idempotency_in_progress`, `retry_state=in_progress`, and the authoritative Run identity, and SHALL not classify it as terminal failure

#### Scenario: Terminal replay remains terminal

- **WHEN** a same-key request replays a completed, confirmation-required, failed, or cancelled authoritative Run
- **THEN** it SHALL return the persisted terminal semantics and authoritative identity without invoking a second execution

#### Scenario: Persistence failure remains fail-closed

- **WHEN** idempotency or runtime persistence cannot establish or expose authoritative ownership
- **THEN** the public result SHALL use the existing bounded failure or recovery semantics and SHALL not permit duplicate Agent execution

### Requirement: Tool and write-handoff failures SHALL remain bounded and typed

Failures from Tool Gateway adapters, RAG/tool execution, Cart write handoff, and preference HITL preparation or confirmation SHALL retain their existing stable typed semantics when known. Unknown adapter failures SHALL be classified as safe internal failures at the Chat boundary.

#### Scenario: Known Tool Gateway failure is preserved

- **WHEN** a Tool Gateway returns a known execution, timeout, policy, or unavailable failure
- **THEN** Chat JSON/SSE projection SHALL preserve the stable tool/runtime code and bounded message without exposing adapter details

#### Scenario: Write-handoff domain failure is not reported as success

- **WHEN** Cart or preference write-handoff preparation returns a typed failure or confirmation-required outcome
- **THEN** the public response SHALL preserve that outcome and SHALL not convert failure into completed success or fall back to a legacy writer

#### Scenario: RAG failure semantics remain intact

- **WHEN** RAG execution fails, is partial, or is intentionally unavailable
- **THEN** the existing failed, partial, or bounded degraded semantics SHALL remain distinguishable and SHALL not be flattened by public error sanitization

### Requirement: Internal logging SHALL preserve diagnostics safely

Unexpected public-boundary failures SHALL produce structured internal diagnostics sufficient for investigation while excluding secrets, tokens, provider payloads, full sensitive request payloads, and unnecessary personal data.

#### Scenario: Unexpected exception creates bounded diagnostic context

- **WHEN** an unexpected Chat, SSE, or confirmation exception is sanitized
- **THEN** internal logging SHALL retain a stable internal code, exception class, and bounded request/run/thread/action identifiers when available

#### Scenario: Traceback detail stays internal

- **WHEN** diagnostic logging records traceback or exception detail
- **THEN** that detail SHALL remain in internal logs and SHALL never be copied into a public ChatResponse, SSE event, or confirmation answer

#### Scenario: Sensitive values are excluded

- **WHEN** a public-boundary failure is logged
- **THEN** logging SHALL use existing sanitization/redaction and SHALL exclude credentials, auth tokens, provider secrets/payloads, and unnecessary PII

#### Scenario: Public debug projection remains safe

- **WHEN** a Chat or confirmation request sets `include_debug=true` and an expected or unexpected failure occurs
- **THEN** public debug fields SHALL contain only approved bounded/correlation data, SHALL not contain raw exception text, traceback, SQL/driver detail, filesystem paths, secrets, tokens, provider payloads, or unnecessary PII, and SHALL not bypass the public error policy

### Requirement: Error-boundary behavior SHALL have deterministic regression protection

The implementation SHALL be protected by deterministic local tests for public projection, typed domain preservation, retry semantics, and transport parity without changing the five existing capabilities outside this change.

#### Scenario: Focused error-boundary tests cover expected and unexpected paths

- **WHEN** the focused Chat, confirmation, runtime, and stream regression tests run with external services disabled
- **THEN** they SHALL verify safe unexpected projections, preserved typed codes, rollback, and no raw exception leakage

#### Scenario: Existing frontend contract remains compatible

- **WHEN** existing mocked Chat frontend tests consume typed failed, in-progress, and confirmation-required responses
- **THEN** they SHALL continue to distinguish recoverable and terminal states without requiring message-text parsing

#### Scenario: Existing capabilities remain unchanged

- **WHEN** the change is validated against backend-regression-stability, commerce-cart, order-expiration, chat-retry-idempotency, and agent-write-hitl
- **THEN** those capabilities SHALL retain their existing behavior and their main specifications SHALL not be modified by this change
