# recommendation-categories Specification

## Purpose

This capability makes ShopMind structured recommendations category-aware, registry-backed, and deterministic so Laptop, Monitor, and future ordinary categories share one generic recommendation framework.

## Requirements

### Requirement: Recommendation categories SHALL resolve to a machine-readable supported outcome

The structured recommendation gate SHALL resolve category intent through the server-owned CategoryRegistry and shall emit one canonical category code before candidate retrieval. Registered aliases SHALL be normalized by the registry. Ambiguous category intent SHALL produce `clarification_required` with stable `category_ambiguous`; an explicitly named category absent from the registry SHALL produce stable `unsupported_category`. No unsupported or ambiguous request SHALL silently default to Laptop, and presentation text SHALL not be the business source of category identity.

#### Scenario: Explicit registered category resolves
- **WHEN** a request identifies a registered Laptop, Monitor, or future category by canonical code or alias
- **THEN** the gate SHALL return one generic structured recommendation decision containing the canonical code and SHALL use the shared pipeline

#### Scenario: Explicit Laptop intent resolves to Laptop
- **WHEN** a recommendation request explicitly names a laptop/notebook or matches the Laptop definition's registered aliases and constraints
- **THEN** the gate SHALL return a machine-readable Laptop structured recommendation decision and the shared pipeline SHALL use the generic engine

#### Scenario: Explicit Monitor intent resolves to Monitor
- **WHEN** a recommendation request explicitly names a monitor/display and contains recommendation intent
- **THEN** the gate SHALL return a machine-readable Monitor structured recommendation decision and SHALL not route the request through Laptop semantics

#### Scenario: Ambiguous category requests clarification
- **WHEN** a request contains no reliable category or conflicting registered category signals
- **THEN** the structured result SHALL be `clarification_required` with `category_ambiguous`, no catalog retrieval, and no Laptop fallback

#### Scenario: Unsupported category fails safely
- **WHEN** a request explicitly names a category not present in the registry
- **THEN** the structured result SHALL expose `unsupported_category`, bounded clarification text, and no fabricated catalog facts

### Requirement: Structured recommendations SHALL use a shared request and result envelope

The recommendation contract SHALL share opaque validated category identity, generic budget/currency, availability requirement, generic preferences, typed category attributes/constraints, canonical Product/SKU identity, price, availability, ranking/evidence fields, generic comparison fields, and category-specific attributes without adding every category's fields to one global Laptop-shaped schema. Released Laptop-shaped fields MAY remain as an additive compatibility projection.

#### Scenario: Generic request carries bounded category attributes
- **WHEN** a supported category is resolved
- **THEN** the backend SHALL create a machine-readable request containing the category, generic constraints, and only that definition's validated category attributes

#### Scenario: Structured result exposes shared and category-specific facts
- **WHEN** deterministic ranking produces a recommendation
- **THEN** the result SHALL expose shared SKU/price/availability/ranking/evidence fields plus machine-readable category display metadata and declared comparison fields

#### Scenario: Existing Laptop response remains consumable
- **WHEN** an existing client reads a Laptop recommendation without understanding the additive generic envelope
- **THEN** the existing Laptop structured constraint and response fields SHALL remain present and valid

### Requirement: Category policies SHALL isolate hard constraints, soft ranking, and missing attributes

Each registered category SHALL use the generic recommendation engine and its CategoryDefinition for meaningful attributes, hard constraints, soft preferences, scoring dimensions, display definitions, and missing semantics. A category-specific custom scorer or policy SHALL not be the standard path for ordinary categories. Shared orchestration SHALL perform candidate retrieval, generic availability/budget handling, deterministic ranking order, and SPU de-duplication; category fields SHALL not become global condition-tree branches.

#### Scenario: Hard constraints eliminate candidates
- **WHEN** a candidate violates an explicitly requested category hard constraint, generic budget, required availability, or active sale status
- **THEN** the candidate SHALL be excluded before scoring and SHALL not appear in the structured Top K

#### Scenario: Soft preferences rank without eliminating all candidates
- **WHEN** a candidate lacks or does not match a soft category preference
- **THEN** the generic engine SHALL apply a deterministic neutral/penalty score and SHALL not reject every candidate solely for a soft mismatch

