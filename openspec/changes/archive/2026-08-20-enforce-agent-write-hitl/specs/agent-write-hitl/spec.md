## Purpose

This capability makes Agent-side user and business state changes confirmation-first, auditable, deterministic, and replay-safe while preserving direct execution for read-only shopping and preference retrieval.

## ADDED Requirements

### Requirement: Agent actions SHALL have an explicit read or write-intent boundary

Active ShopMind Agent tool paths SHALL classify operations as read-only, write-intent preparation, or deterministic confirmation. Read-only product, document, preference, and canonical Cart reads MAY execute directly. An Agent or LLM SHALL NOT directly commit a user or business domain mutation. Runtime execution facts, audit records, and bounded candidate-context metadata remain system-owned execution state and are not domain writes requiring user confirmation.

#### Scenario: Read-only product and preference retrieval executes directly

- **WHEN** an Agent invokes an allowed product, document, Cart-read, or `get_user_preferences` tool
- **THEN** the tool SHALL be allowed to read data without creating a PendingAction or requiring HITL

#### Scenario: Domain write intent creates a confirmation boundary

- **WHEN** an Agent determines that a request would save, update, clear, add, remove, or otherwise mutate user or business state
- **THEN** it SHALL produce a typed write intent/PendingAction and SHALL NOT commit the target domain mutation

#### Scenario: Direct domain writer is not an active Agent capability

- **WHEN** an active Agent attempts to invoke a direct preference, Cart, or other domain repository writer
- **THEN** the runtime/tool boundary SHALL reject the invocation before persistence and SHALL record a bounded policy failure

### Requirement: Preference intent SHALL use one canonical HITL preparation flow

Preference save intent from Single Agent and Multi-Agent paths SHALL converge on the same confirmation-required `save_preference` action contract. Edits before confirmation only edit the pending action payload; they do not imply updating an existing UserPreference row. Preference read agents SHALL remain read-only. Before confirmation, no `UserPreference` row SHALL be created or deleted.

#### Scenario: Single Agent preference intent is handed off

- **WHEN** the legacy Single Agent receives a request to remember, save, or change a long-term preference
- **THEN** it SHALL not expose or invoke a direct `add_user_preference` writer and SHALL route the intent to the canonical preparation boundary

#### Scenario: Multi-Agent preference intent is handed off

- **WHEN** the Multi-Agent supervisor identifies a preference write intent
- **THEN** the Preference Agent SHALL not write, the write handoff SHALL prepare the canonical action, and the response SHALL be `confirmation_required`

#### Scenario: Preparation leaves preference state unchanged

- **WHEN** a preference PendingAction is prepared but not confirmed
- **THEN** the target user's persisted preferences SHALL remain unchanged and the response SHALL expose the PendingAction identity and preview

### Requirement: Preference PendingAction payloads SHALL be canonical and machine-readable

Every newly prepared preference action SHALL use a versioned schema with stable `action_type=save_preference`, operation semantics, normalized preference type/value, owner and thread binding, risk class, expiry, version, preview, and sufficient metadata for deterministic confirmation. Presentation text SHALL NOT be the source of truth for the write.

#### Scenario: Canonical preference action is inspectable

- **WHEN** a preference write intent is prepared
- **THEN** the persisted PendingAction SHALL contain a supported schema version, typed preference fields, owner/thread scope, `version`, `expires_at`, risk classification, and a user-facing preview

#### Scenario: Preference edit fields are bounded

- **WHEN** a user edits a pending preference before confirmation
- **THEN** only the registered preference fields and allowed enum/text constraints SHALL be accepted, and unsupported fields SHALL be rejected without a domain write

#### Scenario: Confirmation does not derive parameters from prose

- **WHEN** a user confirms a preference action
- **THEN** the confirmation service SHALL use the persisted typed payload plus validated explicit edits, not a new LLM interpretation or presentation-text parsing

### Requirement: Confirmation SHALL be deterministic, owner-bound, and transactional

Only the deterministic confirmation service SHALL write the preference domain state. Confirmation SHALL revalidate owner, thread, pending status, expiry, expected version, action schema, and payload, and SHALL commit the preference mutation and action terminal resolution in one caller-owned transaction.

#### Scenario: Valid confirmation writes exactly one preference

- **WHEN** the correct owner and thread confirm a live canonical preference action with the current version
- **THEN** the service SHALL persist the normalized preference and resolve the PendingAction atomically, without invoking an Agent or LLM

#### Scenario: Wrong owner or thread cannot confirm

- **WHEN** another owner or an unrelated thread attempts to confirm a preference action
- **THEN** confirmation SHALL fail with a typed ownership/scope error and SHALL leave both PendingAction and `UserPreference` state unchanged

