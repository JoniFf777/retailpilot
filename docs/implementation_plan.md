# ShopMind implementation plan

This is the active implementation phase source. Historical design material remains in the other documents under `docs/`.

## Phase 0

Baseline audit, product direction, architecture and risk documentation. No runtime or database changes are implied by this phase.

## Phase 1A — Catalog and deterministic recommendation foundation

Catalog categories, attribute definitions, products/SPUs, SKUs and inventory are PostgreSQL-backed. Catalog is the fact source for SKU, price, specification, sale status and inventory. `legacy_product_id` is only a compatibility bridge to old Product/RAG documents. Hard filtering and ranking run at SKU level; Top K is deduplicated by SPU and returns an explicit `sku_id`. Seed identity is based on stable product/sku codes and managed-seed metadata.

## Phase 1B-Backend — Graph and response projection

The backend integrates Catalog retrieval, preference retrieval, deterministic ranking, Top-K product/policy evidence validation and a single RecommendationResult projection for JSON and SSE. Legacy paths remain compatible. The response builder never repairs persisted run state.

## Phase 1B-Frontend

After Phase 1B-Backend acceptance, the React/Vite frontend consumes generated OpenAPI TypeScript types. It renders all three recommendation outcomes, product cards, alternative SKUs and up to four-SKU comparison; integrates JSON/SSE with stale-result protection; and is covered by Vitest and Playwright. It does not modify recommendation algorithms, Cart management, Order, Payment, Redis or RocketMQ.

## Phase 2A-Backend — Structured HITL and SKU Cart foundation

Phase 2A Backend Acceptance Gate passed. PendingAction GET/confirm/cancel, owner/thread checks, row locking, versioning, idempotent replay, resolution snapshots, Catalog revalidation and SKU Cart persistence are implemented. PostgreSQL migration round-trip, five-case concurrency acceptance, API/Repository integration and OpenAPI export passed. Phase 2B does not change these transaction semantics.

## Phase 2B-Frontend / HITL Cutover — current

The frontend cutover uses `frontend/openapi.json` and `frontend/src/api/openapi.generated.ts` as the only HTTP contract source.

- RecommendationCard selection creates a structured PendingAction from the assistant message's `recommendation_context` (`thread_id`, `source_run_id`, `sku_id`, `quantity` only); it never writes Cart directly or parses natural language.
- Structured catalog actions use `/api/pending-actions/*` without `Idempotency-Key`; legacy chat actions continue to use `/api/chat/confirm` with the existing idempotency behavior.
- JSON `confirmation_required` and SSE terminal `run.result` resolve a typed PendingAction view. `action.prepared` is never used to construct the Drawer. Confirm always sends the Drawer quantity in `updated_fields.quantity` for structured actions.
- ActionDrawer renders catalog, legacy and `save_preference` typed editable fields, maps stable action error codes, disables terminal actions, refreshes terminal conflicts and shows replay/resolution without duplicate writes.
- The read-only SKU Cart uses `GET /api/cart` and TanStack Query key `['shopmind-cart', identity]`. Quantity editing, deletion, checkout, Order, Payment, Redis, RocketMQ and Outbox remain out of scope.
- Accessibility includes dialog semantics, labelled controls and focus restoration. Vitest and Playwright cover the cutover paths.

## Phase 3 and later

### Phase 3 Preflight — ShopMind Cart Management (audit complete)

Phase 2 is formally closed. The current `shopmind_cart_items` table already provides the Phase 3 persistence primitives: `user_id`, `sku_id` FK, `quantity` constrained to 1..20, per-item `version`, timestamps, `(user_id, sku_id)` uniqueness and restrictive Catalog deletion semantics. No Phase 3 migration is required for PATCH/DELETE/CLEAR or summary fields because summaries and warnings are derived read-model data.

The current `GET /api/cart` is read-only and returns live Catalog SKU/Product names, current Decimal price, sale status and live Inventory availability. It currently returns only `items`; it does not expose item count, total quantity, subtotal, currency or warning aggregation. Cart reads do not commit or mutate data. Phase 2 confirmation already uses the same ShopMind Cart repository primitives, merges quantity by SKU and revalidates Catalog/Inventory in the transaction.

