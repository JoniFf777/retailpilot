# recommendation-categories Specification

## Purpose

This capability makes ShopMind structured recommendations category-aware and deterministic so Laptop and a real second catalog category share one extensible recommendation framework.

## Requirements

### Requirement: Recommendation categories SHALL resolve to a machine-readable supported outcome

The structured recommendation gate SHALL resolve reliable Laptop and Monitor intents before candidate retrieval. Ambiguous category intent SHALL produce `clarification_required` with a stable category-ambiguity code, and an explicitly recognized unsupported category SHALL produce a stable unsupported-category code. No unsupported or ambiguous request SHALL silently default to Laptop, and presentation text SHALL not be the business source of category identity.

#### Scenario: Explicit Laptop intent resolves to Laptop

- **WHEN** a recommendation request explicitly names a laptop/notebook or matches the existing closed Laptop constraint vocabulary
- **THEN** the gate SHALL return a machine-readable Laptop structured recommendation decision and the shared pipeline SHALL use the Laptop policy

#### Scenario: Explicit Monitor intent resolves to Monitor

- **WHEN** a recommendation request explicitly names a monitor/display and contains recommendation intent
- **THEN** the gate SHALL return a machine-readable Monitor structured recommendation decision and SHALL not route the request through Laptop policy

#### Scenario: Ambiguous category requests clarification

- **WHEN** a request asks for a recommendation but contains no reliable supported category or contains conflicting category signals
- **THEN** the structured result SHALL be `clarification_required` with a stable category-ambiguity code and SHALL not retrieve or rank Laptop candidates by default

#### Scenario: Unsupported category fails safely

- **WHEN** a request explicitly asks for a category without a registered policy, such as phone or tablet in this capability
- **THEN** the structured result SHALL expose a stable `unsupported_category` code and bounded clarification/failure text, SHALL not fall back to Laptop, and SHALL not fabricate catalog facts

### Requirement: Structured recommendations SHALL use a shared request and result envelope

The recommendation contract SHALL share category identity, generic budget/currency, availability requirement, generic preferences, canonical Product/SKU identity, price, availability, ranking/evidence fields, and category-specific attributes without adding every category's fields to one global Laptop-shaped schema.

#### Scenario: Generic request carries bounded category attributes

- **WHEN** a supported category is resolved
- **THEN** the backend SHALL create a machine-readable request containing the category, generic constraints, and only that policy's validated category attributes

#### Scenario: Structured result exposes shared and category-specific facts

- **WHEN** deterministic ranking produces a recommendation
- **THEN** the result SHALL expose shared SKU/price/availability/ranking/evidence fields plus machine-readable category and declared comparison specifications

#### Scenario: Existing Laptop response remains consumable

- **WHEN** an existing client reads a Laptop recommendation without understanding the additive category envelope
- **THEN** the existing Laptop structured constraint and response fields SHALL remain present and valid

### Requirement: Category policies SHALL isolate hard constraints, soft ranking, and missing attributes

Each supported category policy SHALL define its meaningful attributes, hard constraints, soft preferences, scoring dimensions, and display definitions. Shared orchestration SHALL perform candidate retrieval, generic availability/budget handling, ranking order, and SPU de-duplication; category fields SHALL not become global condition-tree branches.

#### Scenario: Hard constraints eliminate candidates

- **WHEN** a candidate violates an explicitly requested category hard constraint, generic budget, required availability, or active sale status
- **THEN** the candidate SHALL be excluded before scoring and SHALL not appear in the structured Top K

#### Scenario: Soft preferences rank without eliminating all candidates

- **WHEN** a candidate lacks or does not match a soft category preference
- **THEN** the policy SHALL apply a deterministic neutral/penalty score and SHALL not reject every candidate solely for a soft mismatch

#### Scenario: Missing hard and soft attributes are deterministic

- **WHEN** a candidate lacks a required hard attribute or a soft ranking attribute
- **THEN** a missing hard attribute SHALL make the candidate ineligible, while a missing soft attribute SHALL receive the documented neutral/penalty behavior without exception, random ordering, or LLM inference

### Requirement: Laptop policy SHALL preserve existing structured behavior

Laptop-specific parsing and scoring, including CPU/GPU tiers, memory, storage, weight, screen, use cases, price, availability, and current TECH-shaped compatibility vocabulary, SHALL remain available behind the Laptop policy. These fields SHALL not be treated as universal category attributes.

#### Scenario: Existing Laptop hard constraints still filter

- **WHEN** a Laptop request specifies the existing budget, memory, storage, weight, CPU, GPU, screen, or use-case constraints
- **THEN** the Laptop policy SHALL preserve the existing deterministic eligibility behavior and structured result semantics

#### Scenario: Existing Laptop ranking and alternatives remain stable

- **WHEN** the same Laptop candidates and constraints are supplied as before
- **THEN** the policy SHALL preserve the existing score ordering, stable tie-break, SPU de-duplication, and alternative-SKU behavior

#### Scenario: Laptop heuristics do not affect Monitor ranking

- **WHEN** a Monitor request is ranked
- **THEN** CPU/GPU/memory/storage/weight Laptop fields and Laptop use-case heuristics SHALL not contribute to Monitor eligibility or score

### Requirement: Monitor SHALL be a real second deterministic category policy

Monitor recommendations SHALL use the existing Monitor catalog/data identifiers and a policy with at least size, resolution, refresh rate, panel type, and use-case attributes. The policy SHALL support meaningful filtering, ranking, availability, missing-field behavior, and machine-readable comparison output.

