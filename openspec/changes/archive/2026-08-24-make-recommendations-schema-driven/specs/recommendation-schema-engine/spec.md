## Purpose

This capability makes ordinary product-category recommendation behavior declarative, typed, deterministic, and category-independent across resolution, parsing, filtering, ranking, catalog validation, public projection, and first-party rendering.

## ADDED Requirements

### Requirement: The CategoryRegistry SHALL be the sole source of truth for supported recommendation categories

The server SHALL load a trusted set of typed `CategoryDefinition` documents through one `CategoryRegistry`. The registry SHALL own category code lookup, normalized alias lookup, definition validation, attribute schema, display metadata, ranking references, and supported-category discovery. Gate, parser, recommendation engine, Agent graph, frontend contract projection, and catalog validator SHALL consume the registry rather than maintain independent category lists.

#### Scenario: Registry resolves a canonical code and alias
- **WHEN** a category code or a non-conflicting registered alias is submitted
- **THEN** the registry SHALL return the same validated category definition and canonical code

#### Scenario: Registry rejects malformed definitions before serving requests
- **WHEN** definitions contain duplicate codes, conflicting aliases, unsupported types/operators/ranking strategies, invalid enum values, invalid missing strategies, ranking references to absent attributes, or display references to absent attributes
- **THEN** registry construction/startup SHALL fail closed with stable validation issue facts and SHALL not expose a partially registered category set

#### Scenario: Registry has no category fallback
- **WHEN** resolution produces no supported canonical category
- **THEN** the recommendation path SHALL return `category_ambiguous` or `unsupported_category` as applicable and SHALL never select Laptop or another default category

### Requirement: CategoryDefinition SHALL express complete typed category semantics without executable category code

Each definition SHALL express category `code`, `display_name`, aliases, and ordered attribute metadata. Every attribute SHALL declare a key, label, type (`number`, `string`, `enum`, or `boolean`), optional unit and enum values, supported operators (`eq`, `gte`, `lte`, `contains`, `match`, or `enum_match`), constraint role (`hard`, `soft`, `hard_or_soft`, or `display_only`), ranking strategy (`higher_is_better`, `lower_is_better`, `exact_match`, `preference_match`, or `neutral`), missing strategy (`reject_if_hard`, `neutral`, `deterministic_penalty`, or `ignore`), and display order/formatting metadata when needed. Definitions SHALL not embed arbitrary Python or other executable code.

#### Scenario: A new numeric attribute is generic
- **WHEN** a category definition adds `battery_wh` as a numeric attribute with `gte` and `higher_is_better`
- **THEN** the existing parser, constraint engine, and ranking engine SHALL validate, compare, normalize, and display it without recognizing the literal name `battery_wh`

#### Scenario: Attribute metadata is type-safe
- **WHEN** a request or catalog candidate supplies a value of the wrong type or an enum value not listed by the definition
- **THEN** validation SHALL return a bounded typed issue and SHALL not coerce the value into a catalog fact or continue with an unsafe comparison

### Requirement: Generic category resolution SHALL be alias-driven and machine-readable

Resolution SHALL accept structured category intent, validate the candidate code through the registry, and return one of `resolved`, `category_ambiguous`, or `unsupported_category`. Alias vocabulary and collision precedence SHALL come from the registry. An unknown or unsupported category SHALL not silently resolve to Laptop.

#### Scenario: Supported category intent resolves
- **WHEN** structured extraction returns a registered category code or alias
- **THEN** the gate SHALL emit one generic structured-recommendation path with the canonical category code before catalog retrieval

#### Scenario: Conflicting categories are ambiguous
- **WHEN** extraction returns two distinct supported category candidates with no deterministic winner
- **THEN** the result SHALL be `clarification_required` with `error_code=category_ambiguous`, no candidates, and no ranking execution

#### Scenario: Explicit unsupported category fails safely
- **WHEN** extraction returns a category code that is not registered
- **THEN** the result SHALL expose `unsupported_category`, bounded clarification text, and no catalog facts or Laptop fallback

### Requirement: Generic request parsing SHALL be schema-guided and fail closed

The parser SHALL provide the active category schema to a structured extraction layer and SHALL normalize machine-readable attribute constraints into `RecommendationRequest.category_attributes`. It SHALL support typed values, operators, and explicit hard/soft roles, validate all keys and values against the registry, and keep LLM/extractor output separate from catalog facts. Adding a category or attribute that uses existing generic capabilities SHALL not require parser source code changes.

