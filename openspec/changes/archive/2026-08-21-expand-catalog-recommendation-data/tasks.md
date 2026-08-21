## 1. Audit and baseline

- [x] 1.1 Record Apply-before git status/diff stat and preserve the dirty worktree with a relative-path baseline.
- [x] 1.2 Produce the before Data Quality Inventory for Laptop/Monitor products, SKUs, attributes, price bands, inventory, and docs coverage.
- [x] 1.3 Re-read the seven existing main specs and record protected architecture/commerce/runtime boundaries.

## 2. Deterministic data validator

- [x] 2.1 Implement reusable validator/report types for managed seed files with stable issue codes and JSON-serializable output.
- [x] 2.2 Validate unique category/product/legacy/SKU identifiers and Product/SKU/category relationships.
- [x] 2.3 Validate sale status, positive money/currency, inventory invariants, and declared attribute types/values.
- [x] 2.4 Validate Laptop/Monitor hard-required recommendation attributes and intentionally missing soft-field policy.
- [x] 2.5 Validate managed legacy product document existence and identity alignment without making documents factual authority.
- [x] 2.6 Add an executable validator command with deterministic non-zero failure behavior.

## 3. Managed data expansion

- [x] 3.1 Add plausible Laptop managed rows covering value, development, portable, gaming/performance, price bands, close scores, and unavailable inventory.
- [x] 3.2 Add plausible Monitor managed rows covering office, high-refresh gaming, high-resolution, size/panel preferences, price bands, close scores, and unavailable inventory.
- [x] 3.3 Preserve all existing canonical Product/SKU identifiers and ensure new rows use unique stable identifiers.
- [x] 3.4 Add product documents for all new managed legacy identities using the existing corpus format.
- [x] 3.5 Run the validator against the expanded seed and record before/after counts and remaining gaps.

## 4. Seed idempotency and policy fixtures

- [x] 4.1 Extend clean/repeated seed tests to include both managed Laptop and Monitor files.
- [x] 4.2 Prove rerun creates no duplicate Products/SKUs and preserves mutated inventory quantities.
- [x] 4.3 Add Laptop data-driven recommendation scenarios for value/development/portable/gaming, hard constraints, no-match, and unavailable filtering.
- [x] 4.4 Add Monitor data-driven recommendation scenarios for office/gaming/resolution/size/panel, hard constraints, no-match, and unavailable filtering.
- [x] 4.5 Add close-score deterministic tie and repeated-input ordering tests.
- [x] 4.6 Add cross-category isolation tests proving Laptop attributes do not affect Monitor and vice versa.
- [x] 4.7 Add Catalog/RAG authority and document identity alignment tests.

## 5. Commerce and regression protection

- [x] 5.1 Verify newly managed Laptop and Monitor SKU selections retain canonical PendingAction/HITL/expected-version/Cart behavior.
- [x] 5.2 Verify Chat retry, safe error, RAG semantics, Agent write boundary, and existing recommendation-category contracts remain green.
- [x] 5.3 Confirm no new legacy Cart writer, direct Agent write, or recommendation architecture seam is introduced.

## 6. Verification and lifecycle

- [x] 6.1 Complete readiness self-review for data plausibility, stable IDs, validator coverage, seed safety, Catalog authority, and scope.
- [x] 6.2 Run validator and focused backend/data/recommendation tests with external services disabled.
- [x] 6.3 Run full non-integration backend suite with writable isolated basetemp.
- [x] 6.4 Run frontend focused/full Vitest, lint, typecheck, typecheck:e2e, and OpenAPI checks if schema changed.
- [x] 6.5 Decide PostgreSQL necessity from actual implementation; if Not Required, document why; otherwise use only isolated `retailpilot_v2_smoke_test`.
- [x] 6.6 Run strict change/spec validation, git diff check, and complete scope review.
- [x] 6.7 Sync `catalog-recommendation-data-quality`, verify all seven existing main specs unchanged, and validate.
- [x] 6.8 Archive with `--skip-specs`, validate specs/archived artifacts, confirm no active changes, and generate final review ZIP.
