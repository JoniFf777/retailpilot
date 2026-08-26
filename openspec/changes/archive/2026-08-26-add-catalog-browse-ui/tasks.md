## 1. Baseline and contracts

- [x] 1.1 Capture the clean Git baseline and record the files allowed to change in `add-catalog-browse-ui-baseline`.
- [x] 1.2 Extend typed Catalog API schemas with generic category, Product, SKU, availability, specification, list, detail, and safe error projections.
- [x] 1.3 Add focused contract tests for deterministic ordering, opaque category identity, safe errors, and no filesystem/document-path leakage.

## 2. Catalog read API

- [x] 2.1 Add repository read functions for Registry-backed categories and active Products/SKUs with outer inventory availability, preserving canonical Catalog facts.
- [x] 2.2 Add generic specification projection from `CategoryRegistry` metadata and validate/handle malformed cross-category attributes fail closed.
- [x] 2.3 Add read-only `/api/catalog/categories`, `/api/catalog/products`, and `/api/catalog/products/{product_code}` routes with bounded limit/offset and typed 404 responses.
- [x] 2.4 Add backend API/repository tests for all categories, Phone/Keyboard/Router listings, details, out-of-stock rows, unsupported categories, missing products, and stable ordering.

## 3. Browse HITL bridge

- [x] 3.1 Add a catalog-browse PendingAction preparation request/endpoint that accepts a concrete canonical SKU and delegates to the existing confirmation payload machinery.
- [x] 3.2 Preserve owner/thread/quantity/inventory/sale-status validation and prove preparation performs no Cart write.
- [x] 3.3 Add API tests for prepare, confirm, cancel, stale version, wrong owner/thread, out-of-stock, replay, and canonical Cart visibility.

## 4. Frontend catalog experience

- [x] 4.1 Add generated-contract aliases and API client query/mutation methods for catalog reads and browse PendingAction preparation.
- [x] 4.2 Add `/catalog`, `/catalog/:category`, and `/catalog/:category/:product` routes and a visible generic 商品 navigation entry.
- [x] 4.3 Implement Registry-backed category discovery, generic Product cards, deterministic list states, and responsive layout without category-specific React branches.
- [x] 4.4 Implement generic Product detail and specification rendering from returned metadata, including SKU variants, price, availability, and safe error/empty states.
- [x] 4.5 Reuse `ActionDrawer` for browse add-to-cart confirmation and invalidate/refetch Cart and checkout state after confirmation.
- [x] 4.6 Add Vitest coverage for navigation, category discovery, Phone/Keyboard/Router browsing, specifications, unavailable state, loading/error/empty states, and browse HITL.

## 5. Contract generation and regression

- [x] 5.1 Export the runtime OpenAPI document and regenerate frontend TypeScript through the committed generation scripts; do not hand-edit generated output.
- [x] 5.2 Add OpenAPI consistency tests for all new paths and schemas while preserving existing Chat, Cart, Checkout, Order, and Payment contracts.
- [x] 5.3 Run focused backend/frontend tests, catalog validation, and the existing recommendation, Chat, Cart, and HITL regressions with external services disabled.
- [x] 5.4 Run the full non-integration backend suite plus frontend Vitest, lint, typecheck, e2e typecheck, production build, and bundle budget.

## 6. Demo and closeout

- [x] 6.1 Run the local frontend/backend Demo smoke from Catalog to Phone detail to Router detail to PendingAction confirmation and canonical Cart; record URL and result.
- [x] 6.2 Run `git diff --check` and a static architecture audit proving no category-specific Catalog renderer or recommendation-engine branch was added.
- [x] 6.3 Update implementation evidence and review artifacts, mark completed tasks truthfully, and confirm PostgreSQL is Not Required unless query semantics changed.
- [x] 6.4 Strict-validate the Change and main specs, sync only the approved `catalog-browse-ui` capability, archive with `--skip-specs`, and run archived strict validation.
- [x] 6.5 Generate `add-catalog-browse-ui-final-review.zip` containing the archived Change, synced spec, actual changed files, baseline/diff, test results, smoke report, and final review without checksums.