#### Scenario: Camera attribute extraction uses the registry
- **WHEN** a new definition declares `sensor_size` and the extractor returns that key with a typed value
- **THEN** the parser SHALL produce a validated category attribute constraint without a `parse_camera` function or category branch

#### Scenario: Unknown or invalid request attributes fail safely
- **WHEN** extraction returns an unknown key, unsupported operator, wrong type, invalid enum, or an unresolved `hard_or_soft` role
- **THEN** parsing SHALL return a typed clarification/invalid-attribute outcome and SHALL not send the invalid constraint to filtering or ranking

#### Scenario: Extractors cannot create catalog facts
- **WHEN** the extractor mentions a price, stock state, or product specification
- **THEN** that value SHALL remain a request constraint/preference only; canonical Catalog facts SHALL remain authoritative

### Requirement: Generic constraints SHALL filter candidates using definition semantics only

The constraint engine SHALL evaluate generic budget/availability plus category attributes using the active definition. It SHALL implement number comparisons, string equality/contains/match, enum equality/order/enum match, boolean matching, hard/soft roles, cross-category isolation, and deterministic missing-field behavior without checking category codes or attribute names.

#### Scenario: Hard constraints eliminate candidates
- **WHEN** a candidate violates a requested hard `eq`, `gte`, `lte`, `contains`, `match`, or `enum_match` condition, lacks a hard field, exceeds generic budget, or fails required availability
- **THEN** the candidate SHALL be removed before scoring

#### Scenario: Soft constraints remain ranking signals
- **WHEN** a candidate misses or mismatches a soft constraint
- **THEN** it SHALL remain eligible and receive the definition's neutral or deterministic penalty signal

#### Scenario: Cross-category attributes cannot bleed
- **WHEN** a request includes an attribute not declared by the resolved category
- **THEN** the request SHALL fail closed or be explicitly reported as invalid, and the attribute SHALL not affect any candidate score or eligibility

### Requirement: Generic ranking SHALL be bounded, deterministic, and dimensionally safe

The ranking engine SHALL combine bounded signals rather than raw values. For numeric rules it SHALL use declared definition bounds when available; otherwise it SHALL compute min/max from the post-hard-filter candidate snapshot, clamp values to `[0,1]`, and treat a zero-width range deterministically. `higher_is_better` SHALL map `(value-min)/(max-min)` and `lower_is_better` SHALL map `(max-value)/(max-min)`. Exact enum/boolean matches SHALL map to 1 or 0; preference matches SHALL use declared overlap/match semantics; missing values SHALL use the declared missing strategy. Weighted signals SHALL combine into a bounded score with a documented rounding rule, and price SHALL be a hard budget constraint plus deterministic tie-break by default, not an unnormalized score term.

#### Scenario: Equal input is reproducible
- **WHEN** the same request and catalog snapshot are evaluated repeatedly
- **THEN** eligibility, normalized signals, score breakdown, and recommendation order SHALL be identical

#### Scenario: Numeric units do not dominate one another
- **WHEN** candidates contain values such as `5000 mAh`, `16 GB`, `1.2 kg`, and `144 Hz`
- **THEN** each configured rule SHALL contribute its bounded weighted signal rather than its raw magnitude

#### Scenario: Ties use the stable rule
- **WHEN** candidates have equal final scores and price
- **THEN** the engine SHALL order them by ascending `sku_code` after score and price, with SPU de-duplication applied deterministically

### Requirement: Missing semantics SHALL be explicit and observable

The engine and validator SHALL distinguish a missing hard field, missing soft field, invalid request field, and display-only missing field. `reject_if_hard` SHALL make an active candidate ineligible, `neutral` SHALL contribute a fixed neutral signal, `deterministic_penalty` SHALL contribute a definition-declared bounded penalty, and `ignore` SHALL omit the field from scoring without exception. No missing value SHALL be invented from names, prose, RAG, or LLM output.

#### Scenario: Missing required hard catalog field is rejected
- **WHEN** an active candidate omits an attribute required by a hard rule
- **THEN** catalog validation SHALL fail and the recommendation engine SHALL not rank that candidate as eligible

#### Scenario: Missing soft field is stable
- **WHEN** an eligible candidate lacks a soft ranking attribute
- **THEN** the result SHALL contain the documented neutral/penalty breakdown and remain deterministic

### Requirement: Generic result projection SHALL expose declared comparison fields

