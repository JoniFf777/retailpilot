## Purpose

This capability makes backend Agent execution and specialist failure reporting truthful and deterministic across production thread boundaries and local non-integration test environments.

## ADDED Requirements

### Requirement: Synchronous Agent work SHALL remain isolated from the asynchronous HTTP event loop

The Chat HTTP boundary SHALL execute synchronous Agent work outside the asynchronous event loop. Database Sessions and other thread-affine resources used by that work SHALL be created, used, and closed within the owning execution context; a caller or test SHALL NOT share one live Session object across execution threads.

#### Scenario: Chat keeps the event loop responsive

- **WHEN** a synchronous Agent execution takes longer than one normal request turn
- **THEN** the Chat route SHALL keep the event loop available for unrelated lightweight requests while the Agent execution continues

#### Scenario: SQLite test execution uses owned Sessions

- **WHEN** a Chat test injects an SQLite-backed session boundary and the route executes the Agent in a worker context
- **THEN** the request SHALL complete without SQLite thread-affinity errors, and the fixture SHALL be able to close its inspection resources on the test thread

#### Scenario: Session failure does not change production thread policy

- **WHEN** a session/thread regression is detected
- **THEN** the fix SHALL repair resource ownership or dependency injection rather than removing the production worker boundary or relying on a global shared Session

### Requirement: Actual RAG tool failures SHALL be distinguishable from successful RAG execution

An RAG tool invocation that raises an exception or returns an invalid tool result SHALL NOT be represented as a successful RAG specialist result. The failure SHALL remain observable through the typed specialist/plan execution contract and SHALL contain a bounded, non-sensitive failure classification.

#### Scenario: RAG tool raises during a parallel read plan

- **WHEN** Product or Preference reads complete and the RAG tool raises
- **THEN** the RAG step SHALL be `failed`, the plan SHALL be `partial`, and the merged state SHALL omit a fabricated successful `rag_summary`

#### Scenario: RAG tool raises with no independent successful read

- **WHEN** the RAG step is required and no independent read step produces usable output
- **THEN** the execution SHALL be reported as failed or insufficient according to the existing runtime terminal contract, and SHALL NOT report the RAG step as completed

#### Scenario: RAG result violates its output contract

- **WHEN** an RAG adapter receives output that does not satisfy the typed public specialist contract
- **THEN** the adapter SHALL return a typed validation failure classification and SHALL NOT promote the result to completed

### Requirement: Intentional pre-invocation RAG unavailability SHALL use explicit degraded semantics

When the RAG specialist is intentionally disabled, has no configured tool, or is known unavailable before any tool invocation, the system SHALL distinguish that state from successful RAG execution and from an actual tool execution failure. Degraded output SHALL not invent citations or imply that a tool completed. The `degraded` semantic SHALL NOT be used after an actual RAG tool invocation raises an exception.

#### Scenario: RAG is disabled by the local profile

- **WHEN** the server deliberately constructs the graph without RAG tools
- **THEN** the RAG summary SHALL be typed as `degraded`, identify a bounded disabled/unavailable reason, and contain no citations attributed to a tool call

#### Scenario: RAG has no configured tool

- **WHEN** the RAG specialist has no configured tool before execution begins
- **THEN** the specialist SHALL return a typed `degraded` summary with a bounded reason, empty citations, and no tool-call claim

#### Scenario: Actual RAG invocation failure is not degraded

- **WHEN** an actual RAG tool invocation raises after execution begins
- **THEN** the specialist SHALL be `failed` and the result SHALL NOT be represented as `degraded` or `completed`

### Requirement: Backend regression validation SHALL prove both focused and suite-level correctness

The project SHALL provide deterministic validation for the Chat Session boundary, RAG failure semantics, partial fan-in, and the complete non-integration backend suite. Validation SHALL run with LangSmith tracing disabled and SHALL NOT require LangSmith, Redis, RocketMQ, PostgreSQL integration services, or external APIs.

#### Scenario: Focused regression tests pass

- **WHEN** the directly affected Chat write-handoff and parallel RAG tests are run with the local Python environment
- **THEN** all selected tests and teardown paths SHALL pass with zero failures and zero errors

#### Scenario: Full non-integration backend suite passes

- **WHEN** the full backend suite is run while integration tests are excluded and the pytest temporary directory is writable
- **THEN** the run SHALL report zero failed tests and zero errors

#### Scenario: Validation does not require external services

- **WHEN** the change validation is executed under `LANGSMITH_TRACING=false`
- **THEN** it SHALL not contact LangSmith, Redis, RocketMQ, PostgreSQL integration targets, or other external paid/API services
