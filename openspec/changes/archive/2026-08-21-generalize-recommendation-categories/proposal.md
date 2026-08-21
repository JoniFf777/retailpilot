## Why

ShopMind's structured recommendation path is currently a closed Laptop-only slice: the gate, parser, candidate provider, ranking service, and frontend constraint panel all encode Laptop vocabulary. The repository already contains real Monitor products (`TECH-MON-006` through `TECH-MON-009`) in the structured catalog data and product documents, so this is the right moment to prove a second category through the same deterministic recommendation boundary instead of allowing more Laptop fields to leak into global contracts.

## What Changes

- Add a machine-readable category-aware recommendation request envelope with generic budget/availability/preferences and a bounded category-attribute map.
- Resolve Laptop, Monitor, ambiguous, and explicitly unsupported recommendation intents without silently defaulting to Laptop.
- Introduce one small server-owned policy seam that selects Laptop or Monitor attribute parsing, hard constraints, soft scoring, and display definitions while sharing catalog retrieval, filtering orchestration, ranking tie-breaks, evidence, and response projection.
- Keep the existing Laptop parser, constraints, ranking behavior, TECH compatibility heuristics, response shape, and commerce handoff behavior through a Laptop policy.
- Add a deterministic Monitor policy using real Monitor seed data and meaningful fields such as size, resolution, refresh rate, panel type, and use cases.
- Generalize Catalog candidate retrieval by category while retaining `list_active_laptop_skus` as a compatibility wrapper for existing callers.
- Extend the structured recommendation envelope additively with category, recommendation request/category attributes, and machine-readable resolution/error information.
- Reuse the existing generic ProductSpecification and comparison UI so Monitor fields render without a copied Monitor recommendation page.
- Preserve canonical SKU identity, PendingAction/HITL, expected-version confirmation, Chat idempotency, RAG evidence semantics, and safe Chat error projection.
- Add deterministic local fixtures/tests for cross-category isolation, unsupported/ambiguous resolution, missing attributes, ranking ties, structured response, frontend rendering, and commerce compatibility.

## Capabilities

### New Capabilities

- `recommendation-categories`: Long-term category-aware, deterministic, catalog-backed structured recommendation behavior for Laptop and Monitor.

### Modified Capabilities

- None. Existing `backend-regression-stability`, `commerce-cart`, `order-expiration`, `chat-retry-idempotency`, `agent-write-hitl`, and `chat-error-boundaries` remain independent and unchanged.

## Impact

Expected implementation touches `app/recommendation/`, recommendation schemas, the Catalog repository/provider, Multi-Agent recommendation nodes/gate, the ShopMind catalog seed data/script, frontend recommendation contract/rendering, generated OpenAPI types, and focused tests. No payment, order, auth, Redis, MQ, RAG platform, or destructive migration change is planned. PostgreSQL is expected to be Not Required because the policy and ranking behavior can be proved with existing local/SQLite fixtures and generic SQLAlchemy query tests.

## Acceptance Criteria

- Laptop and Monitor use one shared category-aware pipeline with category-specific policies rather than duplicated end-to-end pipelines.
- Laptop regression behavior remains green and its Laptop-specific logic is contained in the Laptop policy boundary.
- Monitor resolves from real catalog/fixture data and supports structured attributes, hard filtering, soft ranking, missing-attribute semantics, deterministic ties, availability, and structured display fields.
- Ambiguous and unsupported categories return machine-readable non-success outcomes and never silently fall back to Laptop.
- Catalog facts remain authoritative; LLM/Agent paths do not fabricate product, SKU, price, inventory, or attributes.
- Recommendation add-to-cart continues through canonical SKU → PendingAction → expected-version confirmation → canonical Cart.
- Focused tests, full non-integration backend tests, relevant/full frontend verification, strict OpenSpec validation, Sync, Archive, and archived validation pass without changing the six existing main capabilities.
