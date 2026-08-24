## MODIFIED Requirements

### Requirement: Managed attributes SHALL satisfy category policy completeness and type rules

Every active managed recommendation candidate in every Registry-discovered electronics category SHALL provide attributes required by its CategoryDefinition with valid declared types and enum values. Hard-required fields SHALL be present; optional soft fields MAY be absent only when their definition declares deterministic missing semantics. Validator logic SHALL remain category-independent.

#### Scenario: All ten categories pass definition validation
- **WHEN** managed Laptop, Monitor, Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, and Router seed rows are validated
- **THEN** every hard-required field SHALL have the declared type and every enum value SHALL be valid

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

#### Scenario: Missing hard field fails validation
- **WHEN** an active managed candidate omits a required hard attribute or uses the wrong type
- **THEN** validation SHALL fail with deterministic category/attribute issue facts and recommendation code SHALL not guess a value

#### Scenario: Missing optional soft field is allowed deterministically
- **WHEN** an active candidate omits a definition-declared optional soft field
- **THEN** validation SHALL allow it and recommendation ranking SHALL use the definition's missing semantics

### Requirement: Managed Catalog data SHALL cover deterministic recommendation scenarios

Managed electronics fixtures SHALL cover meaningful price bands, available candidates, unavailable candidates, hard no-match cases, soft preference differences, missing optional soft fields, stable tie-break inputs, and declared comparison fields for each new category. Exact item counts SHALL remain data/report facts.

#### Scenario: New category coverage is meaningful
- **WHEN** a new category fixture set is evaluated
- **THEN** it SHALL expose multiple deterministic recommendation outcomes including recommended, no-match, unavailable filtering, soft preference ordering, and stable ties

#### Scenario: Laptop demo coverage is meaningful
- **WHEN** the Laptop fixture set is evaluated
- **THEN** it SHALL include value, development, portable, gaming/performance, memory/storage, strict-budget no-match, and unavailable-filtering cases

#### Scenario: Monitor demo coverage is meaningful
- **WHEN** the Monitor fixture set is evaluated
- **THEN** it SHALL include office, high-refresh gaming, high-resolution, size, panel, strict-budget no-match, and unavailable-filtering cases

#### Scenario: Close candidates remain deterministically ordered
- **WHEN** multiple eligible candidates have equal or near-equal generic scores
- **THEN** the deterministic ranking and stable tie-break SHALL produce the same result order on repeated evaluation

#### Scenario: Existing managed categories remain valid
- **WHEN** the validator discovers the expanded catalog set
- **THEN** existing Laptop and Monitor data SHALL remain valid with no required product/document rewrite
