## Why

The completed Laptop + Monitor category-aware architecture currently runs on a small managed demo catalog: 5 Laptop products and 4 Monitor products. The data is sufficient to prove the policy seam but too narrow to demonstrate price bands, real use cases, unavailable filtering, close deterministic rankings, and data/document quality. The repository already contains canonical Catalog models, managed seed files, legacy product documents, and deterministic recommendation policies, so this Change should improve data quality and coverage without redesigning that architecture.

## What Changes

- Add a deterministic managed-catalog validator for identifier, relationship, category-policy, money, inventory, required-attribute, and document-identity invariants.
- Expand the managed Laptop seed with additional plausible value, portable/development, and gaming/performance products while preserving all existing product/SKU identities.
- Expand the managed Monitor seed with additional office, high-refresh, high-resolution, panel, price-band, and unavailable coverage while preserving existing identities.
- Add product documents for newly managed products using the existing corpus format and validate document IDs against canonical legacy identifiers.
- Preserve seed idempotency, managed update semantics, inventory preservation, and non-destructive behavior for legacy Product, Cart, Order, and user data.
- Add deterministic recommendation scenario fixtures/tests for Laptop and Monitor price bands, use cases, hard constraints, missing attributes, unavailable filtering, no-match outcomes, tie-breaking, and catalog/RAG authority.
- Keep the existing category policy seam, RecommendationRequest/Result contract, frontend rendering, canonical SKU/HITL flow, RAG semantics, Chat retry, and error boundaries unchanged.

## Capabilities

### New Capabilities

- `catalog-recommendation-data-quality`: Managed Catalog data quality, seed idempotency, document alignment, and deterministic recommendation fixture coverage.

### Modified Capabilities

- None. Existing `recommendation-categories`, `commerce-cart`, `agent-write-hitl`, `chat-retry-idempotency`, `chat-error-boundaries`, `order-expiration`, and `backend-regression-stability` remain unchanged.

## Impact

Expected implementation is limited to managed JSON seed data, a small validator script/helper, product documents, seed tests, recommendation data-quality tests, and possibly no production recommendation code changes. No migration, external service, PostgreSQL-specific SQL, frontend schema, OpenAPI, payment, order, Cart, Agent, or RAG-platform change is planned. PostgreSQL is expected to be Not Required.

## Acceptance Criteria

- A deterministic validator reports machine-readable success/failure for managed Laptop and Monitor data quality.
- Existing canonical identifiers remain unchanged; all managed identifiers are unique and relationships, category, status, money, inventory, required attributes, and docs are valid.
- Expanded data covers value/development/portable/gaming Laptop requests and office/gaming/high-resolution/size/panel Monitor requests, with eligible, no-match, and unavailable cases.
- Seed reruns create no duplicates, preserve existing inventory, do not reset legacy/business tables, and keep managed update semantics explicit.
- Catalog remains authoritative over documents/RAG/LLM text for price, inventory, SKU, and structured attributes.
- Focused data/recommendation tests, full non-integration backend regression, frontend verification, strict validation, Sync, Archive, and archived validation pass.