#### Scenario: Missing hard and soft attributes are deterministic
- **WHEN** a candidate lacks a required hard attribute or a soft ranking attribute
- **THEN** a missing hard attribute SHALL make the candidate ineligible, while a missing soft attribute SHALL receive the documented neutral/penalty behavior without exception, random ordering, or LLM inference

#### Scenario: Laptop and Monitor use generic semantics
- **WHEN** Laptop and Monitor requests are evaluated with their existing candidate snapshots
- **THEN** their behavior SHALL be represented by definitions and generic operators/ranking strategies, with released compatibility projections where required

#### Scenario: Ordinary category needs no policy source edit
- **WHEN** a valid Router definition uses existing generic capabilities
- **THEN** adding Router SHALL not require a new Router policy/scorer class or edits to generic engine source

### Requirement: Laptop policy SHALL preserve existing structured behavior

Laptop CPU/GPU tiers, memory, storage, weight, screen, use cases, budget, availability, structured output, and released compatibility behavior SHALL be represented by the Laptop definition and generic engine. A thin compatibility projection MAY preserve the released Laptop-shaped envelope but SHALL not implement a separate policy hierarchy.

#### Scenario: Existing Laptop hard constraints still filter
- **WHEN** a Laptop request specifies the existing budget, memory, storage, weight, CPU, GPU, screen, or use-case constraints
- **THEN** the generic definition-driven engine SHALL preserve the existing deterministic eligibility behavior and structured result semantics

#### Scenario: Existing Laptop ranking and alternatives remain stable
- **WHEN** the same Laptop candidates and constraints are supplied as before
- **THEN** the generic engine SHALL preserve the existing score ordering, stable tie-break, SPU de-duplication, and alternative-SKU behavior

#### Scenario: Laptop heuristics do not affect Monitor ranking
- **WHEN** a Monitor request is ranked
- **THEN** CPU/GPU/memory/storage/weight Laptop fields and Laptop use-case heuristics SHALL not contribute to Monitor eligibility or score

### Requirement: Monitor SHALL be a real deterministic category on the generic engine

Monitor recommendations SHALL use its registered definition with size, resolution, refresh rate, panel type, and use-case attributes. The definition SHALL support meaningful filtering, ranking, availability, missing-field behavior, and machine-readable comparison output without a Monitor-specific scorer.

#### Scenario: Monitor attributes are parsed and validated
- **WHEN** a request asks for a Monitor with budget, minimum size, resolution, refresh rate, panel type, or use-case preferences
- **THEN** the schema-guided parser SHALL normalize only the registered typed attributes and place them in the category-specific request envelope

#### Scenario: Monitor hard constraints and availability apply
- **WHEN** Monitor candidates include active/inactive, in-stock/out-of-stock, budget, size, resolution, or refresh-rate differences
- **THEN** the generic engine SHALL exclude candidates that violate explicit hard constraints or availability and SHALL never recommend an unavailable SKU

#### Scenario: Monitor soft ranking and missing fields are stable
- **WHEN** Monitor candidates differ in panel/use-case fit or omit a soft attribute
- **THEN** the generic engine SHALL rank them with deterministic bounded signals and documented missing semantics without fabricated values

### Requirement: Catalog facts and deterministic ranking SHALL be authoritative

Recommendation candidates SHALL come from active canonical Catalog Product/SKU/inventory facts. LLM/Agent text, legacy Product price/in-stock fields, names, or RAG evidence SHALL not override canonical category, SKU, price, availability, or declared attributes. Equal inputs and a stable catalog snapshot SHALL produce the same ordered result using an explicit tie-break.

#### Scenario: Catalog facts override intent text
- **WHEN** a user or Agent mentions a price, stock state, or product attribute that differs from Catalog
- **THEN** deterministic filtering and output SHALL use Catalog facts and SHALL treat the mention only as a request constraint/preference

#### Scenario: Ranking tie-break is deterministic
- **WHEN** two eligible candidates have equal generic score and price
- **THEN** the result SHALL use stable SPU/SKU ordering and produce the same order on repeated execution

