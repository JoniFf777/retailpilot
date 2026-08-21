# commerce-cart Specification

## Purpose

This capability defines one canonical SKU-based Cart for ShopMind commerce while preserving legacy intent inputs through a validated, confirmation-bound compatibility adapter.

## Requirements

### Requirement: Formal commerce confirmations SHALL write only the canonical SKU Cart

The system SHALL treat `shopmind_cart_items` as the sole Cart truth for supported ShopMind commerce. Structured recommendation confirmation and any supported legacy Chat add-to-cart confirmation SHALL use the same canonical SKU Cart mutation boundary. A successful confirmation SHALL be reported only after that canonical mutation is part of the committing transaction.

#### Scenario: Structured recommendation confirmation reaches the canonical Cart

- **WHEN** a user confirms a structured recommendation PendingAction for a valid SKU
- **THEN** the confirmed quantity SHALL be represented in the user's canonical SKU Cart and SHALL NOT require a legacy `cart_items` row

#### Scenario: Legacy Chat confirmation reaches the canonical Cart

- **WHEN** a supported legacy Chat add-to-cart intent is prepared, confirmed by its owner in the correct thread, and the canonical SKU remains valid
- **THEN** the confirmation SHALL write `shopmind_cart_items` and the public response SHALL retain the existing confirmation-compatible shape and status vocabulary

### Requirement: Legacy identifiers SHALL resolve collision-safely to Catalog SKU identity

For an untyped legacy identifier, the system SHALL inspect exact `sku_code`, `legacy_product_id`, and `product_code` namespaces together. It SHALL proceed when one canonical target is found or when all namespace hits converge to the same concrete SKU. If exact hits identify different canonical targets, it SHALL return typed `catalog_identifier_ambiguous` (or an equivalent stable typed code), not silently apply namespace priority. A missing mapping SHALL be a typed failure, and legacy Product price/in-stock data SHALL never authorize a Cart write.

#### Scenario: A Product with one Catalog SKU is auto-resolved

- **WHEN** a legacy identifier maps to one CatalogProduct with exactly one CatalogSku
- **THEN** the system SHALL prepare a canonical SKU PendingAction for that SKU, subject to current sale-status, inventory, and quantity validation

#### Scenario: Product mapping without a concrete SKU fails

- **WHEN** an identifier resolves to a CatalogProduct but that Product has no CatalogSku
- **THEN** the system SHALL return typed `catalog_not_found` (or an equivalent canonical-SKU failure), SHALL NOT report variant clarification, SHALL create no PendingAction, and SHALL mutate neither Cart

#### Scenario: Multiple namespaces converge to one concrete SKU

- **WHEN** an untyped identifier matches more than one identity namespace but every match resolves to the same concrete CatalogProduct/CatalogSku
- **THEN** the system SHALL continue with that one canonical SKU and SHALL record only bounded non-sensitive resolution diagnostics

#### Scenario: No Catalog mapping exists

- **WHEN** a legacy identifier matches neither an exact Catalog SKU code nor an exact Catalog Product mapping
- **THEN** the system SHALL return a typed mapping failure, SHALL create no confirmed action, SHALL leave the canonical Cart unchanged, and SHALL not write legacy Cart as fallback

#### Scenario: Cross-namespace identifier collision fails safely

- **WHEN** an untyped identifier matches multiple identity namespaces whose concrete targets differ
- **THEN** the system SHALL return typed `catalog_identifier_ambiguous`, SHALL create no PendingAction, SHALL write neither `shopmind_cart_items` nor `cart_items`, and SHALL not use namespace priority or legacy fallback

### Requirement: SKU ambiguity and SKU availability SHALL fail safely

The system SHALL never silently select a variant when a Product has multiple Catalog SKUs and the requested identifier does not identify one concrete SKU. It SHALL reject inactive, unavailable, or invalid quantity mutations using the existing typed domain-error boundary.

#### Scenario: Multiple SKUs require explicit variant choice

- **WHEN** a legacy identifier maps to a Product with more than one SKU and no concrete variant is specified
- **THEN** the system SHALL return a machine-readable clarification/ambiguity outcome, SHALL not create a confirmable Cart mutation, and SHALL not write either Cart table

#### Scenario: Inactive, out-of-stock, or invalid quantity is rejected

- **WHEN** the resolved SKU or Product is inactive, inventory is missing/insufficient, or the requested quantity violates Cart limits
- **THEN** the system SHALL return the corresponding typed failure and SHALL leave the canonical Cart unchanged

### Requirement: PendingAction security and replay semantics SHALL remain intact

Canonical add-to-cart confirmation SHALL preserve user ownership, thread binding, expiry, expected-version checks, quantity edits, and existing idempotent replay/conflict semantics. `ConfirmChatRequest.expected_version` MAY be optional at the generic schema level for unrelated actions, but it SHALL be present and equal to the client's real `PendingActionView.version` for canonical SKU add-to-cart. A legacy adapter SHALL not bypass these checks or substitute the server's latest version.

#### Scenario: Wrong owner or thread cannot confirm

- **WHEN** a user or thread different from the PendingAction scope attempts to read, edit, confirm, or cancel it
- **THEN** the system SHALL reject the transition and SHALL not mutate either Cart

#### Scenario: Expired or stale PendingAction cannot mutate the Cart

- **WHEN** a PendingAction is expired or its expected version is stale at confirmation time
- **THEN** the system SHALL return the existing typed expiry/version failure and SHALL not perform a canonical Cart mutation

#### Scenario: Repeated confirmation is idempotent

