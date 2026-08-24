## 1. Baseline and architecture guard

- [x] 1.1 Record Apply-before Git status, HEAD/tag state, existing active changes, and baseline preimage manifest.
- [x] 1.2 Freeze the existing recommendation core, graph/nodes, frontend recommendation renderer, validator core, seed behavior, and Laptop/Monitor data paths for comparison.
- [x] 1.3 Add a test/report guard that fails if this Change modifies recommendation core or introduces new category-specific production branches.

## 2. Category definitions

- [x] 2.1 Add Phone CategoryDefinition with typed memory/storage/battery/screen/connectivity/use-case/display semantics.
- [x] 2.2 Add Tablet CategoryDefinition with typed memory/storage/screen/connectivity/portability/use-case semantics.
- [x] 2.3 Add Keyboard CategoryDefinition with typed layout/switch/connectivity/form-factor/backlight semantics.
- [x] 2.4 Add Mouse CategoryDefinition with typed connectivity/sensor-DPI/buttons/weight/use-case semantics.
- [x] 2.5 Add Headphones CategoryDefinition with typed connectivity/ANC/battery/form-factor/microphone/use-case semantics.
- [x] 2.6 Add Speaker CategoryDefinition with typed connectivity/power/battery/portability/use-case semantics.
- [x] 2.7 Add Camera CategoryDefinition with typed sensor/resolution/video/stabilization/lens/use-case semantics.
- [x] 2.8 Add Router CategoryDefinition with typed Wi-Fi generation/bands/speed/ports/coverage/use-case semantics.
- [x] 2.9 Validate ten-category Registry discovery, aliases, duplicate/conflicting definitions, enum/operator compatibility, and no fallback behavior.

## 3. Managed catalog and evidence data

- [x] 3.1 Add Phone managed Product/SKU data with price bands, available/unavailable rows, hard no-match, soft ranking, missing soft field, and tie coverage.
- [x] 3.2 Add Tablet managed Product/SKU data with the required deterministic scenario coverage.
- [x] 3.3 Add Keyboard managed Product/SKU data with the required deterministic scenario coverage.
- [x] 3.4 Add Mouse managed Product/SKU data with the required deterministic scenario coverage.
- [x] 3.5 Add Headphones managed Product/SKU data with the required deterministic scenario coverage.
- [x] 3.6 Add Speaker managed Product/SKU data with the required deterministic scenario coverage.
- [x] 3.7 Add Camera managed Product/SKU data with the required deterministic scenario coverage.
- [x] 3.8 Add Router managed Product/SKU data with the required deterministic scenario coverage.
- [x] 3.9 Add matching legacy-identity product documents for every new managed Product and verify document prose remains non-authoritative.
- [x] 3.10 Make default seed discovery include sorted `*_catalog.json` files without category-specific branches; preserve Laptop/Monitor seed behavior.

## 4. Category and recommendation tests

- [x] 4.1 Add Registry resolution/alias/ambiguous/unsupported/no-Laptop-fallback tests for all ten categories.
- [x] 4.2 Add per-category generic request, budget, hard constraint, availability, no-match, soft ranking, missing-soft, tie-break, and comparison-field tests.
- [x] 4.3 Add cross-category attribute isolation and generic-engine no-category-name/no-attribute-name branch guards.
- [x] 4.4 Run complete Agent recommendation paths for Phone, Keyboard, and Router using the existing graph and providers.
- [x] 4.5 Verify Phone and Router recommendation context reaches existing PendingAction/expected_version/canonical Cart boundaries without direct writes.

## 5. Data quality and lifecycle verification

- [x] 5.1 Run the Registry-driven Catalog validator and assert `valid=true`, zero issues, canonical identity, money, inventory, type, enum, hard-field, and document checks.
- [x] 5.2 Run category/data focused tests, recommendation/Agent/Commerce-HITL focused tests, and unchanged-core architecture comparison.
- [x] 5.3 Run full non-integration backend regression with external services disabled.
- [x] 5.4 Run frontend focused and full Vitest, lint, typecheck, typecheck:e2e, production build, and bundle budget without changing renderer source.
- [x] 5.5 Confirm PostgreSQL is Not Required unless a real seed/query semantic change is discovered; do not start or seed shared databases.

## 6. OpenSpec lifecycle and final review

- [x] 6.1 Complete implementation self-review for ten categories, data counts, unchanged core paths, generic branches, Printer onboarding, Catalog authority, and Commerce/HITL.
- [x] 6.2 Generate `ARCHITECTURE_AUDIT.md`, `ARCHITECTURE_PROOF_RESULTS.md`, data/test reports, `BASELINE_MANIFEST.md`, and baseline-to-final `CHANGE_ONLY.diff`.
- [x] 6.3 Run strict Change/spec validation and confirm only approved main specs are affected.
- [x] 6.4 Sync `electronics-catalog-coverage`, `recommendation-categories`, and `catalog-recommendation-data-quality`; verify no other main specs change.
- [x] 6.5 Archive with `--skip-specs`, run strict main/archived validation, confirm active changes are empty, and generate the final review ZIP.
