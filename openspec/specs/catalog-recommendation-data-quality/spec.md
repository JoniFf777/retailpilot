# catalog-recommendation-data-quality Specification

## Purpose

This capability defines deterministic quality and coverage rules for managed recommendation Catalog data discovered through CategoryRegistry without making demo item counts a permanent product contract.

## Requirements

### Requirement: Managed recommendation Catalog data SHALL satisfy canonical identity and integrity invariants

Managed recommendation data for every category discovered by CategoryRegistry SHALL have unique category/product/legacy/SKU identifiers, valid Product-to-SKU relationships, consistent category/status values, positive money with valid uppercase currency, and non-negative inventory. A deterministic validator SHALL report machine-readable issue codes before data is accepted; it SHALL not maintain a category-name-to-required-fields allowlist.

#### Scenario: Registered category data is discovered
- **WHEN** a new registered category seed is provided
- **THEN** the validator SHALL validate it using its registry definition without a validator source-code category branch

#### Scenario: Managed identifiers are unique
- **WHEN** the managed seed files are validated
- **THEN** duplicate category, product code, legacy product ID, or SKU code SHALL produce a deterministic validation failure identifying the duplicate namespace and value

#### Scenario: Product and SKU relationships are valid
- **WHEN** a managed product/SKU pair is validated
- **THEN** every SKU SHALL belong to an existing managed Product in the same category and every managed Product SHALL have the expected concrete SKU relationship

#### Scenario: Money/status/inventory invariants are invalid
- **WHEN** managed data contains non-positive price, invalid currency, invalid sale status, negative inventory, or an invalid reserved quantity
- **THEN** validation SHALL fail with bounded machine-readable issue codes before the data is accepted as recommendation fixture data

#### Scenario: Identity and money/inventory invariants fail
- **WHEN** data contains duplicate identity, broken Product/SKU relationship, invalid status, non-positive money, invalid currency, negative inventory, or invalid reserved quantity
- **THEN** validation SHALL fail with a deterministic issue code/path/detail

### Requirement: Managed attributes SHALL satisfy category policy completeness and type rules

Every active managed recommendation candidate SHALL provide attributes required by the active category's definition, with the declared number/string/enum/boolean type and valid enum values. Hard-required attributes SHALL be present; missing soft attributes MAY exist only when their documented missing semantics are covered by tests. Registry definitions, not Laptop/Monitor validator branches, SHALL determine the rules.

#### Scenario: An active registered candidate passes definition validation
- **WHEN** an active candidate contains all required attributes with valid types and enum values
- **THEN** the validator SHALL accept its category-scoped attributes

#### Scenario: Unknown or invalid attribute fails
- **WHEN** a candidate includes an undeclared key, wrong type, invalid enum value, or omits a required hard key
- **THEN** the validator SHALL fail with the category and attribute path and recommendation code SHALL not guess a replacement

#### Scenario: Complete Laptop candidate passes policy validation
- **WHEN** an active Laptop seed row is validated
- **THEN** it SHALL contain valid CPU/GPU, memory, storage, weight, screen, and use-case values required by the Laptop definition

#### Scenario: Complete Monitor candidate passes policy validation
- **WHEN** an active Monitor seed row is validated
- **THEN** it SHALL contain valid size, resolution, refresh-rate, panel-type, and use-case values required by the Monitor definition

#### Scenario: Missing hard attribute fails validation
- **WHEN** an active recommendation candidate omits a category hard-required attribute or uses the wrong declared type
- **THEN** the validator SHALL fail with the category and attribute code, and recommendation code SHALL not guess a replacement value

#### Scenario: All ten categories pass definition validation
- **WHEN** managed Laptop, Monitor, Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, and Router seed rows are validated
- **THEN** every hard-required field SHALL have the declared type and every enum value SHALL be valid

#### Scenario: Missing optional soft field is allowed deterministically
- **WHEN** an active candidate omits a definition-declared optional soft field
- **THEN** validation SHALL allow it and recommendation ranking SHALL use the definition's missing semantics

### Requirement: Managed Catalog data SHALL cover deterministic recommendation scenarios

The managed fixtures SHALL provide multiple meaningful price bands and use cases for currently managed Laptop and Monitor data, multiple eligible candidates, no-match conditions, unavailable candidates, and close-score cases for deterministic ranking tests. Exact item counts SHALL remain data/report facts rather than permanent capability requirements.

#### Scenario: Laptop demo coverage is meaningful
- **WHEN** the Laptop fixture set is evaluated
- **THEN** it SHALL include value, development, portable, gaming/performance, memory/storage, strict-budget no-match, and unavailable-filtering cases

#### Scenario: Monitor demo coverage is meaningful
- **WHEN** the Monitor fixture set is evaluated
- **THEN** it SHALL include office, high-refresh gaming, high-resolution, size, panel, strict-budget no-match, and unavailable-filtering cases

