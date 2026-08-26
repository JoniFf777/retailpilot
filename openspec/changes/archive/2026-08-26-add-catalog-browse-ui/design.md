## Context

Explore found a mature Catalog model and repository, but no public Catalog read routes. `CatalogProduct`, `CatalogSku`, and `CatalogInventory` already hold canonical identity, price, and stock; `CategoryRegistry` already holds trusted category display and attribute metadata. The current `list_active_skus` path is recommendation-oriented because it filters out-of-stock rows and returns SKU candidates, so browse needs a small read projection that includes active but unavailable SKUs. The frontend already has React Router, TanStack Query, generated OpenAPI aliases, generic `ProductSpecifications`, and an `ActionDrawer`; it has no Catalog route or navigation entry.

## Goals / Non-Goals

**Goals:**

- Add deterministic, read-only category/list/detail Catalog endpoints using existing SQLAlchemy tables and Registry metadata.
- Keep the public projection generic: category metadata, Product identity, SKU variants, money, availability, and ordered specifications.
- Add a responsive `/catalog`, `/catalog/:category`, and `/catalog/:category/:product` experience with shared components and safe states.
- Reuse the existing PendingAction confirmation and canonical Cart transaction, adding only a narrow browse preparation adapter because the current structured endpoint requires a recommendation run.
- Keep OpenAPI as the source for browser contracts and avoid a database migration.

**Non-Goals:**

- No recommendation engine/ranking/parser/RAG redesign, image marketplace, search, complex pagination, or new commerce writer.
- No direct Cart mutation from browse, no filesystem document exposure, and no new category-specific React or Python policy.
- No changes to existing checkout, payment, order, identity, retry, Redis, RocketMQ, or external service behavior.

## Decisions

### 1. Add minimal Catalog read routes rather than reuse recommendation output

Add `GET /api/catalog/categories`, `GET /api/catalog/products?category=<code>&limit=&offset=`, and `GET /api/catalog/products/{product_code}`. The category route enumerates `default_category_registry().supported_categories()` and derives counts from active Catalog rows. The list/detail routes validate category through the Registry, query active Products and active SKUs with an outer inventory join, and order by `product_code`, then `sku_code`. The product projection uses Registry attributes to create generic `specifications`; the DB `AttributeDefinition` table is not allowed to invent labels that disagree with the trusted Registry.

Alternative considered: expose recommendation results as browse data. Rejected because recommendation results are request-shaped and omit unavailable inventory; browse must be a direct Catalog read with no ranking or RAG dependency. Alternative considered: add a second JSON-file API. Rejected because the database Catalog is the established fact source.

### 2. Keep one typed public projection for list and detail

Add Pydantic models for `CatalogCategoryView`, `CatalogProductSummary`, `CatalogProductDetail`, `CatalogSkuView`, `CatalogSpecificationView`, and list/detail envelopes plus a bounded `CatalogErrorResponse`. Decimal money is projected through the existing `Money` contract. Availability reuses `AvailabilityView` and computes `available_quantity = max(on_hand - reserved, 0)`; missing inventory is represented as unavailable for reads. Product detail includes the active Product description but never document paths.

Alternative considered: return raw ORM/attribute dictionaries. Rejected because it would leak storage details and make frontend type safety/category independence weaker.

### 3. Use Registry metadata as the only display schema

Projection code joins each declared Registry attribute's `canonical_catalog_key` to the merged Product/SKU attributes, preserves `label`, `unit`, `display_order`, `type`, `comparable`, and `format_hint`, and omits fields with no value. It does not inspect attribute names. The list UI chooses the first bounded set of returned fields for compact cards; the detail UI renders all returned fields. If a Catalog value fails Registry validation, the route returns the bounded Catalog failure rather than guessing.

### 4. Add a browse-only PendingAction preparation adapter

The existing `POST /api/pending-actions/add-to-cart` intentionally requires an owned recommendation run and must remain unchanged for recommendation-origin actions. Add a separate `POST /api/pending-actions/catalog-add-to-cart` request with `thread_id`, `sku_id`, and `quantity`; it resolves the canonical SKU, validates active Product/SKU, inventory, and quantity, and delegates to the existing `_create_catalog_pending_action` payload/TTL/version machinery without a direct Cart write. Confirmation/cancellation continue through the existing endpoints and `confirm_add_to_cart` implementation. The frontend uses the same `ActionDrawer`, expected version, owner binding, and Cart query invalidation.

Alternative considered: create a synthetic recommendation run for browsing. Rejected because it pollutes recommendation provenance and introduces a hidden write/read coupling. Alternative considered: call Cart service directly. Rejected because it bypasses the required HITL boundary.

### 5. Keep frontend routing and query state small

Add a `features/catalog` module with `catalogQuery.ts`, shared `CatalogCategoryPage`, `CatalogProductCard`, `CatalogProductDetailPage`, and `CatalogSpecifications` components. Router params are treated as opaque category/product codes and are URL encoded by the API client. Query keys include category and product code; query functions use AbortSignals; retry is disabled for predictable public errors. `App` adds one navigation item and an icon. The browse action component owns only preparation/confirmation state and uses `ActionDrawer`; it does not duplicate Cart write logic.

### 6. OpenAPI generation and compatibility

After backend models/routes are implemented, run `scripts/export_openapi.py --output frontend/openapi.json` and `npm run generate:api` from `frontend`. Update `frontend/src/api/contracts.ts` only with aliases to generated types. Existing generated contracts and all existing routes remain additive and backward compatible.

## Risks / Trade-offs

- [Risk] Counting categories requires database reads even when a category has no products → Mitigation: Registry remains the category source of truth; counts default to zero and category discovery still works.
- [Risk] Existing seeded DBs may not have the new category data loaded → Mitigation: browse reflects the current Catalog truth, while the existing seed discovery already loads all managed JSON; no UI fabricates missing products.
- [Risk] A Product can eventually have multiple active SKUs with different availability → Mitigation: list responses retain a SKU collection and detail exposes every canonical variant; add-to-cart always requires a concrete SKU.
- [Risk] Registry and persisted AttributeDefinition metadata can drift → Mitigation: response labels/order/types come from Registry and focused tests assert no cross-category field leakage; validator remains the Catalog data gate.
- [Risk] Browse action preparation is a new additive endpoint → Mitigation: it delegates to the existing canonical payload and confirmation service, with focused owner/thread/stale/inventory tests and no Cart writes before confirmation.

## Migration Plan

1. Deploy the additive API models/routes and frontend feature; run OpenAPI generation and focused tests.
2. Run the existing catalog validator and seed discovery in normal environments; no migration or data rewrite is required.
3. Start the local backend/frontend demo and smoke `/catalog → Phone → detail → Router → detail → PendingAction → Cart`.
4. Rollback by removing the frontend navigation/routes and additive Catalog routes; existing recommendation and commerce endpoints remain operational. No database rollback is needed.

## Open Questions

None that affect the contract or implementation plan. Complex search, pagination, images, and document evidence can be separate capabilities later.
