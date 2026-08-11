# ShopMind Phase 4A Backend Implementation Report

Status: Phase 4A accepted and closed. Phase 4B frontend is outside this historical Phase 4A report.

## Scope and boundary

Implemented only the backend Checkout/Order slice:

- `POST /api/checkout/preview`
- `POST /api/orders`
- `GET /api/orders`
- `GET /api/orders/{order_id}`
- `POST /api/orders/{order_id}/cancel`

The slice does not implement payment attempts, payment providers, paid/completed/expired statuses, automatic expiration, shipping, address, tax, coupon, discount, FX, Redis, RocketMQ, Outbox/Inbox, or frontend/OpenAPI TypeScript generation.

Cart and Preview are read-only with respect to inventory. Order Create reserves inventory and consumes the exact Cart snapshot. Cancel releases the reservation and never restores Cart. A pending-payment reservation remains until an explicit Cancel; there is no automatic expiration.

## Files added

- `app/checkout/__init__.py`
- `app/checkout/tokens.py`
- `app/orders/__init__.py`
- `app/orders/models.py`
- `app/orders/state.py`
- `app/schemas/checkout.py`
- `app/schemas/orders.py`
- `app/repositories/shopmind_orders.py`
- `app/repositories/inventory_reservations.py`
- `app/services/checkout.py`
- `app/services/orders.py`
- `app/api/routes/checkout.py`
- `app/api/routes/orders.py`
- `alembic/versions/0012_shopmind_orders.py`
- Phase 4A unit/API/config/integration tests

## Files minimally modified

- `app/core/settings.py`
- `.env.example`
- `app/api/router.py`
- `app/api/routes/_helpers.py`
- `app/repositories/shopmind_cart.py`
- `alembic/env.py`

No frontend files were modified for Phase 4A.

## Database schema and migration

Alembic revision `0012_shopmind_orders` follows `0011_shopmind_cart` and is 20 characters long. It creates exactly three new tables:

- `shopmind_orders`: UUID id, owner, `pending_payment|cancelled` status, uppercase 3-letter currency, subtotal/total numeric money, Cart fingerprint, private idempotency key and request hash, version, created/updated timestamps. The unique constraint is `uq_shopmind_orders_user_idempotency`; list indexes are owner/created/id and owner/status/created.
- `shopmind_order_items`: order and SKU references, non-null product/SKU display snapshots, unit price, currency, quantity, line total, timestamp, order/SKU uniqueness, and database checks for positive money, quantity 1–20, uppercase currency, and exact line total arithmetic.
- `shopmind_inventory_reservations`: order-item/SKU references, quantity, `active|released` status, timestamps, one reservation per order item, SKU/status index, and the active/released timestamp consistency check.

There are no payment, address, shipping, expiration, consumed, or automatic-release columns in this revision. Order item and reservation foreign keys use the required RESTRICT/CASCADE boundaries.

The real PostgreSQL migration test uses a random private schema, creates a private baseline `pending_actions` table required by historical revision `0010`, stamps `0007`, upgrades `0008 → 0009 → 0010 → 0011 → 0012`, downgrades to `0011`, upgrades to `0012` again, and verifies public revision/table counts are unchanged.

## Checkout token and fingerprint contracts

Checkout tokens are `v1.<base64url(payload)>.<base64url(HMAC-SHA256)>`. Payload JSON is canonical UTF-8 JSON with sorted keys, compact separators, no NaN, and `shopmind.checkout-token.v1` schema. It contains only the owner fingerprint, Cart fingerprint, price fingerprint, sorted SKU price lines, currency, subtotal, issue time, and expiry time. The raw owner identifier is never placed in a token.

Owner fingerprints are domain-separated SHA-256 values. Cart fingerprints include Cart item id, SKU id, quantity, and version only. Price fingerprints include SKU id, two-decimal unit amount, and currency only. Validation rejects malformed encoding, tampering, unknown schema/fields, duplicate SKU, mixed currency, wrong owner, malformed money, and expiry. `checkout_invalid` is a typed 409; expiry is 410 and unavailable signing configuration is 503. The default development app can still start without the secret.

## Create transaction and idempotency

Create validates the request shape and Idempotency-Key, computes the exact canonical request hash, and performs the `(user_id, key)` lookup before token signature/expiry, secret, Cart, Catalog, or inventory checks. An existing equal hash replays immediately, including after token expiry, price changes, Cart consumption, or secret removal. A different hash returns `idempotency_conflict` 409.

