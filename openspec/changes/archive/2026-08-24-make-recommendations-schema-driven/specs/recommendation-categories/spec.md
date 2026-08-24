## MODIFIED Requirements

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

### Requirement: Category policies SHALL isolate hard constraints, soft ranking, and missing attributes

Each registered category SHALL use the generic recommendation engine and its CategoryDefinition for attributes, operators, hard/soft roles, ranking strategies, missing semantics, and display metadata. A category-specific custom scorer or policy SHALL not be the standard path for ordinary categories; a future extension hook is allowed only for a reusable generic capability and is outside this Change's ordinary-category contract.

#### Scenario: Laptop and Monitor use generic semantics
- **WHEN** Laptop and Monitor requests are evaluated with their existing candidate snapshots
- **THEN** their behavior SHALL be represented by definitions and generic operators/ranking strategies, with released compatibility projections where required

#### Scenario: Ordinary category needs no policy source edit
- **WHEN** a valid Router definition uses existing generic capabilities
- **THEN** adding Router SHALL not require a new Router policy/scorer class or edits to generic engine source

#### Scenario: Hard constraints eliminate candidates
- **WHEN** a candidate violates an explicitly requested category hard constraint, generic budget, required availability, or active sale status
- **THEN** the candidate SHALL be excluded before scoring and SHALL not appear in the structured Top K

#### Scenario: Soft preferences rank without eliminating all candidates
- **WHEN** a candidate lacks or does not match a soft category preference
- **THEN** the generic engine SHALL apply a deterministic neutral/penalty score and SHALL not reject every candidate solely for a soft mismatch

#### Scenario: Missing hard and soft attributes are deterministic
- **WHEN** a candidate lacks a required hard attribute or a soft ranking attribute
- **THEN** a missing hard attribute SHALL make the candidate ineligible, while a missing soft attribute SHALL receive the documented neutral/penalty behavior without exception, random ordering, or LLM inference

### Requirement: Laptop policy SHALL preserve existing structured behavior

The migration SHALL preserve released Laptop/Monitor canonical SKU, availability, budget, hard-filter, deterministic-order, evidence, alternatives, and Commerce/HITL behavior. Generic comparison fields SHALL be additive or bridged so existing clients can continue consuming released result fields until the public migration is complete.

#### Scenario: Existing Laptop behavior remains stable
- **WHEN** the same Laptop request and catalog snapshot are evaluated before and after migration
- **THEN** hard eligibility, stable ordering, SPU de-duplication, alternatives, and canonical SKU identity SHALL remain equivalent within the documented compatibility projection

#### Scenario: Monitor does not receive Laptop semantics
- **WHEN** a Monitor request is evaluated
- **THEN** Laptop CPU/GPU/memory/storage/weight heuristics SHALL not affect its filtering or score

#### Scenario: Existing Laptop hard constraints still filter
- **WHEN** a Laptop request specifies the existing budget, memory, storage, weight, CPU, GPU, screen, or use-case constraints
- **THEN** the generic definition-driven engine SHALL preserve the existing deterministic eligibility behavior and structured result semantics

#### Scenario: Existing Laptop ranking and alternatives remain stable
- **WHEN** the same Laptop candidates and constraints are supplied as before
- **THEN** the generic engine SHALL preserve the existing score ordering, stable tie-break, SPU de-duplication, and alternative-SKU behavior

#### Scenario: Laptop heuristics do not affect Monitor ranking
- **WHEN** a Monitor request is ranked
- **THEN** CPU/GPU/memory/storage/weight Laptop fields and Laptop use-case heuristics SHALL not contribute to Monitor eligibility or score
