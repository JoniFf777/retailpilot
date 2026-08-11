# Phase 3 Preflight — ShopMind Cart Management

Date: 2026-08-07
Status: **audit complete; Phase 3 implementation not started**

This report is based on the current Phase 2A/2B code, migrations and tests. It does not authorize or include database, API, frontend, Graph, Runtime, Order, Payment, Redis, RocketMQ or Outbox implementation changes.

## 1. Current ShopMind Cart architecture

`alembic/versions/0011_shopmind_cart.py` and `app/cart/models.py` define `shopmind_cart_items` with:

| Field/constraint | Current reality |
|---|---|
| identity | `id` UUID primary key, `user_id`, `sku_id` |
| Catalog relation | restrictive FK to `shopmind_product_skus.id`; Product is reached through SKU → Product |
| uniqueness | `UNIQUE(user_id, sku_id)` |
| quantity | database and domain checks enforce `1..20` |
| concurrency | per-item integer `version`, initial value 1 |
| timestamps | `created_at`, `updated_at` |
| price snapshot | none |
| inventory reservation | none |
| legacy relation | none; legacy `cart_items` is a separate compatibility path |

The schema is sufficient for Phase 3 Cart CRUD and derived summary data. No migration is required for the planned PATCH/DELETE/CLEAR operations.

## 2. Current read model and fact sources

`GET /api/cart` is registered in `app/api/routes/cart.py` and calls `list_cart_items`. The repository executes one joined read over ShopMind Cart, Catalog SKU, Catalog Product and optional Inventory. It does not commit and does not mutate the database.

The current `CartItemView` contains product/SKU identity, current SKU money, quantity, current sale statuses, timestamps, version and live availability. Price is read from `CatalogSku.money_amount`; sale status is read from Catalog Product/SKU; availability is computed from `on_hand_quantity - reserved_quantity`, with `inventory_missing`, `out_of_stock`, `product_inactive` and `sku_inactive` reason codes. The current `CartResponse` contains only `items`; it has no item count, total quantity, subtotal, currency or aggregate warnings.

The current catalog seed uses CNY. Phase 3 will therefore expose a single-CNY subtotal initially, while explicitly rejecting arithmetic across mixed currencies. If a future Catalog introduces multiple currencies, the response must use per-currency totals or a null subtotal with a stable warning; it must never add unlike currencies.

Because `shopmind_cart_items` stores no historical price, the current code cannot truthfully report `price_changed_since_added`. Phase 3 will not invent that warning. An `added_price_snapshot` migration is deferred until checkout/order semantics require a durable price reference.

## 3. Phase 2 confirmation relationship

`app/services/pending_actions.py` already reuses `app/repositories/shopmind_cart.py` for add-to-cart confirmation. It locks the existing `(user_id, sku_id)` row, re-reads Catalog Product/SKU/Inventory, checks active status and available quantity, merges quantity, increments CartItem version on an existing row, and flushes. The route owns commit/rollback. Inventory is not reserved and is never changed by Cart confirmation.

Phase 3 direct Cart PATCH/DELETE/CLEAR will share repository primitives and the same transaction boundary, but will not create a PendingAction. The existing Recommendation → add-to-cart PendingAction flow remains unchanged.

## 4. Phase 3 API contract decision

Planned endpoints:

```text
GET    /api/cart
PATCH  /api/cart/items/{cart_item_id}
DELETE /api/cart/items/{cart_item_id}
DELETE /api/cart
```

PATCH body is exactly:

```json
{
  "expected_version": 1,
  "quantity": 2
}
```

It does not accept `user_id`, `sku_id`, `product_id`, price or inventory. Owner identity comes from `IdentityBoundary`; a development identity may continue to use the existing development adapter, but the request body cannot override the resolved owner.

PATCH uses absolute quantity semantics and requires `expected_version`. It locks the owned Cart row, checks the version, reads the current Catalog Product/SKU and Inventory facts, then validates active status, `1..20` and current available quantity. Catalog facts are read-only in this phase; the CartItem is the mutation serialization point and this lock order remains compatible with Phase 2 confirmation. On failure the existing quantity and version remain unchanged. `insufficient_inventory` is HTTP 409. Inactive and inventory-missing items remain readable and deletable, but cannot be increased or updated.

DELETE item does not require a version. For the current owner, repeated deletion and an unknown/other-owner ID both return the same idempotent `204` behavior, preventing ownership enumeration. DELETE Cart has the same idempotent semantics and only removes the current user's `shopmind_cart_items`; it never touches legacy `cart_items`, another user or Inventory.

Cart errors are a separate public contract (`CartErrorResponse`/`CartErrorDetails`), not `ActionErrorResponse`, because these operations are not PendingAction transitions. The planned code set is:

```text
cart_item_not_found
cart_version_conflict
invalid_quantity
cart_quantity_limit
insufficient_inventory
product_inactive
sku_inactive
catalog_not_found
inventory_missing
```

`cart_item_not_found` is used for a PATCH lookup miss and the same safe result is used for an owner mismatch. The response includes stable details such as `current_version` and `available_quantity` only when safe and relevant.

Successful PATCH returns a typed `CartMutationResponse` containing the updated `item` and the refreshed `cart` read model. DELETE item and DELETE Cart return `204` with no body. The planned generated read contracts are:

