# recommendation-schema-engine Specification

## Purpose

This capability makes ordinary product-category recommendation behavior declarative, typed, deterministic, and category-independent across resolution, parsing, filtering, ranking, catalog validation, public projection, and first-party rendering.

## Requirements

### Requirement: The CategoryRegistry SHALL be the sole source of truth for supported recommendation categories
The server SHALL load trusted typed CategoryDefinition documents through one CategoryRegistry. The registry SHALL own category lookup, normalized aliases, definition validation, attribute schema, display metadata, ranking references, and supported-category discovery. Gate, parser, recommendation engine, Agent graph, frontend result projection, and catalog validator SHALL consume the registry rather than maintain independent category lists.

#### Scenario: Registry resolves a canonical code and alias
- **WHEN** a category code or non-conflicting registered alias is submitted
- **THEN** the registry SHALL return the same validated definition and canonical code

#### Scenario: Registry rejects malformed definitions before serving requests
- **WHEN** definitions contain duplicate codes, conflicting aliases, unsupported types/operators/ranking strategies, invalid enum values, invalid missing strategies, dangling ranking references, or dangling display references
- **THEN** registry construction SHALL fail closed with stable validation facts and SHALL not expose a partially registered set

### Requirement: CategoryDefinition SHALL express complete typed category semantics without executable category code
Each definition SHALL express code, display name, aliases, version, and ordered attributes. Every attribute SHALL declare key, label, type (`number`, `string`, `enum`, or `boolean`), optional unit/enum values, supported operators (`eq`, `gte`, `lte`, `contains`, `match`, `enum_match`), constraint role (`hard`, `soft`, `hard_or_soft`, or `display_only`), ranking strategy (`higher_is_better`, `lower_is_better`, `exact_match`, `preference_match`, or `neutral`), missing strategy (`reject_if_hard`, `neutral`, `deterministic_penalty`, or `ignore`), and display/format metadata. Definitions SHALL not embed executable code.

#### Scenario: A new numeric attribute is generic
- **WHEN** a category definition adds `battery_wh` as a numeric attribute with `gte` and `higher_is_better`
- **THEN** the existing parser, constraint engine, ranking engine, and renderer SHALL work without recognizing the literal name `battery_wh`

#### Scenario: Attribute metadata is type-safe
- **WHEN** a request or candidate supplies a wrong type or undeclared enum value
- **THEN** validation SHALL return a bounded typed issue and SHALL not continue with an unsafe comparison

### Requirement: Generic category resolution SHALL be alias-driven and machine-readable
Resolution SHALL accept structured category intent, validate candidate codes through the registry, and return `resolved`, `category_ambiguous`, or `unsupported_category`. Alias vocabulary and collision precedence SHALL come from the registry. Unknown or unsupported categories SHALL never default to Laptop.

#### Scenario: Supported category intent resolves
- **WHEN** structured extraction returns a registered code or alias
- **THEN** the gate SHALL emit one generic structured-recommendation path with the canonical code before catalog retrieval

#### Scenario: Conflicting categories are ambiguous
- **WHEN** extraction returns two distinct supported candidates with no deterministic winner
- **THEN** the result SHALL be `clarification_required` with `error_code=category_ambiguous`, no candidates, and no ranking

#### Scenario: Explicit unsupported category fails safely
- **WHEN** extraction returns an unregistered category code
- **THEN** the result SHALL expose `unsupported_category`, bounded clarification, and no catalog facts or fallback

### Requirement: Generic request parsing SHALL be schema-guided and fail closed
The parser SHALL provide the active category schema to a structured extraction layer and SHALL normalize typed constraints into `RecommendationRequest.category_attributes`. It SHALL validate keys, values, operators, and roles against the registry; extractor output SHALL remain separate from Catalog facts.

#### Scenario: Camera attribute extraction uses the registry
- **WHEN** a new definition declares `sensor_size` and the extractor returns that key with a typed value
- **THEN** the parser SHALL produce a validated constraint without a `parse_camera` function or category branch

#### Scenario: Invalid request attributes fail safely
- **WHEN** extraction returns an unknown key, unsupported operator, wrong type, invalid enum, or unresolved `hard_or_soft` role
- **THEN** parsing SHALL return a typed safe outcome and SHALL not send the invalid constraint to ranking

### Requirement: Generic constraints SHALL filter candidates using definition semantics only
The constraint engine SHALL evaluate generic budget/availability and category attributes using the active definition. It SHALL implement number, string, enum/multi-enum, and boolean operators, hard/soft roles, cross-category isolation, and deterministic missing behavior without checking category codes or business attribute names.

#### Scenario: Hard constraints eliminate candidates
- **WHEN** a candidate violates a hard condition, budget, availability, or required hard field
- **THEN** it SHALL be removed before scoring

#### Scenario: Soft constraints remain ranking signals
- **WHEN** a candidate misses or mismatches a soft constraint
- **THEN** it SHALL remain eligible and receive the declared neutral or deterministic penalty signal

### Requirement: Generic ranking SHALL be bounded, deterministic, and dimensionally safe
The ranking engine SHALL use declared bounds or explicitly permitted post-hard-filter snapshot bounds, clamp numeric signals to `[0,1]`, implement higher/lower directions, exact/boolean/enum matches, preference matches, and declared missing behavior, then combine bounded weighted signals with deterministic rounding. Price SHALL be a budget constraint and stable tie-break by default, not an unnormalized score term.

