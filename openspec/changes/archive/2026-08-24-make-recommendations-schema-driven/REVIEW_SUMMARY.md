# make-recommendations-schema-driven — Proposal Review Summary

Review date: 2026-08-24 (Asia/Shanghai)

Scope: planning-only OpenSpec Change for the next version after released `v3.1.0`.

## 1. Current category coupling

The current implementation has shared candidate retrieval, evidence, SPU de-duplication, and React specification/comparison components, but category semantics are duplicated across the gate, parser, service, graph, validator, OpenAPI, and UI. The detailed matrix is in `CURRENT_CATEGORY_COUPLING.md`.

Current hardcoded examples include:

- `app/recommendation/gate.py`: Laptop/Monitor term lists, Laptop hint inference, category-specific modes, unsupported list, and Laptop-oriented fallback text.
- `app/recommendation/request.py` and `constraints.py`: Monitor model/parser branch and Laptop parser/model branch.
- `app/recommendation/service.py`: Laptop tier map/scorer, Monitor resolution map/scorer, named attribute lookups, and category branches.
- `agents/shopmind_multi_agent/recommendation_nodes.py`: category mode sets, `or "laptop"` fallback, category-specific clarification.
- `scripts/validate_shopmind_catalog.py`: `REQUIRED_ATTRIBUTES` category map and Monitor enum branch.
- React recommendation components: Monitor/Laptop conditionals and named constraint fields.
- Generated OpenAPI: closed `laptop | monitor | unknown` unions and Laptop-shaped constraints.

## 2. New-category current production impact

Adding an ordinary third category today requires approximately 10–11 production locations, excluding its catalog/product-document data: recommendation schema, gate, request/parser, constraints/service, graph nodes, provider/repository integration, catalog validator, frontend constraint panel/card, and generated public contract. Tests are expected additional changes and are not counted as undesirable coupling. The exact current locations and reasons are enumerated in `CURRENT_CATEGORY_COUPLING.md`.

## 3. Proposed final architecture

```text
trusted CategoryDefinition files
          ↓
typed CategoryRegistry (single source of truth; fail-fast)
          ↓
category resolution → schema-guided parser → typed RecommendationRequest
          ↓
canonical catalog candidates → generic hard constraints
          ↓
bounded generic ranking/normalization → deterministic top-K/SPU projection
          ↓
generic comparison_fields + canonical SKU + RAG enrichment
          ↓
shared frontend → existing PendingAction/HITL → canonical Cart
```

One `GenericRecommendationEngine` is the ordinary path. There is no default PhonePolicy/RouterPolicy family and no dynamic plugin code.

## 4. CategoryRegistry

The Registry owns canonical code lookup, normalized aliases, definition validation, typed attribute schema, enum values/order, operators, roles, ranking/missing semantics, display metadata, and supported-category discovery. Gate, parser, engine, graph, validator, and result projection consume it. Catalog database attribute rows are projections checked against the registry; React consumes returned metadata and does not maintain category lists.

Fail-fast checks cover duplicate code, conflicting alias, malformed attribute, unsupported type/operator/ranking, invalid enum, invalid missing strategy, invalid weight/bounds, dangling ranking reference, and dangling display reference.

## 5. CategoryDefinition schema

The selected storage is trusted declarative JSON (YAML only if an established repository convention requires it) loaded into typed Pydantic models. A definition contains:

- category `code`, `display_name`, aliases, and definition/version metadata;
- attributes: key, label, type (`number`, `string`, `enum`, `boolean`), unit, enum values/order, allowed operators, constraint role, ranking strategy, missing strategy, weight/bounds, display order, comparable flag, and bounded formatting hint;
- generic vocabulary: `eq`, `gte`, `lte`, `contains`, `match`, `enum_match`; `hard`, `soft`, `hard_or_soft`, `display_only`; `higher_is_better`, `lower_is_better`, `exact_match`, `preference_match`, `neutral`; `reject_if_hard`, `neutral`, `deterministic_penalty`, `ignore`.

Definitions contain no executable expressions, callbacks, imports, arbitrary user code, or custom ordinary-category scorer.

## 6. Generic parsing

One parser receives the active category schema and emits a bounded machine-readable extraction envelope. Registry metadata supplies keys, types, units, enum aliases, and operators. It validates output before candidate retrieval; an LLM may extract request intent but cannot create Catalog facts. Adding `camera.sensor_size`, `router.wifi_standard`, or `battery_wh` uses the existing parser loop and does not require `parse_camera`/`parse_router` code.

## 7. Generic constraints

Hard filtering runs before scoring. Number operators compare Decimal values; strings support normalized equality/contains/match; enums support equality, declared order, and scalar/multi-value match; booleans use exact match. Wrong type, unknown key, unsupported operator, cross-category key, or unresolved hard/soft role fails safely. Missing hard fields reject; missing soft fields use neutral, deterministic penalty, or ignore from the definition.

## 8. Ranking normalization

Numeric signals use declared bounds or deterministic post-hard-filter snapshot bounds, clamp to `[0,1]`, and apply:

```text
higher: (x - min) / (max - min)
lower:  (max - x) / (max - min)
```

Exact enum/boolean matches are 1/0; preference match uses declared overlap/match semantics; neutral is 0.5; deterministic penalty is a definition-declared bounded signal. The combined score is `ROUND_HALF_UP(100 * weighted_signal_sum / active_weight_sum)`, clamped to 0–100. Price is a hard budget constraint and default tie-break input, not a raw score term. Final order is `(-score, price, sku_code)` with deterministic SPU de-duplication and alternatives.

## 9. Missing semantics

