# Current Category Coupling Audit

Audit basis: the checked-out `main` at the start of this planning round, current `v3.1.0` tag present and untouched. This file records implementation facts; it is not an implementation patch.

## Executive finding

The current path already has a shared request envelope, catalog candidate model, provider method, evidence stage, SPU de-duplication, and shared React specification components. It is not yet schema-driven because category semantics are duplicated in Python, the registry does not exist, and the shared envelope still has Laptop-shaped required state.

Adding a third ordinary category today requires at least the following production locations (excluding the new catalog/data/document files themselves):

1. `app/schemas/recommendation.py`: extend `RecommendationCategory`, usually add category-owned request/constraint types, and account for the required `LaptopConstraints` field.
2. `app/recommendation/gate.py`: add category aliases, recommendation mode, detection precedence, and resolution text.
3. `app/recommendation/request.py`: add a category branch and a category-specific parser/model.
4. `app/recommendation/service.py`: add a category branch, scorer, attribute lookups, missing behavior, ranking policy version, and projection exceptions.
5. `agents/shopmind_multi_agent/recommendation_nodes.py`: add mode/category sets, resolution text, parser behavior, and possible fallback handling.
6. `app/recommendation/providers.py` / `app/repositories/catalog.py`: the generic method exists, but the Laptop compatibility method and tests are still the architectural default; integration usually requires category-aware definitions and retrieval assertions.
7. `scripts/validate_shopmind_catalog.py`: add the category to `REQUIRED_ATTRIBUTES` and, for enum-like fields, add another category-specific validation branch.
8. `app/catalog` seed/attribute-definition inputs: add category metadata and attribute definitions; current seed files duplicate semantic definitions outside a recommendation registry.
9. `frontend/src/features/recommendation/StructuredConstraintsPanel.tsx`: add a category conditional and labels/units.
10. `frontend/src/features/recommendation/RecommendationCard.tsx`: add a category label conditional.
11. `frontend/src/api/openapi.generated.ts` (and generation input/output if the public category enum changes): extend the category union.
12. Tests in recommendation/catalog/frontend areas: add category-specific fixtures and tests; this part remains expected and is not considered undesirable coupling.

Thus the current answer to “what production code must Router change?” is approximately 10–11 production locations, in addition to Router catalog/doc data. The exact count varies with the public schema choice, but it is materially more than the desired Category Definition + catalog + documents + tests.

## Coupling matrix