```text
CartResponse {
  items: CartItemView[]
  item_count: integer
  total_quantity: integer
  subtotal: Money | null
  currency: string | null
  warnings: CartWarning[]
}

CartMutationResponse {
  item: CartItemView
  cart: CartResponse
}
```

`CartWarning` is a typed `{ code, sku_id, cart_item_id, message }` projection. The server remains the source of warning codes; the frontend does not infer business state from an empty list or from natural-language text.

## 5. Transaction and concurrency boundary

The shared mutation service will follow:

```text
resolve effective owner from IdentityBoundary
→ SELECT CartItem FOR UPDATE by (cart_item_id, owner)
→ validate expected_version (PATCH only)
→ SELECT Product/SKU/Inventory (read-only current facts)
→ validate status, quantity and available inventory
→ update quantity + version + updated_at, or delete rows
→ flush
→ route commits; route rolls back on every error
```

Two PATCH requests based on version 1 therefore allow at most one success; the other receives `cart_version_conflict` and can refresh the latest Cart. Inventory is read-only in Phase 3 and is never reserved, decremented or otherwise mutated. Repository methods must not call `commit()`.

## 6. Phase 3A Backend file-level plan

No implementation is being performed in this preflight. The approved implementation slice is:

| File | Planned responsibility |
|---|---|
| `app/schemas/cart.py` | Move/define generated Cart read, summary, warning, mutation request/response and CartError contracts; keep PendingAction contracts separate |
| `app/repositories/shopmind_cart.py` | Add owner-scoped item lookup with lock, quantity update, delete, clear and summary projection; keep flush-only behavior |
| `app/services/cart.py` | Centralize PATCH/DELETE/CLEAR validation, Catalog/Inventory re-read and transaction-safe business errors; reuse from future callers and Phase 2 confirmation where practical |
| `app/api/routes/cart.py` | Add PATCH/DELETE item/CLEAR routes, IdentityBoundary binding, typed errors and route-owned commit/rollback; preserve GET behavior with enriched read model |
| `app/api/router.py` | Registration check only; the existing Cart router is already included |
| `tests/cart/test_phase3_service.py` | Unit/service matrix for boundaries, inactive/missing inventory, no clamping, owner isolation, rollback and summary |
| `tests/api/test_phase3_cart.py` | Request shape, IdentityBoundary, status/error projection, idempotent DELETE/CLEAR and legacy-cart isolation |
| `tests/integration/test_phase3_postgres_cart.py` | Real PostgreSQL constraints, concurrent PATCH, version conflict, rollback and live Catalog/Inventory re-read |
| `tests/api/test_openapi_schema.py` | Generated Cart schema and error enum assertions |

Expected migration result: **none**. Any later price snapshot or order reservation must be a separately reviewed migration, not hidden in Phase 3 CRUD.

## 7. Phase 3B Frontend file-level plan

| File | Planned responsibility |
|---|---|
| `frontend/openapi.json`, `frontend/src/api/openapi.generated.ts` | Regenerate only after Phase 3A API acceptance |
| `frontend/src/api/contracts.ts` | Generated aliases for Cart summary, warning, mutation and error types |
| `frontend/src/api/client.ts` | `updateCartItem`, `deleteCartItem`, `clearCart` methods; mutation requests omit owner/product/price/inventory fields |
| `frontend/src/features/cart/CartPanel.tsx` | Editable read model, summary, query invalidation and clear confirmation; retain current identity query key |
| `frontend/src/features/cart/CartItem.tsx` | Quantity input/stepper, save/delete controls, current price/subtotal, warnings and disabled states for inactive items |
| `frontend/src/features/cart/cartFormatters.ts` | Money, summary and warning copy without inventing historical price changes |
| `frontend/src/features/cart/*.test.tsx` | loading/empty/error, quantity 1/20, success, version conflict refresh, inventory shortage, inactive/delete, clear and identity switching |
| `frontend/e2e/critical-path.spec.ts` or a dedicated Cart spec | Preserve Phase 1B/2B scenarios and add seven Cart Management mock scenarios |

Phase 3B remains read/write Cart only. No checkout button may imply an active checkout API; if shown, it must be disabled and explicitly marked as a later phase.

## 8. Required acceptance matrix

Backend PostgreSQL tests must cover normal PATCH, quantity 0/21, insufficient inventory, Product inactive, SKU inactive, missing Inventory, owner isolation, version conflict, timestamp/version changes, unchanged Inventory and rollback; two-session concurrent PATCH must produce at most one success. DELETE and CLEAR must cover owner isolation, repeated calls, other-user isolation and legacy Cart non-interference.

Frontend tests must cover loading/empty/error, quantity boundaries, successful update, version conflict + refresh, insufficient inventory without silent clamping, inactive item readable/deletable but not editable, item delete, clear confirmation, TanStack Query invalidation and development identity switching. Existing Phase 1B/2B E2E scenarios remain mandatory.

## 9. Explicit non-goals and open decisions

- No Order, Checkout, reservation, Payment, Redis, RocketMQ or Outbox.
- No PendingAction for direct reversible Cart mutations.
- No price history warning until a durable snapshot is justified by checkout/order requirements.
- No migration is required for the current Phase 3 scope.
- Single-CNY subtotal is the initial contract; mixed-currency handling must be added before any non-CNY Catalog data is accepted.

Git and implementation gate for this preflight: no stage, no commit, and no Phase 3 code changes.
