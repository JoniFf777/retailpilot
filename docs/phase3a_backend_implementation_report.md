# Phase 3A-Backend implementation and acceptance report

Date: 2026-08-07
Scope: direct ShopMind SKU Cart management only.  Phase 3B frontend business
work, Checkout/Order/Payment, Inventory Reservation, Redis, RocketMQ, Outbox,
Graph, Runtime and recommendation changes were not started.

## Implemented files

- `app/schemas/cart.py` — typed Cart summary, item, warning, mutation and
  Cart-domain error contracts. `UpdateCartItemRequest` contains only
  `expected_version` and `quantity`.
- `app/schemas/pending_actions.py` — imports the shared Cart read projections
  without changing PendingAction wire fields or transition semantics.
- `app/repositories/shopmind_cart.py` — owner-scoped row lock, update/delete/
  clear/summary projections; flush-only, never commit.
- `app/services/cart.py` — the sole direct-Cart semantic entrypoint and typed
  domain errors.
- `app/api/routes/cart.py` and `app/api/routes/_helpers.py` — GET summary,
  PATCH quantity, idempotent item DELETE/CLEAR, IdentityBoundary binding and
  route-owned commit/rollback.
- `tests/cart/test_phase3a_service.py`, `tests/api/test_phase3a_cart.py` and
  `tests/integration/test_phase3a_postgres_cart.py` — unit/API/real PostgreSQL
  acceptance coverage.
- `tests/catalog/test_postgres_acceptance.py` — corrected acceptance fixture
  to report actual dangling legacy rows rather than assuming old Product rows
  exist in every isolated database.
- `frontend/openapi.json` — exported contract evidence only; generated
  frontend business code was not changed.

No Alembic migration was added or changed. The existing `0011_shopmind_cart`
schema remains authoritative (`quantity` 1..20, `version` >= 1, unique
`(user_id, sku_id)`, restrictive SKU FK).

## Public contract and transaction semantics

`CartResponse` contains `items`, `item_count`, `total_quantity`, `subtotal`,
`currency` and typed `warnings`. A single-currency cart sums current SKU prices
with `Decimal` and serializes Money amounts as two-decimal strings. An empty
cart has null subtotal/currency. Mixed currencies do not get arithmetically
combined and return null subtotal/currency plus `mixed_currency`.

Warning codes are `mixed_currency`, `product_inactive`, `sku_inactive`,
`out_of_stock`, `insufficient_inventory` and `inventory_missing`. Errors use a
separate `CartErrorResponse` with stable codes, including
`cart_item_not_found`, `cart_version_conflict`, `cart_quantity_limit`,
`insufficient_inventory`, inactive-catalog errors and `inventory_missing`.

PATCH locks the owned CartItem, checks `expected_version`, reads current
Product/SKU/Inventory facts, validates active status and available quantity,
increments `version` and `updated_at`, and flushes. Catalog/Inventory rows are
read-only: there is no reservation, decrement, clamping or auto-delete. The
CartItem lock is the mutation serialization point and avoids a lock-order
cycle with Phase 2 confirm. Routes commit on success and rollback every typed
or unexpected error. DELETE item hides existence and returns 204 for missing or
other-owner IDs; DELETE Cart affects only the current user's ShopMind rows.

## PostgreSQL environment and migration evidence

- PostgreSQL: `16.13 (Debian 16.13-1.pgdg12+deb12u1)`.
- Isolated database: `retailpilot_phase3a_20260807` on `127.0.0.1:5432`.
- Created with `CREATE DATABASE retailpilot_phase3a_20260807`; it was kept as
  the dedicated evidence database (cleanup, when desired, is limited to
  `DROP DATABASE retailpilot_phase3a_20260807` after disconnecting test
  sessions).
- DSN (redacted): `postgresql+psycopg://postgres:***@127.0.0.1:5432/retailpilot_phase3a_20260807`.
- The existing `postgres` container was reused read-only for server access;
  the shared `retailpilot_v2_smoke` database was not changed.
