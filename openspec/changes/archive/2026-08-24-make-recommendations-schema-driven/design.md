## Context

See `proposal.md` and `CURRENT_CATEGORY_COUPLING.md` for motivation and the current code audit. The important starting facts are: the current catalog repository already accepts a category code, the public result already carries a loose `category_attributes` map and declared Product specifications, but `gate.py`, `request.py`, `service.py`, graph nodes, the validator, generated OpenAPI, and React constraints/card presentation still enumerate Laptop/Monitor behavior independently.

The design must preserve the released `v3.1.0` contract and its immutable tag. It must also preserve the existing `SKU → PendingAction → expected_version → canonical Cart` boundary and the runtime contracts described by the existing commerce, HITL, Chat error, and Chat retry specifications.

## Goals / Non-Goals

**Goals:**

- Make ordinary category addition a declarative definition + catalog/SKU + documents + tests operation.
- Make category resolution, request extraction, constraint evaluation, ranking, validation, result projection, and rendering consume one registry contract.
- Keep generic engine behavior name-agnostic and deterministic.
- Migrate Laptop and Monitor behavior into declarative definitions wherever existing generic primitives can express it.
- Make the architecture proof mechanically enforce “no Gate/Parser/Ranking/Service/Graph/React production edit for `test_accessory`”.
- Keep public compatibility additive and make any OpenAPI change explicit and generated.

**Non-Goals:**

- No batch addition of Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, Router, or bulk products in this Change.
- No payment/order/cart/HITL redesign, direct Agent writes, RAG platform redesign, localization, auth, Redis/RocketMQ, deployment, or release/tag operation.
- No arbitrary user-supplied definition paths, imports, expressions, callbacks, custom scorer classes, or dynamic code execution.
- No requirement that every historical Laptop heuristic be represented in the first generic version if a narrow compatibility adapter is proven necessary; such an adapter cannot be the ordinary category path.

## Decisions

### 1. Use trusted declarative definition files validated by typed models

The source of truth will be versioned category definition documents under a trusted application/data path such as `categories/*.json` (YAML may be supported only if the repository already standardizes it; JSON is the initial format). Pydantic models provide typed `CategoryDefinition`, `CategoryAttributeDefinition`, `ConstraintRule`, `RankingRule`, `DisplayFieldDefinition`, and the supported enum types. The server discovers only packaged/allowlisted definition files; it never accepts a caller-selected path or executes definition content.

This is preferred over typed Python modules because adding a category does not require importing or registering a new Python class, and it is preferred over unvalidated JSON because malformed definitions fail before traffic. A Python-only typed-definition approach would still be safe but would make the desired Router addition a production source edit. A plugin framework is rejected because ordinary category differences are data, not executable behavior.

The catalog database's `AttributeDefinition` rows are a storage/display projection of the registry, not a second semantic source. Seed/catalog validation compares them to the registry and rejects drift. Product/SKU JSON remains factual catalog input; product documents remain evidence input.

### 2. Define a closed generic vocabulary, not a category policy hierarchy

The typed model has a small closed vocabulary:

```text
AttributeType       number | string | enum | boolean
FilterOperator      eq | gte | lte | contains | match | enum_match
ConstraintRole      hard | soft | hard_or_soft | display_only
RankingStrategy     higher_is_better | lower_is_better | exact_match |
                    preference_match | neutral
MissingStrategy     reject_if_hard | neutral | deterministic_penalty | ignore
```

An attribute also declares label, unit, enum values/order when applicable, accepted operators, default role, optional numeric bounds, weight, missing penalty (bounded 0–1 when used), comparison/display order, comparable flag, and a deliberately small formatting hint. Multi-valued use-case data is represented as a declared multi-valued enum; it does not require a `use_cases` branch in the engine.

Definition rules are declarative facts. They may select an existing generic primitive, but they may not contain Python expressions, regular-expression programs, imports, callbacks, or arbitrary scoring formulas. Registry validation rejects unsupported combinations, for example numeric-only operators on boolean attributes, enum ranking without enum values, duplicate attribute keys, weights outside bounds, or dangling rule/display references.

### 3. Make registry resolution the first category boundary

`CategoryRegistry` is constructed once by a server-owned factory and validated completely. It exposes:

```text
get(code) -> CategoryDefinition
resolve_code_or_alias(value) -> ResolvedCategory | unresolved
supported_categories() -> ordered metadata
schema_for(code) -> extraction/validation view
validate_catalog_attributes(code, attributes) -> issues
```

Alias normalization is Unicode/case/whitespace normalized and deterministic. A normalized alias may map to exactly one code. The registry reports duplicate codes, conflicting aliases, invalid definitions, and dangling references as startup/configuration failures. The gate keeps only the existing write-intent guard and delegates category resolution; it no longer has category phrase lists or category-specific modes.

Structured extraction returns a bounded machine-readable envelope, for example:

```json
{
  "category": "accessory",
  "category_candidates": [{"code": "accessory", "confidence": 1.0}],
  "attributes": {
    "battery_wh": {"value": 48, "operator": "gte", "role": "hard"}
  }
}
```