#### Scenario: RAG remains enrichment only
- **WHEN** RAG evidence is unavailable, partial, degraded, or conflicts with Catalog
- **THEN** existing RAG failure semantics SHALL remain intact, Catalog identity/price/stock/specifications SHALL remain authoritative, and RAG SHALL not introduce a new candidate

### Requirement: Structured recommendation UI SHALL render registered categories through shared components

The first-party frontend SHALL render recommendation cards, constraints, comparison, evidence, alternatives, and SKU selection from generic result metadata. Category-specific fields SHALL be machine-readable and rendered by declared field metadata; a separate copied page/card pipeline or supported-category table SHALL not be required.

#### Scenario: Laptop structured result renders unchanged
- **WHEN** the frontend receives a Laptop recommendation
- **THEN** it SHALL render the existing Laptop constraints, cards, comparison, evidence, and SKU selection behavior through the shared envelope or compatibility bridge

#### Scenario: Monitor structured result renders category fields
- **WHEN** the frontend receives a Monitor recommendation with declared comparison fields
- **THEN** it SHALL render the fields through shared recommendation UI metadata iteration

#### Scenario: Ordinary category renders without React changes
- **WHEN** the frontend receives a valid `test_accessory` or future ordinary category result with declared comparison fields
- **THEN** the shared renderer SHALL display it without a category conditional or category label map

#### Scenario: Malformed category result fails safely
- **WHEN** a streamed or JSON recommendation has an invalid category-specific shape
- **THEN** the existing typed response/projection error behavior SHALL remain safe and SHALL not cause the frontend to infer product facts from natural-language answer text

### Requirement: Recommendation actions SHALL preserve Agent, Commerce, and public safety boundaries

Recommendation category expansion SHALL not grant Agent direct writes, bypass canonical SKU identity, bypass PendingAction/HITL/expected-version confirmation, change Chat idempotency or authoritative Run semantics, alter safe Chat error projection, or change Order/payment/Cart/RAG boundaries.

#### Scenario: Recommendation add-to-cart uses canonical HITL
- **WHEN** a user selects a Laptop, Monitor, `test_accessory`, or future ordinary recommendation for add-to-cart
- **THEN** the flow SHALL use the concrete canonical SKU, create or reuse the existing PendingAction, require existing expected-version confirmation, and write only through canonical Cart service

#### Scenario: Category B cannot use legacy Cart or direct Agent write
- **WHEN** a future ordinary recommendation is converted into an add-to-cart intent
- **THEN** it SHALL not write legacy Cart, directly mutate Cart, or let an Agent/LLM commit domain state

#### Scenario: Existing runtime contracts remain intact
- **WHEN** category-aware recommendation runs through Chat JSON/SSE and retry/replay
- **THEN** backend thread/session boundaries, Chat idempotency, authoritative Run identity, HITL, safe error projection, and RAG failed/partial/degraded semantics SHALL remain valid

### Requirement: Category-aware recommendation SHALL have deterministic regression protection

The implementation SHALL include local deterministic tests for registry resolution, schema parsing, generic operators/ranking/missing semantics, Laptop/Monitor compatibility, cross-category isolation, structured output, frontend rendering, commerce compatibility, and existing capability regressions. The full non-integration backend and applicable frontend checks SHALL remain green.

#### Scenario: Same catalog and request are reproducible
- **WHEN** the same category request is evaluated repeatedly against the same candidate snapshot
- **THEN** result ordering, scores, category attributes, comparison fields, and machine-readable outcome SHALL be identical

#### Scenario: Cross-category fields do not bleed
- **WHEN** a request supplies an attribute not declared by the resolved category
- **THEN** the invalid field SHALL fail closed and SHALL not alter another category's score or hard filtering

#### Scenario: Existing capabilities regressions remain protected
- **WHEN** recommendation category tests run together with existing Cart/HITL, Chat retry/error, RAG, and backend regression suites
- **THEN** those existing contracts SHALL continue to pass without external LangSmith, Redis, RocketMQ, or API dependencies