- **WHEN** the same owner repeats the same confirmation request for an already-resolved canonical add-to-cart action
- **THEN** the system SHALL replay the persisted success or return the existing resolution conflict according to current semantics, and SHALL not add the requested quantity again

#### Scenario: Missing expected version for canonical Chat add-to-cart is rejected

- **WHEN** a client confirms a canonical SKU add-to-cart through `/api/chat/confirm` without `expected_version`
- **THEN** the system SHALL return a typed non-success and SHALL not mutate either Cart; it SHALL not read the current version and reuse it as the client's expected version

#### Scenario: Stale legacy-origin canonical action is rejected

- **WHEN** a legacy Chat-created canonical SKU PendingAction is confirmed with a stale `expected_version`
- **THEN** the system SHALL return `version_conflict`, SHALL leave the canonical Cart unchanged, and SHALL not write legacy Cart

### Requirement: Cart, Checkout, and Order SHALL share the canonical SKU fact

The formal Cart API, Checkout Preview, and Order creation SHALL use the canonical SKU Cart and SHALL not read legacy `cart_items` as an alternate or merged fact source. After a successful supported confirmation, the canonical Cart SHALL be immediately readable through the current Cart API and eligible for Checkout Preview subject to normal revalidation.

#### Scenario: Confirmed item is visible through the canonical Cart API

- **WHEN** canonical add-to-cart confirmation commits successfully
- **THEN** `GET /api/cart` for the same owner SHALL return the corresponding SKU and quantity without requiring a legacy Cart read

#### Scenario: Confirmed item enters Checkout Preview

- **WHEN** the canonical Cart contains the confirmed SKU and the Checkout service is configured
- **THEN** Checkout Preview SHALL read that item, build its normal fingerprint/price snapshot, and apply its existing price, sale-status, currency, and inventory revalidation rules

#### Scenario: Formal Checkout does not consume legacy Cart

- **WHEN** only a legacy `cart_items` row exists and no corresponding canonical SKU Cart row exists
- **THEN** formal Cart/Checkout SHALL not treat the legacy row as a ShopMind Cart item or include it in an Order

### Requirement: Canonical mutation failure SHALL be truthful and shall not dual-write

The system SHALL commit the PendingAction terminal state and canonical Cart mutation as one caller-owned transaction. If canonical resolution, validation, or persistence fails, the public result SHALL be typed/non-success and SHALL not claim that the item was added. The formal path SHALL never write both `cart_items` and `shopmind_cart_items` for one confirmation.

#### Scenario: Canonical Cart transaction fails

- **WHEN** the canonical Cart write or its surrounding transaction raises before commit
- **THEN** the caller SHALL roll back, return a typed failure, and SHALL not report “added to cart” or write legacy Cart as recovery

#### Scenario: No dual write occurs

- **WHEN** any supported structured or legacy add-to-cart confirmation succeeds
- **THEN** exactly the canonical SKU Cart mutation boundary SHALL be used, with no compensating or parallel insert into legacy `cart_items`

#### Scenario: Historical legacy PendingAction cannot revive the legacy Cart writer

- **WHEN** a pre-existing add-to-cart PendingAction has a non-canonical legacy payload and a client attempts to confirm it
- **THEN** the system SHALL return typed `unsupported_action_schema` (or an equivalent safe failure), SHALL invoke no legacy Cart writer, SHALL write neither Cart table, and SHALL require a newly prepared canonical action

### Requirement: Resolver and Write Handoff outcomes SHALL be machine-readable

The resolver, compatibility adapter, canonical preparation boundary, and Write Handoff SHALL use stable typed status/error outcomes for success, not-found, ambiguity, multi-SKU clarification, unavailable SKU, and failure. Presentation text SHALL be generated after business classification and SHALL NOT drive success, ambiguity, SKU selection, fallback, or failure control flow. A clarification SHALL remain distinguishable from a mutation failure even when it has no `pending_action_id`.

#### Scenario: Typed ambiguity is not inferred from presentation text

- **WHEN** an identifier collision or multi-SKU condition is detected
- **THEN** the Write Handoff SHALL branch on the machine-readable outcome/code, and changing the localized message SHALL not change whether an action is created or a Cart is mutated

#### Scenario: Multi-SKU clarification is not misreported as ordinary execution failure

- **WHEN** a Product has multiple possible SKUs and the user has not supplied a unique variant
- **THEN** the public Chat response SHALL use the existing compatible handled-request status with a clarification presentation, the internal outcome SHALL be `clarification_required`, and no PendingAction or Cart mutation SHALL be created

### Requirement: Canonical behavior SHALL have deterministic local regression protection

The project SHALL protect the dual-Cart boundary with focused tests covering legacy and structured confirmations, identifier resolution, ambiguity, failure, ownership, replay, Cart visibility, and Checkout entry. Validation SHALL run with LangSmith tracing disabled and SHALL not require PostgreSQL integration, Redis, RocketMQ, or external APIs for the local suite.

#### Scenario: Focused Cart-unification tests pass

- **WHEN** the directly affected local service/API/Agent and frontend mocked tests are run with external services disabled
- **THEN** the selected tests SHALL report zero failures and zero errors

#### Scenario: Full local backend regression remains green

- **WHEN** the full non-integration backend suite is run with a writable isolated pytest temporary directory
- **THEN** the suite SHALL report zero failures and zero errors without changing the established regression-stability or RAG semantics

#### Scenario: Successful canonical add-to-cart refreshes frontend Cart state

- **WHEN** a structured or legacy-origin canonical add-to-cart confirmation succeeds in the first-party frontend
- **THEN** the client SHALL invalidate/refetch the canonical Cart and invalidate stale Checkout Preview state without requiring a frontend state-management redesign