Missing hard, missing soft, invalid request, and display-only missing states are distinct. No missing Catalog value is inferred from product name, prose, RAG, or LLM output. Validator and engine report deterministic bounded facts.

## 10. Frontend generic rendering

The result adds generic ordered `comparison_fields` with key, label, value, type, unit, display order, comparable, and bounded formatting metadata. Cards, constraints, and comparison iterate these fields. Laptop/Monitor compatibility fields may remain during migration, but the standard renderer has no category list, copied page, or `category === "phone"` branch. Null/unknown/unresolved categories stay generic/clarification/projection-error states and never become Laptop.

## 11. Laptop migration

CPU/GPU tier order, memory/storage minimums, weight maximum, screen equality, multi-valued use cases, aliases, weights, and display metadata are declaratively expressible. The generic engine should replace the named Laptop scorer. A small compatibility projection may preserve released Laptop-shaped fields and stable public behavior; retaining a full LaptopPolicy is rejected.

## 12. Monitor migration

Size minimum, ordered resolution, refresh minimum, panel preference, multi-valued use cases, missing semantics, clarification metadata, and display fields are declaratively expressible. The generic engine should replace the named Monitor scorer. Laptop heuristics must not affect Monitor. A full MonitorPolicy is rejected.

## 13. Architecture proof test

`ARCHITECTURE_PROOF.md` defines a test-only `test_accessory` with `battery_wh`, enum, boolean, catalog/SKU/document fixtures, and assertions for resolve → validate → filter → rank → generic projection → canonical SKU/context. It must require no production edit to Gate, Parser, service, constraints, ranking, graph, validator, or frontend. It includes a source/AST guard against literal `battery_wh` or category-specific branches.

## 14. Future Router expected files

```text
categories/router.json
data/catalog/router_catalog.json
data/documents/products/<Router document ids>.md
tests/.../router fixtures and regression tests
```

No core recommendation or React production file should change for an ordinary Router definition that uses existing generic semantics.

## 15. Specialized policies

Not required for ordinary categories and explicitly not the default architecture. A future extension hook is acceptable only when it adds a reusable generic operator/ranking capability shared by multiple categories; it cannot be a per-category custom scorer in this Change.

## 16. Public schema impact

Additive generic comparison fields and typed category attributes are planned. Released Laptop-compatible fields remain during migration. OpenAPI/generated frontend types will be regenerated only if the additive envelope requires it; generated files are never hand-edited. Commerce/HITL, Chat, retry/idempotency, RAG, and safe-error boundaries remain unchanged.

## 17. Proposed implementation files

See `design.md` and `tasks.md`. Main proposed areas are `app/recommendation/categories/`, registry/parser/constraints/ranking/service/gate/provider modules, recommendation schemas, catalog repository/validator, one generic graph path, shared React recommendation components, generated OpenAPI, and focused regression/architecture tests. No production implementation is included in this planning round.

## 18. Proposed tests

Registry validation; alias resolution; ambiguous/unsupported/no-fallback; schema-guided extraction; all operators and types; missing semantics; numeric normalization; deterministic ties; Laptop/Monitor golden regression; cross-category isolation; validator/data-document alignment; generic JSON/SSE/OpenAPI projection; graph/RAG; Commerce/HITL; Chat error/retry/replay; frontend `test_accessory`; source/AST no-mud-ball guard; full backend/frontend readiness suites.

## 19. Requirements / Scenarios / Tasks

The active Change contains:

- new `recommendation-schema-engine` spec with 12 requirement areas covering Registry, definitions, resolution, parsing, constraints, ranking, missing semantics, projection, frontend, validator, boundaries, and proof;
- modified deltas for `recommendation-categories`, `catalog-recommendation-data-quality`, and `release-readiness`;
- `tasks.md` with 11 dependency-ordered groups covering all Apply work, validation, and regression gates.

## 20. Risks

Main risks are Laptop score/order drift, schema-mud growth, candidate-snapshot normalization sensitivity, public OpenAPI compatibility, invalid LLM extraction, Registry/catalog drift, and accidental category fallback. Mitigations are golden snapshots, closed typed vocabulary, bounded declarative definitions, fail-fast validation, Catalog authority, generated contracts, source guards, and the architecture proof.

## 21. Remaining uncertainties

No architectural uncertainty blocks Apply. Exact JSON property spelling and final opaque-vs-generated category typing are bounded implementation details; they must remain additive and preserve the no-core-code proof.

## 22. Strict validation

Passed on 2026-08-24:

```text
openspec validate make-recommendations-schema-driven --type change --strict --no-interactive
→ Change 'make-recommendations-schema-driven' is valid

openspec validate --specs --strict --no-interactive
→ 9 passed, 0 failed
```

## 23. Ready For Apply

**Yes — planning-only.** The active Change is complete and reviewable. This does not claim implementation/runtime tests have passed; Apply is intentionally not performed in this round.

## 24. Git status

At review time:

```text
## main...origin/main
?? openspec/changes/make-recommendations-schema-driven/
```

`HEAD` is `d8d7e5f50c173d120eb19a9e35d3059fe363c794`. The existing `v3.1.0` tag resolves to `f6f37f7404acc17a798392d6977b4b1f07e9c3c3`; it was not moved or modified. No commit, push, tag, release, Sync, Archive, or Apply was run.

## Review ZIP contents

The ZIP includes the complete active Change, this summary, `CURRENT_CATEGORY_COUPLING.md`, `ARCHITECTURE_PROOF.md`, `READINESS_SELF_REVIEW.md`, key recommendation schema/parser/gate/service/provider/repository/graph source, frontend recommendation components and contracts, catalog validator, and representative recommendation/catalog/frontend tests. Existing source files are copied for review only; they are not modified by this Change.
