## Context

The current structured path is a Laptop slice. `app/recommendation/gate.py:8-56` returns only `structured_laptop_recommendation`; `app/recommendation/constraints.py` parses only Laptop vocabulary; `app/recommendation/providers.py:9-25` and `app/repositories/catalog.py:17-42` retrieve only active Laptop SKUs; and `app/recommendation/service.py:18-41` ranks with Laptop fields. `agents/shopmind_multi_agent/recommendation_nodes.py:61-140` wires those pieces directly into the graph. `app/schemas/recommendation.py:54-72,167-178` makes `LaptopConstraints` the structured request contract. The frontend `StructuredConstraintsPanel.tsx` enumerates Laptop fields, while `ProductSpecifications.tsx` and the comparison drawer are already generic.

The Catalog model already has category and attribute-definition tables (`app/catalog/models.py`), and the seed script is category-shaped even though `data/catalog/laptop_catalog.json` is currently Laptop-only. `data/structured/products.json` and `data/documents/products/TECH-MON-006.md` through `TECH-MON-009.md` provide real Monitor facts and evidence identifiers. The existing Cart handoff uses canonical SKU context and is outside the recommendation ranking boundary.

## Goals / Non-Goals

**Goals:**

- Make category resolution and recommendation requests machine-readable.
- Share candidate retrieval, generic availability/budget filtering, ranking orchestration, SPU de-duplication, tie-breaking, evidence attachment, and response projection.
- Keep Laptop behavior compatible while moving Laptop-only parsing/scoring into a named policy.
- Add a real Monitor policy and deterministic seed/fixture data with at least two meaningful category attributes.
- Reuse generic structured specifications and comparison UI.
- Make unsupported/ambiguous category outcomes safe and typed.

**Non-Goals:**

- No plugin marketplace, dynamic code loading, ten-category rollout, recommendation analytics, RAG platform redesign, LLM ranking, auth/payment/order changes, localization, or frontend redesign.
- No destructive migration or broad catalog administration system. Monitor data is a small managed seed extension using the existing tables/script.
- No changes to existing Cart/HITL, Chat retry, error-boundary, order-expiration, or Agent write contracts.

## Decisions

### 1. Choose Monitor as Category B

Monitor is the lowest-risk real second category: the repository already carries four structured Monitor products with stable legacy IDs, prices, stock flags, documents, and existing category vocabulary. The Catalog schema can represent Monitor attributes without a new table. A small `data/catalog/monitor_catalog.json` seed will define category attributes and enough active/inactive inventory cases for deterministic tests.

### 2. Use a small static policy registry, not a plugin framework

Introduce a server-owned map of category code to policy (`laptop` and `monitor`). A policy owns parsing/normalization of category attributes, hard-constraint evaluation, soft scoring, missing-field behavior, and display definitions. The shared service owns candidate input, generic availability/budget handling, policy dispatch, stable sorting, SPU de-duplication, and generic response assembly. Adding Category C requires one policy and seed data, not a second graph/pipeline, while avoiding dynamic loading or a large abstraction framework.

### 3. Add an additive request/result envelope while preserving Laptop compatibility

Add `RecommendationRequest` with `category`, generic `budget_max`, `budget_currency`, `availability_required`, `generic_preferences`, and `category_attributes`. Add `category`, `recommendation_request`, `category_attributes`, and optional machine-readable `error_code` to `RecommendationResult`; add `category` to each `Recommendation` with a Laptop default. Retain `structured_constraints: LaptopConstraints` as a backward-compatible field for existing consumers and tests; Monitor uses the generic request/category-attribute fields while leaving that legacy Laptop field at its safe default. Existing clients can ignore additive fields.

### 4. Resolve categories before candidate retrieval

Extend the existing gate without changing the write-intent guard. Explicit Laptop terms resolve to Laptop; explicit Monitor terms resolve to Monitor; mixed category signals produce `clarification_required` with `category_ambiguous`; explicitly recognized unsupported categories such as phone/tablet/headphone produce `clarification_required` with `unsupported_category`; generic recommendation language without a reliable category remains a typed category clarification. No resolution branch defaults to Laptop. Existing generic legacy read/write routing remains intact when the gate does not claim structured recommendation.

### 5. Define Laptop and Monitor policy semantics

Laptop policy wraps the current parser and ranking implementation, including CPU/GPU tiers, memory, storage, weight, screen, use cases, price, availability, and the current TECH-shaped compatibility vocabulary. Its policy version remains compatible with the current Laptop result behavior.