When no row exists, Create validates the immutable token and claims a provisional Order inside a SAVEPOINT. Only the exact `uq_shopmind_orders_user_idempotency` unique violation is interpreted as a concurrent winner; other integrity errors are not converted to an idempotency error. The winner locks `CatalogSku` by SKU id, `CatalogProduct` by product id, `CatalogInventory` by SKU id, and CartItem by Cart item id in that global order, revalidates the Cart and signed prices, performs conditional inventory reservation, writes OrderItem/reservation rows, and deletes exact Cart snapshots in one route-owned transaction.

## Cancel transaction

Cancel is owner-scoped and locks the Order. Missing and cross-owner Orders return the same `order_not_found` 404. A cancelled Order replays without releasing inventory again. A pending-payment Order requires exactly one active reservation per item with matching SKU and quantity. Inventory is locked in SKU order and released with a conditional decrement; the reservation becomes released, the Order becomes cancelled, and the Order version increments. Any inconsistency rolls back the whole transaction.

## Public API and identity

Public Order responses contain only order id, status, money, snapshots, version, and timestamps. They do not expose request hash, Idempotency-Key, owner id, or owner fingerprint. Money amounts are strings. Create has the required `Idempotency-Key` header; Cancel has no Idempotency-Key and no request body. The optional `user_id` query parameter is only the existing development compatibility binding; the body never carries owner identity. Production trusted/signed identity remains owned by `IdentityBoundary`.

## Validation evidence

Latest validation results:

- HTTP API / OpenAPI: `4 passed`.
- Phase 2/3 + Phase 4 focused regression: `34 passed`.
- Phase 3 PostgreSQL Cart: `6 passed`.
- Phase 4 PostgreSQL matrix: `11 passed`.
- Combined PostgreSQL suites: `17 passed`.
- `git diff --check`: `0`.

Observed PostgreSQL outcomes:

| Scenario | Outcome | Orders | Reservation | Inventory | Cart |
|---|---|---:|---|---|---|
| Migration round-trip | private `0007 -> 0012 -> 0011 -> 0012` schema introspection succeeds | n/a | n/a | n/a | n/a |
| Last stock / partial rollback, two owners | one success; one `insufficient_inventory` 409 | 1 | one active | reserved 1, version 1 | winner consumed; loser remains |
| Same key, same request | one first result; one replay | 1 | one active | reserved 1, version 1 | consumed once |
| Same key, different request | one first result; one `idempotency_conflict` 409 | 1 | unchanged except winner | unchanged except winner | unchanged except winner |
| Expired-token replay | committed equal request replays after token expiry | 1 | one active | reserved 1, version 1 | consumed once |
| Truly concurrent same key, different request | one winner; one `idempotency_conflict` 409 | 1 | one active | reserved 1, version 1 | consumed once |
| Multi-SKU A+B / B+A | both requests complete without deadlock | 2 | four active | each SKU reserved 2, version 2 | both carts consumed |
| Mixed currency | `mixed_currency` has priority over per-line price mismatch and rolls back | 0 | none | reserved 0, version 0 | remains |
| Multi-SKU partial rollback | inventory shortage rolls back all provisional order facts | 0 | none | reserved 0, version 0 | remains |
| Corrupt reservation Cancel rollback | `reservation_inconsistent` rolls back Cancel atomically | 1 pending | one released/corrupt | reserved 1, version 1 | remains consumed |
| Concurrent Cancel | one first result; one replay | 1 | one released | reserved 0, version 2 | remains consumed |
| Create replay vs Cancel | replay and Cancel serialize | 1 cancelled | one released | reserved 0, version 2 | remains consumed |
| Create vs Phase 2 PendingAction confirm | serialized without a lost Cart update | 0 or 1 | consistent with winner | consistent with winner | confirmed action preserved |
| Price changed before Create | `price_changed` 409 and full rollback | 0 | none | reserved 0, version 0 | remains |

The real PostgreSQL checks are evidence for implementation behavior only. They do not constitute independent acceptance.

## Known limitations and handoff

Payment integration, automatic expiration, shipping/address/tax/coupon/discount/FX, distributed coordination, and frontend integration were intentionally out of scope for Phase 4A. Payment is implemented by the separate Phase 5A Mock Payment Backend.