The resolver validates the candidate code. Zero reliable candidates is `category_ambiguous`; a requested but unregistered code is `unsupported_category`; multiple tied supported codes is `category_ambiguous`. No fallback category is selected.

### 4. Use one schema-guided parser

The parser receives `CategoryRegistry.schema_for(code)` and produces `RecommendationRequest` with canonical category code, generic budget/availability/preferences, and a `category_attributes` mapping of validated typed constraints. It iterates attribute definitions, numeric/unit coercers, enum aliases, boolean aliases, and generic operator extraction. It does not dispatch to `parse_phone`, `parse_camera`, or `parse_router`.

The default deterministic extractor remains model-independent. An optional structured LLM extractor may fill the same envelope, but it is not authoritative: the registry validates its shape, it cannot add catalog facts, and invalid output becomes a typed safe clarification. Definition-owned phrase aliases are bounded extraction metadata, not executable business logic. This is how `camera.sensor_size` becomes available without parser Python changes.

### 5. Separate generic hard filtering from soft scoring

The service pipeline is:

```text
resolve category
  -> validate/normalize request against definition
  -> retrieve active canonical candidates for category
  -> apply generic budget and availability
  -> apply definition-driven hard constraints
  -> compute bounded soft/ranking signals
  -> score, SPU-deduplicate, tie-break, top-K
  -> project declared fields/evidence and canonical SKU context
```

Operator semantics are explicit:

| Type | `eq` | `gte` / `lte` | `contains` / `match` | `enum_match` |
|---|---|---|---|---|
| number | exact decimal equality | numeric comparison | invalid | invalid |
| string | normalized exact equality | invalid | substring/token match defined by primitive | invalid |
| enum | canonical value equality | ordered enum comparison only when definition declares order | invalid | scalar equality or declared multi-value overlap |
| boolean | exact boolean equality | invalid | invalid | invalid |

`hard_or_soft` is not inferred from ambiguous prose: the normalized request must carry a role, or parsing returns a clarification. Missing hard fields reject; missing soft fields use the definition's neutral/penalty/ignore behavior. Invalid request fields and cross-category fields fail before candidate evaluation.

### 6. Normalize ranking signals instead of summing raw values

Each ranking rule emits a bounded Decimal signal `s ∈ [0,1]` and has a positive bounded weight. For a numeric value `x`, bounds `[lo, hi]` come from the definition when supplied; otherwise they are calculated from the post-hard-filter candidate snapshot for that attribute. Values are clamped to the bounds. If `hi == lo`, the signal is `1` for a present value under a neutral intrinsic rule (all candidates are equal on that dimension) and otherwise follows the match/missing rule.

```text
higher_is_better: (x - lo) / (hi - lo)
lower_is_better:  (hi - x) / (hi - lo)
exact_match:     1 when canonical values match, else 0
preference_match: declared scalar equality or multi-value overlap ratio
neutral:          0.5
```

Missing behavior is applied before combination: `reject_if_hard` removes the candidate; `neutral` contributes 0.5; `deterministic_penalty` contributes the definition's fixed bounded penalty (for example 0.25); `ignore` removes the rule from the denominator. The score is:

```text
score = ROUND_HALF_UP(100 * SUM(weight * signal) / SUM(active weights))
score = clamp(score, 0, 100)
```

If no soft/ranking rule is active, all eligible candidates receive the same deterministic neutral score. Generic budget is a hard `price <= budget` constraint in the candidate currency; baseline price is not multiplied into a score because it is not dimensionally comparable to category attributes. The stable final order is `(-score, price, sku_code)`, with deterministic SPU de-duplication and alternative-SKU projection preserved.

### 7. Keep catalog and evidence boundaries authoritative

The repository calls one category-parameterized active SKU query. Candidate attributes are checked against the registry definition and the canonical Product/SKU/inventory rows. RAG can enrich top-K results but cannot create candidates or override category, attributes, price, stock, or SKU identity. The graph uses one `catalog_candidates → generic ranking → evidence → decision` path. Resolution outcomes terminate before candidate retrieval.

### 8. Project generic fields and preserve the public migration bridge

The backend result gains an additive generic field projection:

```text
comparison_fields: [{
  key, label, value, value_type, unit, display_order,
  comparable, format_hint
}]
```

The existing `specifications` shape may be populated from the same projection during the compatibility window. `RecommendationRequest.category_attributes` remains machine-readable; its public schema is widened only as required to describe typed constraint values. The category code is either an opaque validated string with a registry-backed response metadata field or a generated bounded enum only for a separately versioned public contract; the design favors the opaque/additive form so a data-only category does not require a frontend type edit. OpenAPI is regenerated, never hand-edited.

React uses generic result field iteration for constraints, cards, and comparison rows. It can display `display_name` from the result/registry projection and uses only generic formatting hints. It does not import CategoryRegistry or maintain category lists. The existing recommendation-context gate continues to control SKU selection.

### 9. Migrate Laptop and Monitor by definition first