Monitor policy uses:

- category attributes: `size_inches`, `resolution`, `refresh_rate_hz`, `panel_type`, `use_cases`;
- hard constraints: active category/SKU, available inventory, budget, minimum size, minimum resolution, and minimum refresh rate when explicitly requested;
- soft ranking: requested use case, panel type, higher resolution/refresh when relevant, and value/price fit;
- display fields: all declared comparable Monitor attributes through the existing `ProductSpecificationView` envelope.

Hard-required attributes missing from a candidate eliminate it. Missing soft fields produce a neutral/ bounded penalty and never raise, generate NaN, or permit LLM guesses. Monitor resolution uses a fixed order (`1080p < 1440p < 4k`) and ranking ties use `(-score, money_amount, sku_code)` after stable candidate normalization.

### 6. Generalize Catalog retrieval with a compatibility wrapper

Add `list_active_skus(session, category_code)` and provider `list_active_skus(category_code)`, selecting active Product/SKU/inventory rows and ordered attribute definitions by category. Keep `list_active_laptop_skus()` delegating to the generic method so existing catalog tests and PostgreSQL acceptance callers remain stable. The query remains SQLAlchemy and does not require PostgreSQL-specific behavior.

### 7. Keep RAG and commerce boundaries unchanged

RAG remains enrichment after deterministic top-K catalog ranking. It may use Monitor legacy IDs for existing product evidence, but cannot decide price, stock, category, SKU, or ranking facts. The existing evidence success/partial/degraded/failed semantics remain unchanged. Recommendation context continues to carry canonical SKU identity into the existing PendingAction flow; no Agent or recommendation node writes Cart state.

### 8. Reuse generic frontend rendering

`ProductSpecifications` and `ComparisonDrawer` already render declared machine-readable fields generically. Extend the constraints panel with category-aware generic/category-specific chips and add a small category label; do not create Monitor-specific pages/cards. Update OpenAPI-generated TypeScript using `frontend/package.json`'s `generate:api` script if the additive schema changes require it.

## Alternatives Considered

- **Duplicate Laptop pipeline for Monitor:** rejected because it creates a second gate/provider/service/response path and makes Category C costly.
- **One global schema containing every category field:** rejected because it recreates the Laptop-only coupling as a growing field-mudball.
- **Generic untyped attributes only:** rejected because policy behavior and public contracts need typed validation at the category boundary; untyped JSON is limited to the bounded category-attribute envelope and catalog facts.
- **Treat every existing legacy category as structured immediately:** rejected; Monitor is sufficient proof and other categories remain unsupported/legacy until a later policy exists.
- **PostgreSQL-specific JSON queries/migration:** rejected because existing SQLAlchemy retrieval and local fixtures prove the behavior without adding database coupling.

## Risks / Trade-offs

- **Existing Laptop tests expect `LaptopConstraints`:** retain the field and defaults, add the new envelope additively, and preserve the Laptop wrapper.
- **Monitor seed is separate from the original Laptop seed:** the script will support seeding both managed files while preserving explicit single-file and idempotent behavior.
- **Unknown Monitor attributes:** omit from comparison if not declared; hard missing fields eliminate candidates and soft missing fields are neutral/penalized deterministically.
- **Frontend generated contract drift:** use the existing API generation command and run generated-contract/type checks.
- **Legacy product documents contain facts outside the new Catalog:** they remain evidence only and never override canonical Catalog identity/price/stock/attributes.

## Migration Plan

1. Add generic request/result models, category resolution, policy seam, generic Catalog retrieval, and Monitor seed data.
2. Wire the graph through the generic category path while preserving the Laptop compatibility wrapper and existing write handoff branch.
3. Update frontend types/rendering through OpenAPI generation if required.
4. Run focused local tests, full non-integration backend, frontend checks, and strict OpenSpec validation. PostgreSQL is Not Required unless implementation reveals a database-specific correctness dependency.
5. Sync the new capability to `openspec/specs/recommendation-categories/spec.md`, verify all existing specs unchanged, then archive with `--skip-specs`.

Rollback is application-level: disable the structured Monitor gate/policy and retain the Laptop compatibility path; no destructive schema rollback is introduced.

## Open Questions

None block the selected design. The exact Monitor seed values and localized display labels are implementation details constrained by the policy fields above.