#### Scenario: Monitor attributes are parsed and validated

- **WHEN** a request asks for a Monitor with budget, minimum size, resolution, refresh rate, panel type, or use-case preferences
- **THEN** the Monitor policy SHALL normalize only the supported typed attributes and place them in the category-specific request envelope

#### Scenario: Monitor hard constraints and availability apply

- **WHEN** Monitor candidates include active/inactive, in-stock/out-of-stock, budget, size, resolution, or refresh-rate differences
- **THEN** the policy SHALL exclude candidates that violate explicit hard constraints or availability and SHALL never recommend an unavailable SKU

#### Scenario: Monitor soft ranking and missing fields are stable

- **WHEN** Monitor candidates differ in panel/use-case fit or omit a soft attribute
- **THEN** the policy SHALL rank them with deterministic bounded points, neutral/penalty missing semantics, and no fabricated values

### Requirement: Catalog facts and deterministic ranking SHALL be authoritative

Recommendation candidates SHALL come from active canonical Catalog Product/SKU/inventory facts. LLM/Agent text, legacy Product price/in-stock fields, names, or RAG evidence SHALL not override canonical category, SKU, price, availability, or declared attributes. Equal inputs and a stable catalog snapshot SHALL produce the same ordered result using an explicit tie-break.

#### Scenario: Catalog facts override intent text

- **WHEN** a user or Agent mentions a price, stock state, or product attribute that differs from Catalog
- **THEN** deterministic filtering and output SHALL use Catalog facts and SHALL treat the mention only as a request constraint/preference

#### Scenario: Ranking tie-break is deterministic

- **WHEN** two eligible candidates have equal policy score and price
- **THEN** the result SHALL use the stable SKU/product ordering defined by the shared ranking framework and produce the same order on repeated execution

#### Scenario: RAG remains enrichment only

- **WHEN** RAG evidence is unavailable, partial, degraded, or conflicts with Catalog
- **THEN** existing RAG failure semantics SHALL remain intact, Catalog identity/price/stock/specifications SHALL remain authoritative, and RAG SHALL not introduce a new candidate

### Requirement: Structured recommendation UI SHALL render both categories through shared components

The first-party frontend SHALL render Laptop and Monitor structured results using the shared recommendation card/specification/comparison components. Category-specific fields SHALL be machine-readable and rendered by declared field metadata or an equivalent small mapping; a separate copied page/card pipeline SHALL not be required.

#### Scenario: Laptop structured result renders unchanged

- **WHEN** the frontend receives a Laptop recommendation
- **THEN** it SHALL render the existing Laptop constraints, cards, comparison, evidence, and SKU selection behavior

#### Scenario: Monitor structured result renders category fields

- **WHEN** the frontend receives a Monitor recommendation with declared comparison specifications
- **THEN** it SHALL render the Monitor category and fields such as size, resolution, refresh rate, and panel type through shared recommendation UI

#### Scenario: Malformed category result fails safely

- **WHEN** a streamed or JSON recommendation has an invalid category-specific shape
- **THEN** the existing typed response/projection error behavior SHALL remain safe and SHALL not cause the frontend to infer product facts from natural-language answer text

### Requirement: Recommendation actions SHALL preserve Agent, Commerce, and public safety boundaries

Recommendation category expansion SHALL not grant Agent direct writes, bypass canonical SKU identity, bypass PendingAction/HITL/expected-version confirmation, change Chat idempotency or authoritative Run semantics, alter safe Chat error projection, or change Order/payment/Cart/RAG boundaries.

#### Scenario: Recommendation add-to-cart uses canonical HITL

- **WHEN** a user selects a Laptop or Monitor recommendation for add-to-cart
- **THEN** the flow SHALL use the concrete canonical SKU, create or reuse the existing PendingAction, require existing expected-version confirmation, and write only through canonical Cart service

#### Scenario: Category B cannot use legacy Cart or direct Agent write

- **WHEN** a Monitor recommendation is converted into an add-to-cart intent
- **THEN** it SHALL not write legacy Cart, directly mutate Cart, or let an Agent/LLM commit domain state

#### Scenario: Existing runtime contracts remain intact

- **WHEN** category-aware recommendation runs through Chat JSON/SSE and retry/replay
- **THEN** backend thread/session boundaries, Chat idempotency, authoritative Run identity, HITL, safe error projection, and RAG failed/partial/degraded semantics SHALL remain valid

### Requirement: Category-aware recommendation SHALL have deterministic regression protection

The implementation SHALL include local deterministic tests for resolution, both category policies, cross-category isolation, structured output, frontend rendering, commerce compatibility, and existing capability regressions. The full non-integration backend and applicable frontend checks SHALL remain green.

#### Scenario: Same catalog and request are reproducible

- **WHEN** the same category request is evaluated repeatedly against the same candidate snapshot
- **THEN** the result ordering, scores, category attributes, and machine-readable outcome SHALL be identical

#### Scenario: Cross-category fields do not bleed

- **WHEN** Laptop fields are supplied to Monitor policy or Monitor fields are supplied to Laptop policy
- **THEN** invalid cross-category fields SHALL be ignored/rejected by the policy boundary and SHALL not alter the other category's score or hard filtering

#### Scenario: Existing capabilities regressions remain protected

- **WHEN** recommendation category tests run together with existing Cart/HITL, Chat retry/error, RAG, and backend regression suites
- **THEN** those existing contracts SHALL continue to pass without external LangSmith, Redis, RocketMQ, or API dependencies
