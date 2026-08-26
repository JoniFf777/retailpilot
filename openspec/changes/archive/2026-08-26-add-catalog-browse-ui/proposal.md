## Why

ShopMind currently exposes recommendation, chat, and cart workflows but gives users no first-class way to discover the catalog without already knowing a category or starting a conversation. A small, read-only catalog browse surface will make the existing Catalog truth source discoverable while preserving the schema-driven recommendation and confirmation boundaries.

## What Changes

- Add read-only category, product-list, and product-detail Catalog API contracts backed by the existing Catalog tables and `CategoryRegistry`.
- Project category display metadata and structured Catalog attributes into generic, deterministic product specifications; price, SKU identity, and availability remain Catalog facts.
- Add `/catalog`, `/catalog/:category`, and `/catalog/:category/:product` React routes plus a visible 商品 navigation entry.
- Add shared category/product/specification UI for loading, empty, unavailable, unsupported-category, and safe API-error states.
- Reuse the existing canonical SKU → PendingAction → confirmation → Cart flow for browse-page add-to-cart; do not add direct Cart writes.
- Keep recommendation ranking, category engine, RAG, checkout, payment, and existing Cart contracts unchanged.
- Regenerate the public OpenAPI artifact and generated frontend types through the repository's existing generation workflow.

## Capabilities

### New Capabilities

- `catalog-browse-ui`: Discoverable, schema-driven catalog navigation, product listing/detail, availability/specification projection, safe read errors, and browse-to-HITL behavior.

### Modified Capabilities

None. Existing recommendation, commerce, and HITL requirements are preserved; the browse flow consumes their existing contracts.

## Impact

- Backend: additive `app/api/routes/catalog.py`, catalog response models, and generic read projections in the existing Catalog repository; no database migration is expected.
- Frontend: catalog feature/query/components, shared specification rendering, navigation/routes/styles, and generated OpenAPI types.
- Tests: focused API/repository/OpenAPI tests, React/Vitest coverage for Phone/Keyboard/Router, and browse-to-PendingAction integration coverage.
- Runtime: no LangSmith, Redis, RocketMQ, external API, RAG, recommendation, or payment changes. PostgreSQL is not required unless the implementation changes query semantics beyond existing SQLAlchemy Catalog reads.