Recommended results SHALL retain canonical Product/SKU, money, availability, score, evidence, alternatives, and Commerce context while exposing ordered generic `comparison_fields` containing key, label, value, unit, type, display order, and formatting metadata. Projection SHALL use registry/catalog declarations only and SHALL not infer product facts from answer text. A compatibility bridge MAY retain released Laptop fields while the additive generic envelope is adopted.

#### Scenario: Any category projects comparable fields
- **WHEN** a valid candidate is recommended for any registered category
- **THEN** its declared comparison fields SHALL be serializable, ordered, typed, and sufficient for a category-independent renderer

#### Scenario: Malformed projection fails safely
- **WHEN** a stored or streamed recommendation contains an invalid declared field
- **THEN** the existing safe projection-error boundary SHALL be used and no frontend category fallback or prose inference SHALL occur

### Requirement: The first-party frontend SHALL render generic recommendation metadata

The frontend SHALL iterate the result's generic comparison/constraint fields for cards and comparison views. Category-specific React conditionals, copied category pages, and category-name-to-label maps SHALL not be required for ordinary registered categories. Unresolved results SHALL render a bounded generic/clarification state, and SKU selection SHALL continue to require existing recommendation context.

#### Scenario: Test accessory renders without React changes
- **WHEN** a valid `test_accessory` result contains comparison fields
- **THEN** the shared recommendation panel/card/comparison UI SHALL render the fields by metadata iteration without a category conditional

#### Scenario: Existing Laptop and Monitor UI remains consumable
- **WHEN** released Laptop or Monitor results are rendered during migration
- **THEN** the UI SHALL preserve cards, comparison, evidence, alternatives, and SKU selection through the generic envelope or compatibility bridge

### Requirement: Registry-backed catalog validation SHALL cover data and documents

The validator SHALL automatically validate every registered category's supported code, attribute keys, types, enum values, required hard fields, canonical Product/SKU relationships, money, inventory, and document identity. Adding a category SHALL not require adding a category branch to validator source code.

#### Scenario: Router data is validated from its definition
- **WHEN** `router.json` and Router catalog/document fixtures are supplied
- **THEN** the validator SHALL discover and validate Router using the registry without a new `if category` block

#### Scenario: Invalid data is rejected deterministically
- **WHEN** a catalog row has an unknown attribute, wrong type, invalid enum, missing hard field, invalid money/inventory, duplicate identity, or missing document
- **THEN** validation SHALL fail with stable issue code/path/detail ordering

### Requirement: Recommendation expansion SHALL preserve Commerce, Agent, RAG, and runtime boundaries

The generic engine SHALL output canonical SKU identity and SHALL not modify the existing `SKU → PendingAction → expected_version → canonical Cart` boundary. Read Agents SHALL remain read/intent-only; RAG SHALL remain enrichment; Chat error projection, retry/idempotency, run identity, confirmation, and cancellation semantics SHALL remain unchanged.

#### Scenario: Generic recommendation enters existing HITL
- **WHEN** a user selects a `test_accessory`, Laptop, Monitor, or future ordinary SKU
- **THEN** the system SHALL prepare/confirm/cancel through the existing PendingAction and canonical Cart path, with no direct Agent write

#### Scenario: Retry recovery remains authoritative
- **WHEN** the same Chat idempotency key is retried around a generic recommendation or PendingAction
- **THEN** the existing authoritative Run/PendingAction result SHALL be recovered and no second execution or mutation SHALL be created

### Requirement: The architecture proof SHALL demonstrate no-core-code category addition

The acceptance suite SHALL define `test_accessory` only through a category definition fixture, catalog Product/SKU/document fixture, and tests. The fixture SHALL execute registry resolution, typed attribute validation, generic hard filtering, deterministic ranking, generic result projection, and the existing Commerce context without modifying Gate, Parser, Recommendation service, constraint engine, ranking engine, Agent graph, or frontend production code.

#### Scenario: Test accessory completes the full path
- **WHEN** the architecture-proof fixture is run against a fixed candidate snapshot and request
- **THEN** it SHALL resolve the category, validate attributes, eliminate hard failures, rank remaining candidates, and expose typed comparison fields and canonical SKU identity

#### Scenario: New attribute remains name-agnostic
- **WHEN** the fixture adds a numeric `battery_wh` attribute using existing generic semantics
- **THEN** the generic engine SHALL work without a literal `battery_wh` reference in production code