Phase 3A Backend will add direct Cart mutations without PendingAction: PATCH quantity with `expected_version`, DELETE item, and DELETE current-user Cart. All mutation requests derive owner identity from `IdentityBoundary`; no request may override `user_id`, `sku_id`, product, price or inventory. PATCH locks the owned Cart row, checks version, re-reads active Catalog Product/SKU and Inventory, rejects insufficient stock with a typed 409, and never auto-clamps quantity. DELETE is owner-scoped and idempotent (204 for missing/other-owner IDs); CLEAR affects only the current user's `shopmind_cart_items` and is also idempotent. Repository/service code flushes only; the route owns commit/rollback.

Cart public errors use a separate generated Cart domain contract rather than `ActionErrorResponse`. The minimum codes are `cart_item_not_found`, `cart_version_conflict`, `invalid_quantity`, `cart_quantity_limit`, `insufficient_inventory`, `product_inactive`, `sku_inactive`, `catalog_not_found`, and `inventory_missing`. The same safe not-found behavior is used for unknown and other-owner item IDs. Inactive or inventory-missing items remain readable and deletable but cannot be increased or updated.

The Phase 3 read model will add `item_count`, `total_quantity`, `subtotal`, `currency` and `warnings`. Current seed/catalog data uses CNY, so a single-CNY subtotal is the initial contract. Mixed currencies must never be added arithmetically; the contract will return a null subtotal/currency plus a stable currency warning (or a future per-currency totals extension). Warnings are derived only from current facts (`out_of_stock`, `inventory_missing`, `product_inactive`, `sku_inactive`). The current Cart has no historical price snapshot, so Phase 3 will not claim `price_changed_since_added`; adding `added_price_snapshot` is deferred until an order/checkout requirement justifies a migration.

Phase 3B Frontend will extend the existing read-only `CartPanel`/`CartItem` rather than introduce checkout UI: quantity input/stepper, current subtotal and summary, delete and clear actions, version-conflict refresh, insufficient-inventory and inactive-item handling, identity-isolated query invalidation, and accessible confirmation for clear. It will regenerate OpenAPI types and add API client methods. Cart mutations do not create PendingActions.

Checkout, Order, Inventory reservation, Payment, Redis, RocketMQ and Outbox remain Phase 4+ scope.

### Phase 3A-Backend — ShopMind Cart Management (implemented and accepted)

Phase 3A adds direct, owner-bound SKU Cart management while preserving the existing
`shopmind_cart_items` table and all Phase 2 PendingAction semantics. `GET /api/cart`
now returns the complete summary read model; `PATCH /api/cart/items/{cart_item_id}`
uses an absolute quantity and `expected_version`; item DELETE and Cart CLEAR are
idempotent `204` operations. The request body contains only
`expected_version` and `quantity`; identity is resolved exclusively by the server's
`IdentityBoundary`.

`app/services/cart.py` is the sole mutation semantic entrypoint. It locks the
owned CartItem, validates the version, reads current Product/SKU/Inventory facts,
rejects inactive/missing/insufficient inventory and flushes the quantity/version
change. Catalog rows are read-only in this phase so the CartItem remains the
serialization point and cannot deadlock the Phase 2 confirm lock order. Routes
own commit/rollback; repositories never commit. Inventory is never reserved,
decremented or otherwise changed, and the legacy `cart_items` table is untouched.

Cart uses separate typed `CartErrorResponse` and `CartWarning` contracts. Mixed
currency carts return null subtotal/currency with `mixed_currency`; a single
currency uses Decimal-based Money strings. Unknown and other-owner PATCH IDs
share safe `cart_item_not_found` behavior, while DELETE hides existence and
always returns `204` for missing/other-owner IDs. No Phase 3B frontend business
code, Checkout, Order, Payment, Redis, RocketMQ or Outbox work is included.

