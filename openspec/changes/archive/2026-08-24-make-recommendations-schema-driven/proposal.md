## Why

The released `v3.1.0` recommendation path is shared at the orchestration level, but its category boundary is still closed over Laptop and Monitor. Category names, aliases, request extraction, constraint semantics, scoring, validator completeness, graph fallbacks, and frontend conditionals are maintained in separate places. As a result, adding a normal category such as Router would require editing recommendation production code and would risk changing the Commerce/HITL boundary.

This change defines the next-version architecture for a schema-driven generic recommendation engine. A trusted, typed `CategoryRegistry` becomes the only category source of truth; a generic parser, constraint evaluator, normalizer/ranker, catalog validator, result projection, and frontend renderer consume that definition. The design preserves the released `v3.1.0` behavior and tag while making a new ordinary category data/configuration work a no-core-code change.

## What Changes

- Add a new `recommendation-schema-engine` capability with a typed `CategoryDefinition` model and fail-fast `CategoryRegistry`.
- Store trusted category definitions declaratively as packaged JSON/YAML validated by Pydantic; do not dynamically load user code or introduce a plugin framework.
- Move aliases, attribute types, enum values, operators, constraint roles, ranking strategies, missing-value semantics, and display metadata into the registry.
- Replace category-name branches in resolution, parsing, filtering, ranking, graph candidate retrieval, and validation with registry-driven generic operations.
- Define deterministic bounded numeric normalization and match scoring with explicit weights, missing-value handling, candidate-snapshot rules, and `(-score, price, sku_code)` tie-breaking.
- Project category fields as generic machine-readable `comparison_fields`/declared specifications so the React recommendation UI iterates metadata rather than branching on category names.
- Migrate Laptop and Monitor behavior into registry definitions and generic engine rules. Retain only narrowly documented compatibility adapters for released fields/heuristics that cannot yet be represented declaratively.
- Add an architecture-proof fixture for `test_accessory` that adds only a category definition, catalog fixture, documents, and tests, then resolves, validates, filters, ranks, and projects a result.
- Generalize the catalog validator to read the registry for supported categories, types, enums, hard-field completeness, canonical identity, money, inventory, and document identity.
- Preserve canonical SKU output, `PendingAction`, `expected_version`, Cart service, Agent read/write permissions, RAG enrichment semantics, Chat error boundaries, and retry/idempotency semantics.
- Produce no product-data expansion in this Change. Bulk categories and catalog rows belong to a later independent data Change.

## Capabilities

### New Capabilities

- `recommendation-schema-engine`: Generic category registry, typed definitions, schema-driven parsing, generic constraints/ranking, category-independent result projection, and architecture-proof acceptance contract.

### Modified Capabilities

- `recommendation-categories`: Replace the closed Laptop/Monitor category contract with registry-backed resolution and generic category attributes while preserving safe ambiguous/unsupported outcomes and existing Laptop/Monitor compatibility.
- `catalog-recommendation-data-quality`: Make completeness and type validation registry-driven instead of maintaining a category-name-to-required-fields map.
- `release-readiness`: Require registry validation, fail-fast startup/configuration checks, generic frontend rendering, and no category fallback in readiness evidence.

The following existing capabilities are compatibility constraints, not modified requirements in this Change: `commerce-cart`, `agent-write-hitl`, `chat-error-boundaries`, and `chat-retry-idempotency`.

## Impact

- Proposed backend implementation areas: `app/recommendation/categories/`, `app/recommendation/registry.py`, `app/recommendation/parser.py`, `app/recommendation/constraints.py`, `app/recommendation/ranking.py`, `app/recommendation/service.py`, `app/recommendation/gate.py`, `app/recommendation/providers.py`, `app/schemas/recommendation.py`, `app/repositories/catalog.py`, and `scripts/validate_shopmind_catalog.py`.
- Proposed declarative inputs: `categories/laptop.json`, `categories/monitor.json`, and future `categories/router.json`; existing catalog products/SKUs and documents remain separate data inputs.
- Proposed graph change: consume a resolved registry category and call one generic recommendation path; no category-specific graph nodes.
- Proposed frontend change: consume generic field metadata from the public recommendation result and render fields by iteration. The generated OpenAPI type will be regenerated only if the additive public contract requires it.
- Proposed tests: registry validation, parser contract, generic constraints/ranking, `test_accessory` architecture proof, Laptop/Monitor regression, catalog validation, public contract/OpenAPI, graph, Commerce/HITL, Chat retry/error, and frontend rendering tests.
- No production, tests, frontend, catalog data, main specs, tag, commit, push, or deployment is changed by this planning round. The active Change contains planning artifacts and review evidence only.