#### Scenario: Confirmation transaction rolls back together

- **WHEN** preference persistence or PendingAction resolution fails before commit
- **THEN** the transaction SHALL roll back both sides and SHALL not report a successful preference write

### Requirement: Rejection, cancellation, and invalid actions SHALL be write-free

Reject, cancel, expired, stale-version, malformed-payload, unsupported-schema, and other non-success outcomes SHALL not mutate the target user or business domain state. Terminal action state may be persisted as an audit/lifecycle fact under the existing PendingAction transaction boundary.

#### Scenario: Cancel leaves preference state unchanged

- **WHEN** a user cancels or rejects a pending preference action
- **THEN** the action SHALL become cancelled or equivalent terminal state and no `UserPreference` write SHALL occur

#### Scenario: Expired or stale action is rejected

- **WHEN** a preference action is expired or the supplied `expected_version` is stale
- **THEN** confirmation SHALL return a typed non-success and SHALL not write, update, or delete preferences

#### Scenario: Invalid or legacy action fails closed

- **WHEN** a pending preference action has an invalid payload or a non-canonical legacy schema
- **THEN** confirmation SHALL return `unsupported_action_schema` or an equivalent stable typed failure, SHALL not dynamically convert it, and SHALL require a newly prepared action

### Requirement: Preference and confirmation replay SHALL be exactly-once

Repeated confirmation requests with the same action transition and valid idempotency semantics SHALL replay the persisted result without a second domain write. Chat retry or JSON/SSE recovery SHALL recover the same action rather than invoking preparation again.

#### Scenario: Repeated confirmation does not duplicate preference state

- **WHEN** the same owner repeats a successful preference confirmation
- **THEN** the service SHALL return the stored resolution as an idempotent replay and SHALL not create a second preference row or duplicate mutation

#### Scenario: Chat retry recovers one prepared action

- **WHEN** a Chat transport disconnects after preference preparation and the same authoritative Chat execution is recovered
- **THEN** the response SHALL expose the original PendingAction identity/version/preview and SHALL not prepare a second action

#### Scenario: JSON and SSE use one confirmation lifecycle

- **WHEN** the same logical Chat request is attempted through JSON and POST-SSE
- **THEN** both transports SHALL resolve the same authoritative preparation and confirmation boundary rather than creating separate actions

### Requirement: Canonical Cart HITL and legacy compatibility SHALL remain safe

The existing canonical SKU Cart prepare/confirm flow SHALL remain the source of Cart mutation and SHALL retain its owner, thread, version, expiry, inventory, price, and replay checks. Legacy direct Cart/preference writers SHALL not be active Agent capabilities, and no dual write or fallback writer SHALL be introduced.

#### Scenario: Existing canonical Cart flow remains unchanged

- **WHEN** a structured or legacy-origin add-to-cart action is confirmed through the existing canonical boundary
- **THEN** the action SHALL mutate only the canonical ShopMind Cart and SHALL preserve existing safety and replay semantics

#### Scenario: Legacy direct Cart writer cannot be used as fallback

- **WHEN** a canonical Cart preparation or confirmation fails
- **THEN** the Agent boundary SHALL return a typed non-success and SHALL not call legacy `cart_items` writers or report a fake success

#### Scenario: Legacy preference action requires re-preparation

- **WHEN** a historical preference PendingAction lacks the canonical schema contract
- **THEN** it MAY be read or safely cancelled where existing behavior permits, but confirm SHALL fail closed and SHALL not write preferences through a legacy fallback

### Requirement: The write boundary SHALL have deterministic regression protection

The project SHALL protect the Agent write boundary with static inventory checks and behavioral tests across Single Agent, Multi-Agent, confirmation, replay, ownership, and canonical Cart paths. The capability SHALL preserve backend regression stability, Chat retry idempotency, RAG failure semantics, and Order/payment safety.

#### Scenario: Direct-write inventory remains closed

- **WHEN** the production Agent tool sets, permission allowlists, and write-handoff registrations are inspected
- **THEN** no active Agent path SHALL expose a direct domain repository writer, and all supported domain writes SHALL be reachable only through prepare-then-confirm

#### Scenario: Focused HITL regression tests pass

- **WHEN** preference preparation/confirmation, negative paths, replay, ownership, Single/Multi parity, and canonical Cart regression tests run with external services disabled
- **THEN** the selected tests SHALL report zero failures and zero errors

#### Scenario: Existing capabilities remain independent

- **WHEN** this capability is implemented and validated
- **THEN** `backend-regression-stability`, `commerce-cart`, `order-expiration`, and `chat-retry-idempotency` contracts SHALL remain unchanged
