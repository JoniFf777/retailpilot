## MODIFIED Requirements

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

#### Scenario: Registered candidate passes definition validation
- **WHEN** an active candidate contains all required attributes with valid types and enum values
- **THEN** the validator SHALL accept its category-scoped attributes

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

#### Scenario: Document conflicts do not override Catalog
- **WHEN** document prose conflicts with a canonical Catalog fact
- **THEN** validation/recommendation output SHALL retain the Catalog fact and treat prose only as evidence
