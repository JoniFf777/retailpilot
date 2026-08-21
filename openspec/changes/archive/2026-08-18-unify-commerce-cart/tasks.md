## 1. Baseline and contracts

- [x] 1.1 Record the current legacy and structured add-to-cart call graph, including the exact production callers and the tests that currently assert `cart_items` versus `shopmind_cart_items`.
- [x] 1.2 Define the canonical adapter input/output contract, including machine-readable `prepared`, `clarification_required`, `failed`, and `confirmed` outcomes and typed codes for mapping, collision, availability, owner, expiry, version, and persistence failures.

## 2. Identifier normalization

- [x] 2.1 Add a collision-safe Catalog resolver that queries exact `sku_code`, `legacy_product_id`, and `product_code` namespaces together, converges only identical concrete targets, and never applies silent namespace precedence or fuzzy matching.
- [x] 2.2 Add resolver coverage for unique-SKU resolution, same-SKU cross-namespace convergence, different-target cross-namespace collision (`catalog_identifier_ambiguous`), missing mapping, and bounded diagnostics.
- [x] 2.3 Implement the one-SKU versus multi-SKU rule: auto-select only one concrete SKU; return a machine-readable clarification outcome for multiple variants without creating a Cart mutation or misreporting it as ordinary failure.
- [x] 2.4 Reuse current sellability, inventory-availability, and quantity validation for the resolved SKU and add failure-path tests proving no mutation on rejection.

## 3. Canonical PendingAction adapter

- [x] 3.1 Extract or add the smallest shared PendingAction factory and typed adapter result needed to create the versioned canonical SKU payload/snapshots for both structured recommendations and legacy intent; ensure business control flow never parses Chinese tool text.
- [x] 3.2 Preserve structured recommendation provenance and candidate validation while routing its existing behavior through the shared factory without changing its public endpoint contract.
- [x] 3.3 Add a legacy-intent preparation adapter that resolves the identifier before creating a canonical SKU PendingAction, records bounded origin metadata, and returns a clarification/failure instead of a legacy fallback.
- [x] 3.4 Ensure PendingAction preview/edit schemas render canonical SKU data for newly adapted legacy actions; historical legacy payloads remain readable/cancellable where supported but canonical confirm returns typed `unsupported_action_schema` without invoking either Cart writer.

## 4. Confirmation and transaction boundary

- [x] 4.1 Route the formal `tools.cart.prepare_add_to_cart` path used by V1/V3 Chat to the canonical preparation adapter while preserving the tool name, pending-action ID, typed clarification outcome, and Chat response compatibility.
- [x] 4.2 Add additive `ConfirmChatRequest.expected_version` plumbing through `/api/chat/confirm`, the confirmation boundary, and the Cart confirmation tool; require the real client version for canonical add-to-cart while leaving unrelated actions compatible.
- [x] 4.3 Route formal `tools.cart.confirm_add_to_cart`/`/api/chat/confirm` to the existing typed SKU confirmation service and keep one Session/transaction per confirmation invocation.
- [x] 4.4 Verify that canonical confirmation preserves owner/thread binding, expiry, expected version, quantity edits, sale-status, inventory, price snapshot, and idempotent replay/conflict behavior, including missing/stale version rejection.
- [x] 4.5 Remove the formal production call to `app.repositories.cart.confirm_add_to_cart`; retain the legacy repository only as explicitly non-canonical compatibility/workshop code and add a no-legacy-writer/no-dual-write regression assertion.
- [x] 4.6 Ensure canonical write or commit failure rolls back and produces a typed failed response rather than a success message or legacy Cart fallback.

## 5. Canonical reads and client behavior

- [x] 5.1 Audit supported Agent/tool Cart reads and either route them to the canonical Cart service or remove them from the formal ShopMind commerce path; do not make legacy `get_cart_items` a second Cart truth.
- [x] 5.2 Make the frontend send the loaded real `PendingActionView.version` for legacy canonical confirmation, refuse confirmation when no real version is available, and invalidate/refetch canonical Cart plus clear stale Checkout Preview after successful legacy or structured add-to-cart confirmation without redesigning Cart or Checkout UI.

## 6. Focused verification

- [x] 6.1 Add service tests for typed outcomes, same-target convergence, cross-namespace collision, unique-SKU selection, multi-SKU clarification, missing mapping, inactive/out-of-stock SKU, invalid quantity, rollback, and no legacy fallback.
- [x] 6.2 Update/add legacy tool and Write Handoff tests to assert typed clarification/failure handling, canonical `ShopMindCartItem` confirmation, historical legacy-action safe failure, and unchanged legacy `CartItem` table.
- [x] 6.3 Add an API regression covering Chat intent → canonical PendingAction → `/api/chat/confirm` with real `expected_version` → `GET /api/cart`, including missing/stale version, owner/thread/expiry failures and repeated confirmation.
- [x] 6.4 Add a Cart → Checkout Preview regression proving a legacy-confirmed canonical SKU is eligible for preview, uses existing fingerprint/revalidation semantics, and never reads legacy Cart.
- [x] 6.5 Preserve and rerun structured PendingAction, Cart owner/version/inventory, and Order/Checkout local regression tests; list applicable PostgreSQL transaction/concurrency tests for later implementation validation without running integration in this proposal.
- [x] 6.6 Run applicable frontend mocked tests for real expected-version submission, successful Cart refresh, Checkout Preview invalidation, Cart visibility, and Checkout navigation/error behavior.

## 7. Final validation and scope review

- [x] 7.1 Run focused backend tests with LangSmith tracing disabled and no PostgreSQL integration, Redis, RocketMQ, or external API access; record zero failures and zero errors.
- [x] 7.2 Run the full non-integration backend suite with a writable isolated pytest basetemp and record zero failures and zero errors.
- [x] 7.3 Run frontend tests/lint/typecheck commands that actually exist, run `git diff --check`, and statically verify no formal add-to-cart path writes both Cart tables.
- [x] 7.4 Review the final diff for scope creep and confirm the archived `backend-regression-stability` behavior, Checkout/Order/inventory semantics, and public Chat contract remain intact.

## 8. Implementation review follow-ups

- [x] 8.1 Correct zero-SKU Product resolution to return typed `catalog_not_found`/canonical-SKU failure, add resolver/service/tool regression coverage, and verify no PendingAction or Cart mutation.
- [x] 8.2 Gate frontend Cart/Checkout invalidation on a genuinely successful canonical add-to-cart response; add HTTP-200 `status=failed` regression coverage and rerun focused/full verification.