Laptop definition data declares ordered CPU/GPU enums, memory/storage/weight/screen numeric rules, multi-valued use cases, aliases, weights, and display fields. Monitor declares size, ordered resolution enum, refresh rate, panel enum, and multi-valued use cases. Existing TECH aliases become definition data. The generic engine therefore replaces both current named scorers.

During migration, compatibility adapters are limited to translating the released `LaptopConstraints`/`structured_constraints` shape and preserving ranking-policy/version fields where persisted responses require it. They cannot participate in ordinary category selection or introduce Laptop semantics into Monitor/other categories. If a historical TECH heuristic cannot be represented, the adapter is listed with an explicit removal condition and tested separately; retaining an entire LaptopPolicy or MonitorPolicy is not accepted.

### 10. Make validation and architecture proof enforce the target

The validator loads the same registry used by recommendation. It checks supported category, every declared attribute key/type/enum, required hard fields, Product/SKU/category identity, money, inventory, and document identity. It emits stable sorted issue facts. There is no `REQUIRED_ATTRIBUTES[category]` map in the target.

The proof fixture defines `test_accessory` in test-only registry/catalog/document fixtures. The test imports the production registry factory and generic service only; it does not patch or edit category branches. The proof asserts that the fixture works end-to-end and uses static source scans/AST checks to fail if generic engine, graph, frontend renderer, or validator contains a new category-name branch or a literal `battery_wh`/fixture key lookup.

### Proposed implementation files

The Apply task plan is expected to add or modify only these areas:

```text
app/recommendation/categories/models.py       # typed definitions/enums
app/recommendation/categories/registry.py     # load, validate, resolve
app/recommendation/categories/*.json          # Laptop/Monitor definitions
app/recommendation/parser.py                  # schema-guided extraction
app/recommendation/constraints.py             # generic operators/validation
app/recommendation/ranking.py                 # normalization/signals/score
app/recommendation/service.py                 # generic orchestration/projection
app/recommendation/gate.py                    # registry-backed resolution
app/recommendation/providers.py               # generic canonical retrieval
app/schemas/recommendation.py                 # additive generic public models
agents/shopmind_multi_agent/recommendation_nodes.py
app/repositories/catalog.py
scripts/validate_shopmind_catalog.py
frontend/src/features/recommendation/*       # metadata iteration/bridge
frontend/src/api/openapi.generated.ts         # generated only, if needed
tests/...                                     # architecture and regressions
```

No new ordinary category-specific scorer, policy, graph node, frontend page, or validator branch is planned.

## Risks / Trade-offs

- **[Risk]** Migrating Laptop ranking changes scores or old tie behavior. → Freeze before/after golden snapshots, keep a compatibility projection, and block Apply until existing category regression and public contract tests pass.
- **[Risk]** A declarative schema becomes a new hardcoded mud ball. → Keep a closed generic vocabulary, forbid executable fields, validate schema complexity/ranges, require every new field to use existing primitives, and add source-scan proof for name-based engine branches.
- **[Risk]** Candidate-snapshot min/max makes scores sensitive to catalog composition. → Prefer explicit definition bounds for stable dimensions; use snapshot bounds only when explicitly allowed, record the ranking policy/version and snapshot fingerprint, and require same-snapshot determinism tests.
- **[Risk]** Public clients depend on Laptop-shaped OpenAPI literals. → Use additive generic fields and compatibility defaults; regenerate OpenAPI; do not silently remove released fields.
- **[Risk]** LLM structured extraction emits invalid or fabricated values. → Treat it as untrusted request input, validate against the registry, fail safely, and never merge it into Catalog facts.
- **[Risk]** Registry and catalog metadata drift. → Make validator and seed projection consume the same registry and fail before serving or accepting managed data.
- **[Risk]** Category resolution accidentally reintroduces a fallback. → Add explicit ambiguous/unsupported tests and a source/AST check forbidding default-category selection in the graph.
- **[Trade-off]** JSON definitions are easier to add but need strong schema validation and code review. → Version definitions, validate at startup/CI, and keep them in the trusted repository path.

## Migration Plan

1. In Apply, capture current `v3.1.0` Laptop/Monitor contract snapshots and add the typed registry/model tests without changing the public path.
2. Add definitions and registry validation, then make validator and read-only catalog metadata consume them.
3. Add generic parser, operator validation, constraint engine, normalization/ranking, and result projection behind the current service boundary.
4. Migrate graph/gate/providers and Laptop/Monitor compatibility behavior to the single generic path; keep the existing commerce/evidence boundaries.
5. Add generic frontend rendering and regenerate OpenAPI if the additive envelope changes; run focused and full regression checks.
6. Enable the generic path under a controlled configuration, compare deterministic snapshots, and retain a reversible compatibility switch during rollout.

Rollback is application-level: disable the new generic recommendation path and restore the pre-migration Laptop/Monitor adapter while leaving catalog, Cart, PendingAction, and existing runtime persistence untouched. No destructive database rollback or tag movement is part of this Change.

## Open Questions

None block the selected architecture or task breakdown. Exact JSON field spelling and the final public `category` typing are implementation details constrained by the additive compatibility contract and OpenAPI tests; they must not change the no-core-code category-addition proof.
