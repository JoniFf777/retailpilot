## Context

The current managed seed inventory is `data/catalog/laptop_catalog.json` with 5 Laptop products and `data/catalog/monitor_catalog.json` with 4 Monitor products. All current managed recommendation attributes are present, but the narrow set limits ranking and filtering demonstrations. `scripts/seed_shopmind_catalog.py` already writes category/attribute/SPU/SKU/inventory rows idempotently and protects existing inventory. `app/catalog/models.py` and `app/repositories/catalog.py` define the canonical relationships and facts used by recommendation policies. The existing product document corpus contains all current Laptop/Monitor legacy IDs.

## Goals / Non-Goals

**Goals:**

- Expand only managed demo data and the small validation/test surface needed to prove its quality.
- Preserve all existing identifiers and recommendation architecture.
- Make missing/invalid data failures deterministic and machine-readable.
- Demonstrate meaningful category policy scenarios without making counts part of permanent behavioral contracts.

**Non-Goals:**

- No category-policy seam redesign, new recommendation algorithm, catalog administration system, dynamic ingestion, vector/RAG platform, migration, or PostgreSQL-specific data layer.
- No deletion or mutation of legacy Product, Cart, Order, user, or existing Catalog identities.
- No frontend redesign or public API schema change unless a test proves an existing contract is insufficient; expected result is no schema change.

## Decisions

### 1. Expand existing managed seed files, preserving stable identities

Append new rows to the existing Laptop and Monitor JSON seed files. New rows use stable `product_code`, `legacy_product_id`, and `sku_code` values and plausible attributes aligned with the existing product/document corpus style. Existing rows are never renamed or deleted. Existing Monitor out-of-stock coverage remains and an additional Laptop out-of-stock/value case is added.

Target demonstration coverage is intentionally small: 9 Laptop products and 8 Monitor products after expansion, with multiple price bands and use cases. These counts are test/report facts, not main-spec requirements.

### 2. Add a deterministic managed-data validator

Create `scripts/validate_shopmind_catalog.py` with a reusable `validate_catalog_files(paths)` helper and JSON-serializable `ValidationReport`. The validator reads managed seed JSON only and checks:

- unique category, product, legacy, and SKU identifiers;
- every product has one valid SKU and the SKU references its product;
- valid category/status, positive money, uppercase 3-letter currency, and non-negative inventory;
- required Laptop/Monitor attribute codes and declared value types;
- category policy field compatibility;
- one matching product document per managed legacy ID, with the ID present in the document;
- no conflicting duplicate facts across seed files.

The command exits non-zero on invalid data and emits stable issue codes, paths, and bounded details. It does not connect to a database or mutate data.

### 3. Preserve seed idempotency and inventory safety

Keep `seed_catalog`/`run_seed` as the write path. The validator runs before tests and can be invoked independently. Seed tests use an isolated local SQLite schema to prove clean insert and repeated rerun; a second run must report zero new Product/SKU rows and must not reset an existing Inventory quantity. No legacy tables are touched. The existing `--replace-managed-seed` restriction remains the only managed update path.

### 4. Align documents without making RAG authoritative

Add concise product documents for new legacy IDs using the existing Markdown headings and identity convention. The validator requires identity presence but does not parse document price/specs as facts. Recommendation tests assert Catalog price/stock/specification values win when document text is present; RAG remains explanation/evidence only.

### 5. Test data against existing policies, not new heuristics

Use `parse_recommendation_request`, `build_recommendation`, and existing policy contracts to load deterministic seed rows into local candidate fixtures. Tests cover Laptop value/development/portable/gaming and Monitor office/gaming/high-resolution/size/panel cases, strict no-match, out-of-stock filtering, missing soft attributes, close scores, and stable order. No fallback heuristic is added to make a data case pass.

### 6. Keep public and commerce boundaries unchanged

New SKU facts flow through the existing category-aware RecommendationResult and generic ProductSpecification envelope. Recommendation selection still exposes canonical SKU identity and uses the existing PendingAction/HITL path. Since no schema changes are expected, frontend/OpenAPI should remain unchanged; existing recommendation UI tests confirm larger data/spec sets render.

## Alternatives Considered

- **Generate hundreds of synthetic products:** rejected; it would obscure data quality and create untrustworthy demo facts.
- **Create a new catalog database/admin layer:** rejected; out of scope and unnecessary for managed fixtures.
- **Patch recommendation heuristics for missing data:** rejected; quality gaps must fail validator/tests rather than become hidden policy guesses.
- **Use RAG documents as the source of missing attributes:** rejected; Catalog remains the price/stock/specification authority.
- **Run PostgreSQL only for ceremony:** rejected; no schema or database-specific behavior changes.

## Risks / Trade-offs

- **New fixture facts can drift from documents:** validator checks identity; focused tests keep canonical Catalog facts authoritative.
- **Seed rerun semantics can accidentally reset inventory:** tests explicitly mutate inventory before rerun and assert preservation.
- **More candidates can alter ranking examples:** existing Laptop behavior and deterministic tie-break tests are retained; new scenario assertions use explicit policy expectations.
- **Legacy documents use historical text units:** documents are evidence only; validator checks identity, not fact authority.

## Migration Plan

1. Snapshot the dirty worktree and create the Apply baseline.
2. Add validator, seed rows/documents, and deterministic tests.
3. Run validator, focused tests, full backend/frontend checks, and strict OpenSpec validation. PostgreSQL remains Not Required unless a real DB-specific issue appears.
4. Sync `catalog-recommendation-data-quality` into its main spec, verify all seven existing main specs unchanged, archive with `--skip-specs`, and validate specs/archived artifacts.

Rollback is file-level: remove only newly managed seed/document rows and validator/tests from the Change diff; existing identifiers and business data are never deleted or rewritten.

## Open Questions

None block implementation. Exact new fixture names/values remain bounded implementation data, validated by the invariant checker and existing category policies.
