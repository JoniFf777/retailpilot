## Purpose

This capability defines how additional ordinary electronics categories become managed, testable, deterministic recommendations through the existing CategoryRegistry and Catalog data contracts without category-specific recommendation implementation.

## ADDED Requirements

### Requirement: Electronics categories SHALL be onboarded through Registry definitions and managed data only

Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, and Router SHALL be registered by trusted CategoryDefinition files and managed Catalog Product/SKU/document data. Their ordinary recommendation behavior SHALL use existing generic primitives; no category-specific Python policy, graph branch, validator branch, or React renderer branch SHALL be required.

#### Scenario: Ten registered categories are discoverable
- **WHEN** the trusted definition directory is loaded after the eight definitions are added
- **THEN** Registry discovery SHALL return Laptop, Monitor, Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, and Router with canonical codes and display metadata

#### Scenario: Future Printer onboarding remains data-only
- **WHEN** a future Printer definition/data/document/test set uses existing generic capabilities
- **THEN** the expected changes SHALL be limited to a Printer definition, Catalog/data/document inputs, and tests

#### Scenario: No category-specific production branch is needed
- **WHEN** any of the eight new categories is resolved or ranked
- **THEN** the existing generic gate, parser, constraints, ranking, service, graph, validator, and frontend renderer SHALL be used unchanged

### Requirement: Each managed electronics category SHALL have factual and sufficiently varied Catalog coverage

Each new category SHALL have managed canonical Product/SKU data with multiple price bands, available candidates, at least one unavailable/out-of-stock candidate, hard no-match coverage, soft preference differences, an intentionally missing optional soft field, deterministic tie-break inputs, and declared comparison fields. Exact Product/SKU counts SHALL remain data/report facts rather than permanent business requirements.

#### Scenario: Category data passes Registry-driven validation
- **WHEN** the eight new catalog files are validated
- **THEN** every supported category, attribute key/type/enum, required hard field, Product/SKU identity, money, inventory, and matching document SHALL pass with deterministic zero issues

#### Scenario: Catalog remains factual authority
- **WHEN** a document or request text conflicts with Catalog price, inventory, SKU, category, or structured attribute
- **THEN** recommendation output SHALL retain the canonical Catalog fact and use documents only as evidence/explanation

#### Scenario: Optional soft data may be missing safely
- **WHEN** a candidate omits a definition-declared optional soft attribute
- **THEN** validation and ranking SHALL apply the declared neutral/penalty/ignore semantics without fabricating a value

### Requirement: Every new electronics category SHALL have generic recommendation coverage

Each new category SHALL be covered by deterministic tests for resolution, aliases, budget, hard constraints, soft ranking, availability, no-match, missing-soft behavior, deterministic ordering, and structured comparison fields. At least three new categories SHALL run through the complete Agent recommendation path.

#### Scenario: New category resolves without Laptop fallback
- **WHEN** a Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, or Router request is submitted
- **THEN** Registry resolution SHALL return its canonical code and unknown/ambiguous/unsupported requests SHALL retain typed outcomes without Laptop fallback

#### Scenario: Cross-category request attributes fail closed
- **WHEN** a request supplies an attribute belonging to another category
- **THEN** the generic request boundary SHALL reject or safely report the invalid field and SHALL not alter filtering, ranking, or comparison output

#### Scenario: Agent path works for representative categories
- **WHEN** representative Phone, Keyboard, and Router requests run through the existing multi-agent graph
- **THEN** each SHALL retrieve canonical candidates, rank them generically, project comparison fields, and preserve RAG enrichment ordering

### Requirement: New electronics recommendations SHALL preserve Commerce and HITL boundaries

Recommendations for new categories SHALL output canonical SKU identity and SHALL use the existing recommendation-context → PendingAction → expected_version → canonical Cart flow. Agents and LLMs SHALL not directly mutate Cart or infer SKU identity from product prose.

#### Scenario: Phone recommendation reaches existing HITL
- **WHEN** a user selects a Phone recommendation for add-to-cart
- **THEN** the existing PendingAction and expected-version confirmation path SHALL be used before one canonical Cart mutation

#### Scenario: Router recommendation reaches existing HITL
- **WHEN** a user selects a Router recommendation for add-to-cart
- **THEN** the existing canonical SKU, owner/thread, expected-version, confirmation, and Cart boundary SHALL remain authoritative

#### Scenario: New category does not write directly
- **WHEN** any new category recommendation is processed
- **THEN** no Agent/recommendation code SHALL directly write Cart, use a legacy Cart fallback, or guess SKU from a name

### Requirement: Expansion SHALL prove unchanged generic implementation

The Change SHALL compare Apply-before baseline and final worktree for recommendation core, graph/nodes, frontend recommendation renderer, validator generic core, and existing Laptop/Monitor data. Except for an explicitly documented data-index/seed-discovery adjustment, those paths SHALL remain unchanged.

#### Scenario: Core implementation remains unchanged
- **WHEN** the final architecture guard compares baseline and final paths
- **THEN** gate, request parser, constraints, ranking, service, compatibility, Registry core, graph/nodes, frontend renderer, validator core, and existing Laptop/Monitor data SHALL have no Change-specific modifications

#### Scenario: No ordinary category branch exists
- **WHEN** production recommendation and renderer sources are scanned
- **THEN** no `if category == <new category>`, `if key == <new attribute>`, or equivalent category-specific branch SHALL be present