- Final revision: `0011_shopmind_cart` (`head`).

Executed against the isolated database (all exit codes 0):

```text
alembic upgrade 0007
alembic upgrade 0008
alembic downgrade 0007
alembic upgrade 0008
alembic upgrade 0009
alembic downgrade 0008
alembic upgrade 0009
alembic upgrade head
alembic current
```

`alembic current` reported `0011_shopmind_cart (head)`. Live metadata showed
all five Catalog tables and `shopmind_cart_items`; downgrade removed the
corresponding Catalog tables and a later upgrade recreated them without
residual conflicts. PostgreSQL reported the root-category constraint as
`UNIQUE NULLS NOT DISTINCT (parent_id, code)`, and the Cart table constraints
as quantity 1..20, version >=1, unique owner/SKU and restrictive SKU FK.
An actual SQLAlchemy Inspector versus ORM metadata comparison returned `True`
for every column set across all six ShopMind Catalog/Cart tables.
Legacy `products` and `cart_items` remained present and were not modified.
The round-trip was deliberately run at dedicated-database level rather than a
search-path-only schema: historical revision `0010_pending_action_contract`
uses unqualified `pending_actions` DDL, and a schema-only harness can resolve a
same-named public table. The dedicated database run above is the authoritative
live acceptance evidence.

The real PostgreSQL seed run in the isolated database inserted
`1/7/5/5/5` categories/attributes/products/SKUs/inventory on the first run and
`0/0/0/0/0` on the second, with managed records skipped on repeat. That
isolated database intentionally contained no copied legacy Product rows, so it
reported five dangling legacy IDs. A read-only inspection of the existing
shared smoke database confirmed all five Laptop legacy IDs (`TECH-LAP-001` to
`TECH-LAP-005`) exist there; no shared data was altered. Catalog resolution
remains usable even when reconciliation reports a dangling old row.

## Acceptance results

Commands and results:

```text
pytest tests/cart -q -p no:cacheprovider                         17 passed
pytest tests/api -q -p no:cacheprovider                           77 passed
pytest tests/repositories -q -p no:cacheprovider                 40 passed
pytest tests/catalog -q -p no:cacheprovider                        9 passed, 2 skipped
pytest tests/recommendation -q -p no:cacheprovider                12 passed
pytest tests/db/test_models.py tests/docs -q -p no:cacheprovider  20 passed
pytest tests/integration/test_phase3a_postgres_cart.py -q ...       6 passed
pytest tests/integration/test_phase2a_postgres_acceptance.py -q ... 5 passed
pytest tests/catalog/test_postgres_acceptance.py -q ... -k ...      3 passed, 1 deselected
```

The real PostgreSQL Cart tests covered exact available quantity, shortage,
inactive/missing catalog facts, unchanged Inventory, owner isolation, rollback,
idempotent DELETE/CLEAR, constant summary SQL and two-session PATCH/PATCH and
PATCH/Phase2-confirm races. PATCH/PATCH produced exactly one update and one
`cart_version_conflict`; PATCH/confirm produced no lost update and final
quantity remained a serialized value (`2` or `3`). A live PostgreSQL Cart GET
was instrumented at one SQL statement for the selected user (no per-item N+1
query).

OpenAPI export:

```text
python scripts/export_openapi.py --output frontend/openapi.json
OpenAPI exported ... (55 schemas)
```

The generated contract contains `CartResponse`, `CartMutationResponse`,
`CartWarning`, `CartErrorResponse`, `CartErrorDetails`, `CartItemView` and
`UpdateCartItemRequest`; the latter has exactly the two allowed body fields.

Final whitespace check:

```text
git diff --check
exit code: 0
```

Phase 3A-Backend acceptance is complete based on the isolated real PostgreSQL
round-trip, direct Cart concurrency/rollback tests, Phase 2 regression and
OpenAPI contract export. No files were staged or committed, no remote workflow
was triggered, and Phase 3B was not started.
