## MODIFIED Requirements

### Requirement: Recommendation categories SHALL resolve to a machine-readable supported outcome

The structured recommendation gate SHALL resolve reliable category intent through the server-owned CategoryRegistry before candidate retrieval. The formally managed electronics set SHALL include Laptop, Monitor, Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, and Router. Registered aliases SHALL resolve to canonical codes; ambiguous intent SHALL produce `clarification_required` with `category_ambiguous`; an explicitly named unregistered category SHALL produce `unsupported_category`. No unsupported or ambiguous request SHALL default to Laptop.

#### Scenario: Explicit Laptop intent resolves to Laptop
- **WHEN** a recommendation request explicitly names a laptop/notebook or matches the Laptop definition's registered aliases and constraints
- **THEN** the gate SHALL return a machine-readable Laptop structured recommendation decision and the shared pipeline SHALL use the generic engine

#### Scenario: Explicit registered category resolves
- **WHEN** a request identifies a registered Laptop, Monitor, or future category by canonical code or alias
- **THEN** the gate SHALL return one generic structured recommendation decision containing the canonical code and SHALL use the shared pipeline

#### Scenario: Explicit Monitor intent resolves to Monitor
- **WHEN** a recommendation request explicitly names a monitor/display and contains recommendation intent
- **THEN** the gate SHALL return a machine-readable Monitor structured recommendation decision and SHALL not route the request through Laptop semantics

#### Scenario: Each new electronics category resolves
- **WHEN** a request explicitly identifies Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, or Router through a registered alias/code
- **THEN** the gate SHALL return the canonical Registry code and the generic structured recommendation path

#### Scenario: Ambiguous category requests clarification
- **WHEN** a request contains no reliable category or conflicting registered category signals
- **THEN** the structured result SHALL be `clarification_required` with `category_ambiguous`, no catalog retrieval, and no Laptop fallback

#### Scenario: Unsupported category fails safely
- **WHEN** a request explicitly names a category not present in the Registry, such as Printer before it is registered
- **THEN** the structured result SHALL expose `unsupported_category`, bounded clarification text, and no fabricated catalog facts