| Location | Current hardcoding | Why it changes per category | Target ownership |
|---|---|---|---|
| `app/schemas/recommendation.py:14-15` | `RecommendationCategory = Literal["laptop", "monitor", "unknown"]`; `LaptopConstraints` is a named model | Public type and request shape enumerate categories; Laptop fields are required in every result | Registry-backed opaque category code plus typed generic attribute/field contracts; keep a compatibility projection for released clients |
| `app/schemas/recommendation.py:55-74` | Laptop-only fields and validators | Attribute keys, units, and use-case vocabulary differ by category | `CategoryDefinition.attributes` and generic typed values/operators |
| `app/schemas/recommendation.py:197-203` | `RecommendationResult.structured_constraints: LaptopConstraints` | Result contract is still Laptop-shaped even for Monitor | Generic `recognized_constraints`/`category_attributes`; additive legacy Laptop projection only during migration |
| `app/recommendation/gate.py:9-16` | Modes `structured_laptop_recommendation` and `structured_monitor_recommendation` | Gate must know each new category and mode | One `structured_recommendation` mode plus `CategoryRegistry.resolve()` result |
| `app/recommendation/gate.py:35-110` | `_LAPTOP_TERMS`, `_MONITOR_TERMS`, unsupported list, Laptop hint count, Laptop fallback language | Alias vocabulary and category precedence vary; unknown categories cannot be inferred safely | Registry aliases + structured category-intent extractor; no category branch or fallback |
| `app/recommendation/request.py:14-26` | `MonitorCategoryAttributes` and Monitor literals | Attribute keys/types/enums are category-owned | Registry-generated schema supplied to one parser/extractor |
| `app/recommendation/request.py:45-105` | `parse_monitor_attributes`, Laptop import branch, `if category` | Natural-language extraction differs in vocabulary, not in engine capability | Generic schema-guided extraction/normalization loop; category definitions provide keys, units, enums and operators |
| `app/recommendation/constraints.py:1-51` | Laptop regex vocabulary and `parse_laptop_constraints` | Laptop phrases and tier/use-case aliases are category data | Definition-owned extraction aliases and generic typed constraint coercion; deterministic compatibility fixtures may remain outside core |
| `app/recommendation/service.py:15-17` | Laptop/Monitor policy versions and Laptop tier map | Scoring vocabulary and normalization are category-specific | Registry definition version + generic operator/ranking strategies; no key-name lookup in engine |
| `app/recommendation/service.py:28-64` | `if request.category == laptop/monitor`, Laptop fallback | Each category selects a separate implementation | `registry.definition_for(request.category)` and one generic engine |
| `app/recommendation/service.py:67-210` | `_score`, `_TIER_ORDER`, named `memory_gb`, `storage_gb`, `weight_kg`, `cpu_tier`, `gpu_tier`, use-case behavior | Current Laptop semantics are encoded in function logic | Declarative constraints/ranking rules; a very small generic comparator adapter for ordered enums may be used |
| `app/recommendation/service.py:212-400` | `_MONITOR_RESOLUTION_ORDER`, named Monitor fields, hard/soft branches, Monitor text | Monitor semantics are encoded in a second scorer | Definition enum order, roles, operators, strategies, missing rules, and display labels |
| `app/recommendation/providers.py:9-31` | Laptop compatibility method remains part of Protocol and SQL provider | Legacy callers depend on a Laptop-named method | Generic `list_active_skus(category_code)` as canonical interface; retain wrapper only as deprecated compatibility adapter |
| `app/repositories/catalog.py:43-44` | `list_active_laptop_skus` wrapper; unrelated legacy resolution fallback at line ~220 | Older tests/callers use Laptop name | Generic category query; compatibility wrapper must not be used by generic graph |
| `agents/shopmind_multi_agent/recommendation_nodes.py:48-52` | Category-specific mode set | Graph must dispatch each category mode | One structured path selected only by a validated registry resolution |
| `agents/shopmind_multi_agent/recommendation_nodes.py:71-75` | `or "laptop"` and Laptop provider fallback | Missing resolution can silently select Laptop | Missing/unknown resolution ends in typed ambiguity/unsupported result; no fallback |
| `agents/shopmind_multi_agent/recommendation_nodes.py:114-132` | Laptop/Monitor set and Monitor-specific clarification strings | Missing-field semantics/text differ today | Generic projection of definition display metadata and stable error catalog |
| `scripts/validate_shopmind_catalog.py:1-45` | Docstring, `REQUIRED_ATTRIBUTES`, Monitor resolution set | Validator owns a second category schema and category rules | Load/validate `CategoryRegistry`; enum/type/required checks come from definition |
| `app/catalog/models.py:45-60` | DB data types support only catalog `string/integer/decimal/boolean/string_list`; options are raw JSON | Storage projection does not carry full recommendation semantics | Registry owns recommendation semantics; catalog DB stores facts and can receive projected metadata without becoming source of truth |
| `frontend/src/features/recommendation/StructuredConstraintsPanel.tsx:4-21` | Laptop field tuple and Monitor conditional with named fields | Display order/labels/units differ per category | Iterate generic `comparison_fields`/constraint fields from backend metadata |
| `frontend/src/features/recommendation/RecommendationCard.tsx:18` | `item.category === "monitor" ? ... : ...` | Category display label is hardcoded | Use result/category display metadata; unresolved category has generic label |
| `frontend/src/features/recommendation/RecommendationPanel.tsx:14-22` | Only treats non-`unknown` category as resolved | Public category union is closed and unresolved semantics are special-cased | Validate generic result envelope; render category metadata without category list |
| `frontend/src/features/recommendation/ProductSpecifications.tsx` / `ComparisonDrawer.tsx` | Mostly generic iteration already, but consumes legacy `specifications` only | New result fields need a stable generic projection | Canonical `comparison_fields` array, with legacy specifications bridged during migration |
| `frontend/src/api/openapi.generated.ts:1582,1640,1651` | Literal `laptop | monitor | unknown`; LaptopConstraints schema | Generated contract reflects closed public enum | Use opaque validated code or bounded string-compatible category field; regenerate only for additive contract changes |
| `data/catalog/*.json` | `category` and `attribute_definitions` are repeated per seed | Data must align with semantic schema and documents | Separate catalog facts from trusted category definitions; validator proves exact alignment |

## Laptop/Monitor special-logic audit

### Laptop

| Existing behavior | Declarative target | Residual special behavior |
|---|---|---|
| CPU/GPU tiers | Ordered enum values plus `gte`/`higher_is_better` | None for ordinary ordered enum comparison |
| Memory/storage minimums | Number attributes with `gte`, hard role, reject-if-missing | None |
| Weight maximum | Number attribute with `lte`, hard role | None |
| Screen size exact match | Number attribute with `eq` | None |
| Primary/secondary use cases | Multi-valued enum with `enum_match`/`preference_match`, declared weights | None if multi-valued enum is part of generic capability |
| Base/bonus score | Definition ranking rules and weights | None; score wording is presentation metadata |
| TECH heuristic compatibility vocabulary | Definition-owned aliases mapping to canonical enum values | Compatibility alias table is data, not engine logic |

### Monitor

| Existing behavior | Declarative target | Residual special behavior |
|---|---|---|
| Size minimum | Number + `gte` + hard role | None |
| Resolution order | Ordered enum values + `gte`/higher strategy | None |
| Refresh-rate minimum | Number + `gte` + hard role | None |
| Panel match | Enum + soft role + exact/preference strategy | None |
| Use-case match | Multi-valued enum + preference strategy | None |
| Higher resolution bonus when no minimum | Ranking rule for resolution | None |
| “Insufficient constraints” clarification | Definition-level minimum request/required-input metadata | Generic validation/projection |

The current Laptop and Monitor scorers therefore do not justify a fleet of `PhonePolicy`/`RouterPolicy` classes. The only permitted extension point is a future generic strategy/operator added when it represents a reusable capability across categories; an ordinary category may not register arbitrary custom scorer code in this Change.

## Target ownership test

After Apply, a normal Router should require only:

```text
categories/router.json
data/catalog/router_catalog.json
data/documents/products/<canonical ids>.md
tests/.../router fixtures and regression cases
```

It must not require edits to `gate.py`, `parser.py`, `ranking.py`, `service.py`, `graph.py`, `RecommendationPanel.tsx`, or category maps in the validator. This claim is formalized in `ARCHITECTURE_PROOF.md`.