#### Scenario: Equal input is reproducible
- **WHEN** the same request and catalog snapshot are evaluated repeatedly
- **THEN** eligibility, normalized signals, breakdown, score, and order SHALL be identical

#### Scenario: Ties use the stable rule
- **WHEN** candidates have equal score and price
- **THEN** the engine SHALL order by `sku_code` after deterministic SPU de-duplication

### Requirement: Missing semantics SHALL be explicit and observable
The engine and validator SHALL distinguish missing hard, missing soft, invalid request, and display-only values. `reject_if_hard` SHALL make a candidate ineligible; `neutral` SHALL contribute 0.5; `deterministic_penalty` SHALL contribute a definition-declared bounded signal; `ignore` SHALL omit the rule. No missing value SHALL be invented.

#### Scenario: Missing required hard field is rejected
- **WHEN** an active candidate omits an attribute required by a hard rule
- **THEN** validation SHALL fail and the engine SHALL not rank it eligible

#### Scenario: Missing soft field is stable
- **WHEN** an eligible candidate lacks a soft ranking field
- **THEN** the result SHALL contain the documented neutral/penalty breakdown and remain deterministic

### Requirement: Generic result projection SHALL expose declared comparison fields
Recommended results SHALL retain canonical Product/SKU, money, availability, score, evidence, alternatives, and Commerce context while exposing ordered typed comparison fields from registry/catalog declarations. Projection SHALL not infer facts from answer text.

#### Scenario: Any category projects comparable fields
- **WHEN** a valid candidate is recommended for a registered category
- **THEN** its declared comparison fields SHALL be serializable, ordered, typed, and sufficient for a category-independent renderer

#### Scenario: Malformed projection fails safely
- **WHEN** a stored or streamed recommendation contains an invalid declared field
- **THEN** the existing safe projection-error boundary SHALL be used without frontend fallback or prose inference

### Requirement: The first-party frontend SHALL render generic recommendation metadata
The frontend SHALL iterate generic comparison/constraint fields for cards and comparison views. Ordinary categories SHALL not require React conditionals, copied pages, or category label maps. Unresolved results SHALL remain generic/clarification/error states, and SKU selection SHALL keep the existing recommendation-context requirement.

#### Scenario: Test accessory renders without React changes
- **WHEN** a valid `test_accessory` result contains comparison fields
- **THEN** shared recommendation UI SHALL render them by metadata iteration without a category conditional

#### Scenario: Existing results remain consumable
- **WHEN** released Laptop or Monitor results are rendered during migration
- **THEN** cards, comparison, evidence, alternatives, and SKU selection SHALL remain available through the generic envelope or compatibility bridge

### Requirement: Registry-backed catalog validation SHALL cover data and documents
The validator SHALL automatically validate every registered category's supported code, attribute keys, types, enum values, required hard fields, canonical identity, money, inventory, and document identity. Adding a category SHALL not require a validator category branch.

#### Scenario: Router data is validated from its definition
- **WHEN** Router definition and catalog/document fixtures are supplied
- **THEN** the validator SHALL discover and validate Router without new category source code

#### Scenario: Invalid data is rejected deterministically
- **WHEN** a row has an unknown attribute, wrong type, invalid enum, missing hard field, invalid identity/money/inventory, or missing document
- **THEN** validation SHALL fail with stable issue code/path/detail ordering

### Requirement: Recommendation expansion SHALL preserve Commerce, Agent, RAG, and runtime boundaries
The generic engine SHALL output canonical SKU identity and SHALL not modify `SKU → PendingAction → expected_version → canonical Cart`. Read Agents remain read/intent-only; RAG remains enrichment; Chat error projection, retry/idempotency, run identity, confirmation, and cancellation semantics remain unchanged.

#### Scenario: Generic recommendation enters existing HITL
- **WHEN** a user selects a `test_accessory`, Laptop, Monitor, or future ordinary SKU
- **THEN** preparation/confirmation/cancellation SHALL use the existing PendingAction and canonical Cart path with no direct Agent write

#### Scenario: Retry recovery remains authoritative
- **WHEN** the same Chat idempotency key is retried around a generic recommendation or PendingAction
- **THEN** the authoritative Run/PendingAction result SHALL be recovered without a second execution or mutation

### Requirement: The architecture proof SHALL demonstrate no-core-code category addition
The acceptance suite SHALL define `test_accessory` only through a CategoryDefinition fixture, catalog Product/SKU/document fixture, and tests. It SHALL execute Registry resolution, typed validation, generic hard filtering, deterministic ranking, generic result projection, and existing Commerce context without modifying Gate, Parser, service, constraints, ranking, graph, validator core, or frontend production code.

#### Scenario: Test accessory completes the full path
- **WHEN** the architecture-proof fixture runs against a fixed request and candidate snapshot
- **THEN** it SHALL resolve, validate, filter, rank, project typed fields, and expose canonical SKU identity

#### Scenario: New attribute remains name-agnostic
- **WHEN** the fixture adds numeric `battery_wh` using existing semantics
- **THEN** the generic engine SHALL work without a literal `battery_wh` reference in production code