#### Scenario: Close candidates remain deterministically ordered
- **WHEN** multiple eligible candidates have equal or near-equal generic scores
- **THEN** the deterministic ranking and stable tie-break SHALL produce the same result order on repeated evaluation

#### Scenario: New category coverage is meaningful
- **WHEN** a new category fixture set is evaluated
- **THEN** it SHALL expose multiple deterministic recommendation outcomes including recommended, no-match, unavailable filtering, soft preference ordering, and stable ties

### Requirement: Seed execution SHALL be idempotent and non-destructive

Managed seed execution SHALL be repeatable, SHALL not create duplicate Products/SKUs, SHALL preserve existing inventory quantities, and SHALL not reset or delete legacy Product, user, Cart, or Order data. Managed replacement SHALL remain explicit and limited to rows owned by the same seed source.

#### Scenario: Clean managed seed inserts deterministically
- **WHEN** the managed Laptop and Monitor seeds run against an isolated empty catalog schema
- **THEN** they SHALL insert the declared managed rows and produce a stable bounded report

#### Scenario: Repeated seed creates no duplicates
- **WHEN** the same managed seeds run again
- **THEN** no duplicate category/product/SKU rows SHALL be created and the report SHALL identify existing rows as skipped or unchanged

#### Scenario: Existing inventory is preserved
- **WHEN** an existing managed SKU inventory quantity is changed and the seed is rerun
- **THEN** the seed SHALL not reset that inventory quantity unless an explicit, same-source managed replacement contract authorizes it

### Requirement: Product documents SHALL align by identity while Catalog remains factual authority

Every managed Product whose data contract requires a document SHALL have a document matching its canonical identity, regardless of category. Document text SHALL remain evidence/explanation only; registry and canonical Catalog facts SHALL own category, SKU, money, availability, and structured attributes.

#### Scenario: Future category document identity is checked
- **WHEN** a registered Router Product has a legacy identity
- **THEN** the validator SHALL require the matching document without adding Router-specific validator code

#### Scenario: Managed legacy identity has matching document
- **WHEN** the validator checks a managed Product with a legacy product ID
- **THEN** the expected document SHALL exist and contain the same bounded identity, otherwise validation SHALL fail deterministically

#### Scenario: Document price or specification conflicts with Catalog
- **WHEN** a document contains a price/specification that differs from canonical Catalog data
- **THEN** recommendation output SHALL retain Catalog price/specification/inventory facts and SHALL not use document text to override them

#### Scenario: RAG evidence is unavailable
- **WHEN** product document/RAG enrichment is unavailable or partial
- **THEN** existing RAG success/partial/degraded/failed semantics SHALL remain intact and valid Catalog recommendations SHALL not be discarded solely because evidence is unavailable

### Requirement: Data expansion SHALL preserve category, commerce, and runtime boundaries

New managed SKUs SHALL enter the existing registry-backed generic recommendation pipeline without changing its semantic source. Recommendation selection SHALL retain canonical SKU identity and the existing PendingAction, expected-version, canonical Cart, Chat retry, HITL, and safe-error boundaries.

#### Scenario: New Laptop SKU follows canonical commerce flow
- **WHEN** a user selects a newly managed Laptop recommendation for add-to-cart
- **THEN** the flow SHALL use canonical SKU → PendingAction → expected-version confirmation → canonical Cart, with no legacy fallback

#### Scenario: New Monitor SKU follows canonical commerce flow
- **WHEN** a user selects a newly managed Monitor recommendation for add-to-cart
- **THEN** the flow SHALL use the same canonical SKU/HITL/Cart boundary and SHALL not directly mutate Cart from Agent or recommendation code

#### Scenario: Existing runtime contracts remain unchanged
- **WHEN** expanded data is used through Chat JSON/SSE and retry/replay
- **THEN** Chat idempotency, authoritative Run identity, safe error projection, backend session/thread boundaries, Agent write-HITL, and Order/payment behavior SHALL remain unchanged

### Requirement: Data quality and recommendation coverage SHALL have deterministic regression protection

The Registry-backed validator, seed tests, Laptop/Monitor recommendation tests, cross-category isolation tests, and applicable frontend tests SHALL run without LangSmith, Redis, RocketMQ, PostgreSQL integration, or external API dependencies. The full non-integration backend and frontend checks SHALL remain green.

#### Scenario: Validator failure is machine-readable
- **WHEN** a fixture violates an invariant
- **THEN** the validator SHALL return a stable non-zero result with deterministic issue code/path/detail and SHALL not silently repair the data

#### Scenario: Same data and request reproduce the same recommendation
- **WHEN** the same managed seed snapshot and request are evaluated repeatedly
- **THEN** outcome, selected SKU order, score breakdown, comparison fields, and structured attributes SHALL be identical

#### Scenario: Existing capability regression suite remains green
- **WHEN** data-quality and recommendation tests run with the existing Cart/HITL, Chat retry/error, RAG, order-expiration, and backend regression suites
- **THEN** all existing capabilities SHALL retain their established behavior
