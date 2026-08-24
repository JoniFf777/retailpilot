## 1. Baseline, contract inventory, and safety boundaries

- [x] 1.1 Record Apply-before Git status, tag target, current recommendation/public/OpenAPI snapshots, and preserve all pre-existing worktree files.
- [x] 1.2 Add focused tests that prove `v3.1.0` Laptop/Monitor result identity, hard eligibility, stable ordering, alternatives, evidence, and Commerce context before enabling the generic path.
- [x] 1.3 Inventory every current category branch from `CURRENT_CATEGORY_COUPLING.md` and mark each as remove, replace with registry lookup, or compatibility-only.
- [x] 1.4 Add a static guard that the implementation does not move, recreate, or retag `v3.1.0`.

## 2. Typed definitions and CategoryRegistry

- [x] 2.1 Add typed models/enums for CategoryDefinition, attribute metadata, operators, constraint roles, ranking strategies, missing strategies, numeric bounds, display metadata, and structured validation issues.
- [x] 2.2 Add trusted declarative Laptop and Monitor definitions containing aliases, typed attributes, enum order/aliases, generic rules, weights, missing semantics, and comparison fields.
- [x] 2.3 Implement CategoryRegistry loading from the fixed trusted definition directory with deterministic file ordering and no user-controlled paths or dynamic code execution.
- [x] 2.4 Implement fail-fast validation for duplicate codes, conflicting aliases, malformed attributes, unsupported type/operator/ranking combinations, invalid enum definitions, invalid missing strategies, invalid bounds/weights, dangling ranking references, and dangling display references.
- [x] 2.5 Add registry tests for canonical lookup, normalized aliases, conflict detection, supported-category discovery, error ordering, and immutable validated definitions.

## 3. Generic category resolution and schema-guided parsing

- [x] 3.1 Replace category-specific gate modes/term tables with one structured recommendation path and registry-backed category resolution while retaining the supervisor write-intent guard.
- [x] 3.2 Define the bounded machine-readable category-intent/extraction envelope and a deterministic extractor adapter; keep optional LLM extraction untrusted and schema-validated.
- [x] 3.3 Implement generic typed coercion for number, string, enum, multi-valued enum, and boolean attributes, including units, aliases, operators, and explicit hard/soft roles.
- [x] 3.4 Validate unknown attributes, invalid types, invalid enums, unsupported operators, cross-category attributes, and unresolved `hard_or_soft` roles before candidate retrieval/ranking.
- [x] 3.5 Add resolution/parser tests for Laptop, Monitor, ambiguous, unknown, unsupported, `camera.sensor_size`, `battery_wh`, invalid extractor output, and no-Laptop-fallback behavior.

## 4. Generic constraints and deterministic ranking

- [x] 4.1 Implement definition-driven number, string, enum, multi-enum, and boolean operator evaluation with canonical comparison and explicit error behavior.
- [x] 4.2 Implement generic hard filtering for availability, budget, active status, hard roles, missing hard fields, and invalid candidate attributes without category-name or attribute-name branches.
- [x] 4.3 Implement soft preference signals and missing semantics for neutral, deterministic penalty, and ignore behavior with bounded score-breakdown facts.
- [x] 4.4 Implement declared-bound and candidate-snapshot numeric normalization, clamping, zero-width handling, exact/enum/boolean matching, preference overlap, weighted score combination, and deterministic rounding.
- [x] 4.5 Implement deterministic `(-score, price, sku_code)` ordering, SPU de-duplication, top-K, and alternative-SKU projection in the generic service.
- [x] 4.6 Add unit tests for all operators, dimensional normalization, price-as-budget-only behavior, missing hard/soft fields, invalid/cross-category inputs, repeated-input determinism, and equal-score ties.

## 5. Request/result schemas and public projection

- [x] 5.1 Replace the generic engine's required Laptop-shaped internal state with typed generic recognized/category constraints while preserving an additive Laptop compatibility projection.
- [x] 5.2 Add machine-readable comparison field models containing key, label, value, type, unit, order, comparable flag, and bounded formatting metadata.
- [x] 5.3 Project all recommended fields from registry/catalog declarations and retain canonical Product/SKU, money, availability, evidence, score, alternatives, and recommendation context.
- [x] 5.4 Preserve safe malformed-result/projection-error behavior and ensure answer prose never supplies missing catalog facts.
- [x] 5.5 Decide and test the additive public category typing; regenerate OpenAPI/frontend types through the repository script rather than hand-editing generated output.
- [x] 5.6 Add public JSON/SSE, persistence/replay, and generated-contract regression tests for Laptop, Monitor, `test_accessory`, unresolved categories, and projection failure.

## 6. Catalog retrieval, validator, and data/document alignment