### Phase 4A Checkout/Order Backend (accepted/closed)

Phase 4A is accepted and closed. This backend-only patch provides Checkout Preview and
pending-payment Order reservation/cancellation. It deliberately excludes frontend work, payment, automatic
expiration, address/shipping/tax, Redis, RocketMQ, and Outbox/Inbox.

Latest Phase 4A validation records `4 passed` for real HTTP API/OpenAPI, `34 passed` for Phase 2/3 plus
Phase 4 focused regression, `6 passed` for Phase 3 PostgreSQL Cart, `11 passed` for the Phase 4 PostgreSQL
matrix, `17 passed` for the combined PostgreSQL suites, and `git diff --check` exit code `0`.

### Phase 5A Mock Payment Backend (accepted/closed)

Phase 5A adds the ShopMind Mock Payment Attempt backend after Phase 4A.
Migration `0013_shopmind_payments` adds `shopmind_payment_attempts`, extends
Order status with `paid`, and extends Inventory Reservation status with
`consumed` and `consumed_at`. Payment Attempts use the states `processing`,
`unknown`, `provider_succeeded`, `failed`, and `succeeded`.

The payment service claims an attempt and commits before calling the
server-owned Mock Provider. It commits the provider outcome before local
finalization, then locks Order, PaymentAttempt, Reservations and Inventory in
the documented order. Successful finalization consumes every Reservation,
decrements on-hand and reserved Inventory, increments `Inventory.version`
exactly once, and marks the Order `paid`. Same-key replay/resume is owner-bound
and request-hash bound; a different request with the same key returns
`idempotency_conflict`. Declines leave the Order pending and Reservations active.
The request never accepts amount, currency, user identity or provider scenario
controls.

Phase 5A is accepted and closed. Phase 5B frontend, real payment providers,
webhooks, refunds/chargebacks, and automatic reconciliation remain outside the
implemented backend scope.

### Phase 6A Transactional Outbox + RocketMQ (accepted/closed)

Phase 6A adds migration `0014_shopmind_outbox_events` after
`0013_shopmind_payments`. The separate Outbox model stores immutable,
versioned Order events and mutable delivery state with lease/status CHECK
constraints, aggregate sequence uniqueness, bounded retry/backoff, dead-letter
redrive, and compare-and-set completion. Create, Cancel, and successful
Payment finalization enqueue their event in the same transaction as the
corresponding Order, Reservation, Inventory, and Payment facts.

The standalone publisher claims in short PostgreSQL transactions and calls
RocketMQ only after claim commit. `RocketMQPublisher` lazy-loads the pinned
Apache Python SDK and sends FIFO messages to `shopmind-order-events-v1` with
the Order ID as message group, event type as tag, and event ID as key. The API
does not start the worker and does not require the SDK. `scripts/redrive_outbox.py`
is the only Phase 6A dead-letter redrive entrypoint.

Phase 6A is accepted and closed. The API still does not require the RocketMQ
SDK; publisher startup remains an explicit advanced operation. Consumer, Inbox,
deduplication consumer, webhook, automatic reconciliation worker, Redis and
RocketMQ consumer orchestration remain deferred.

### Phase 6B-1 Core Demo Packaging (accepted/closed)

The current ShopMind web frontend, deterministic `offline-demo` profile and
`scripts/start_shopmind_demo.ps1` now provide a repeatable Prepare/Start/Verify
path for PostgreSQL, Backend, Frontend and the seeded Catalog. Prepare is
loopback/marked-database guarded and runs only idempotent migration and seed
operations. Verify and the separate live Playwright gate exercise the real
Recommendation -> PendingAction -> Cart -> Checkout -> Order -> Mock Payment
path and assert PostgreSQL Reservation, Inventory and versioned Outbox facts.
LangSmith is disabled and RocketMQ remains an optional Advanced Reliability
Demo, never a core startup dependency. Phase 6B-1 and Phase 6B-2 are accepted
and closed. Project Closure implementation is in progress; Inbox/Consumer is
deferred.