- [x] 6.1 Make the category-parameterized canonical SKU query the only generic retrieval path; retain Laptop-named repository/provider methods only as deprecated compatibility wrappers.
- [x] 6.2 Make catalog attribute-definition projection and candidate validation compare against CategoryRegistry metadata instead of duplicating recommendation semantics.
- [x] 6.3 Generalize `validate_shopmind_catalog.py` to discover registry categories and validate supported codes, keys, types, enums, hard completeness, Product/SKU identity, money, status, inventory, and document identity with stable issue ordering.
- [x] 6.4 Add validator tests for a valid registry category and each invalid identity/type/enum/hard-field/money/inventory/document case without adding category-specific validator branches.
- [x] 6.5 Keep existing Laptop/Monitor catalog files and product documents unchanged in this Change; defer new production data to a separate data Change.

## 7. Agent graph, RAG, Commerce, and runtime integration

- [x] 7.1 Route all resolved registered categories through one graph recommendation path and terminate ambiguous/unsupported resolution before candidate retrieval.
- [x] 7.2 Remove graph/provider default-to-Laptop behavior and assert the registry category is present and validated at each boundary.
- [x] 7.3 Preserve top-K-before-RAG ordering, Catalog authority, evidence failure semantics, and no-new-candidate RAG behavior.
- [x] 7.4 Preserve canonical SKU recommendation context and the existing PendingAction owner/thread/expiry/expected-version confirmation path.
- [x] 7.5 Verify read Agents remain read/intent-only and no generic recommendation path can directly write Cart/preferences/domain state.
- [x] 7.6 Add graph, RAG, Commerce/HITL, Chat error, retry/idempotency, replay, and SSE regression cases for generic and unresolved category trajectories.

## 8. Frontend generic renderer

- [x] 8.1 Replace named category constraint chips with generic declared constraint/comparison field iteration and bounded formatter selection.
- [x] 8.2 Remove Laptop/Monitor label conditionals from recommendation cards/panels and render category display metadata or a safe generic label.
- [x] 8.3 Keep shared ProductSpecifications/ComparisonDrawer behavior, alternatives, evidence, comparison ordering, projection-error UI, and recommendation-context SKU selection.
- [x] 8.4 Add a `test_accessory` frontend fixture that renders without adding a category conditional or category label map.
- [x] 8.5 Run generated typecheck, Vitest, lint, build, and relevant mocked/live browser checks after the public contract is finalized.

## 9. Laptop and Monitor migration

- [x] 9.1 Translate Laptop CPU/GPU tiers, memory, storage, weight, screen, use-case aliases, hard/soft behavior, and display metadata into the declarative definition.
- [x] 9.2 Translate Monitor size, resolution order, refresh rate, panel, use-case behavior, minimum-input clarification, missing semantics, and display metadata into the declarative definition.
- [x] 9.3 Delete/replace named scorer branches and literal attribute lookups from the generic engine; isolate only proven released-contract adapters.
- [x] 9.4 Run before/after Laptop/Monitor golden snapshots and investigate every score/order/field difference before enabling the new default path.
- [x] 9.5 Document any retained compatibility adapter, why the schema cannot express it, its bounded surface, and its removal condition; reject whole-category policy retention.

## 10. Architecture proof and no-mud-ball controls

- [x] 10.1 Add a test-only `test_accessory` CategoryDefinition fixture with one numeric, one enum, one boolean, and one display field using existing generic capabilities.
- [x] 10.2 Add only test-only catalog Product/SKU/inventory/document fixtures and a request fixture for `test_accessory`; do not add production category data.
- [x] 10.3 Assert resolve → validate attributes → hard filter → normalize/rank → generic comparison fields → canonical SKU/context end-to-end.
- [x] 10.4 Add source/AST guards that fail on category-name branches, literal `battery_wh`/fixture key lookups, custom ordinary-category scorers, frontend category conditionals, and validator category maps in generic paths.
- [x] 10.5 Add a review checklist that any new operator/ranking semantic is implemented once as a reusable generic capability, never as an ordinary category patch.

## 11. Verification and release readiness

- [x] 11.1 Run focused backend recommendation/catalog/parser/registry tests with LangSmith, Redis, RocketMQ, and external APIs disabled.
- [x] 11.2 PostgreSQL verification is not required: no migration or SQL query semantics changed; SQLite repository and full non-integration checks cover the registry validation path, and the local PostgreSQL service is not running.
- [x] 11.3 Run frontend typecheck, lint, build, unit/browser checks, and generated OpenAPI consistency checks.
- [x] 11.4 Run full non-integration backend regression plus Commerce/HITL, Chat error, Chat retry/idempotency, RAG, and release-readiness suites.
- [x] 11.5 Run registry fail-fast validation with malformed/duplicate definitions and confirm bounded failure before serving recommendation traffic.
- [x] 11.6 Run `git diff --check`, inspect the immutable `v3.1.0` tag, verify no catalog expansion is included, and record clean/expected Git status.
- [x] 11.7 Run strict OpenSpec change/spec validation and review all requirements/scenarios/tasks against the final implementation evidence.
