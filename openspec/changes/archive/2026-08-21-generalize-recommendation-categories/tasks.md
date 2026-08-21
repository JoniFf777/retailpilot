## 1. Audit, baseline, and contract inventory

- [x] 1.1 Record Apply-before `git status --short` and `git diff --stat`, preserving all pre-existing dirty worktree files.
- [x] 1.2 Record the current Laptop-only gate/parser/provider/service/graph/frontend flow with exact source references and identify legacy TECH heuristics.
- [x] 1.3 Confirm Monitor is supported by real repository data (`data/structured/products.json`, `data/documents/products/TECH-MON-*`) and define the minimal managed seed extension.
- [x] 1.4 Re-read the six existing main specs and add regression assertions/notes for their protected boundaries without modifying those main specs.

## 2. Generic recommendation contracts

- [x] 2.1 Add the shared `RecommendationRequest` envelope for category, generic budget/currency, availability, generic preferences, and bounded category attributes.
- [x] 2.2 Extend `RecommendationResult` and `Recommendation` additively with category, request/category attributes, and machine-readable resolution/error fields while preserving existing Laptop fields/defaults.
- [x] 2.3 Add typed Monitor category attribute validation and explicit policy/display metadata without adding Monitor fields to the global Laptop constraints model.
- [x] 2.4 Preserve `RecommendationResult` validation, persistence, replay, and projection compatibility for existing Laptop/test fixtures.

## 3. Category resolution

- [x] 3.1 Extend the recommendation gate with machine-readable Laptop/Monitor resolution while preserving the existing write-intent guard.
- [x] 3.2 Add deterministic ambiguous-category clarification behavior with a stable `category_ambiguous` code.
- [x] 3.3 Add deterministic unsupported-category behavior with a stable `unsupported_category` code and no Laptop fallback.
- [x] 3.4 Add graph resolution handling so ambiguous/unsupported outcomes end safely before catalog retrieval and ranking.

## 4. Shared policy and deterministic recommendation service

- [x] 4.1 Introduce the small static category-policy seam and shared orchestration for candidate input, generic availability/budget filtering, scoring, SPU de-duplication, Top K, and stable tie-breaking.
- [x] 4.2 Move the existing Laptop parser/scoring behavior behind the Laptop policy while preserving `build_laptop_recommendation` compatibility and ranking policy behavior.
- [x] 4.3 Implement Monitor parsing for size, resolution, refresh rate, panel type, and use-case attributes.
- [x] 4.4 Implement Monitor hard constraints for active/available SKU, budget, size, resolution, and refresh rate.
- [x] 4.5 Implement Monitor soft ranking, bounded score breakdown, missing-attribute neutral/penalty semantics, and deterministic `(-score, price, sku_code)` ordering.
- [x] 4.6 Ensure cross-category attributes cannot affect the other policy and unknown fields fail closed without LLM inference.

## 5. Catalog retrieval and managed data

- [x] 5.1 Generalize Catalog candidate retrieval and provider interfaces by category while retaining `list_active_laptop_skus` compatibility.
- [x] 5.2 Ensure ordered category AttributeDefinitions and canonical Product/SKU/inventory facts populate candidates for both categories.
- [x] 5.3 Add the minimal managed Monitor seed with real `TECH-MON-006`–`TECH-MON-009` identities, attributes, prices, sale status, and inventory cases.
- [x] 5.4 Extend the existing seed command only as needed to seed the Laptop and Monitor managed files without resetting legacy data or inventory.

## 6. Graph, RAG, commerce, and runtime integration

- [x] 6.1 Route both supported categories through one recommendation graph path and shared service; do not add a copied Monitor pipeline.
- [x] 6.2 Preserve top-K-before-RAG ordering and existing RAG success/partial/degraded/failed semantics for both categories.
- [x] 6.3 Preserve recommendation context and canonical SKU identity for add-to-cart PendingAction preparation.
- [x] 6.4 Verify Agent/LLM paths remain read/intent-only and cannot directly mutate Cart or other domain state.
- [x] 6.5 Verify Chat JSON/SSE, retry/replay, safe error projection, and authoritative Run identity remain unchanged for category-aware runs.

## 7. Frontend and generated contract

- [x] 7.1 Update OpenAPI-generated frontend types through the existing generation script after public schema changes.
- [x] 7.2 Extend shared recommendation constraints/category display to render Laptop and Monitor fields without duplicate category pages/cards.
- [x] 7.3 Preserve existing SKU selection, comparison, evidence, empty, clarification, and projection-error UI behavior.

## 8. Focused regression tests

- [x] 8.1 Add category resolution tests for Laptop, Monitor, ambiguous, unsupported, and no-Laptop-fallback outcomes.
- [x] 8.2 Add Laptop regression tests for existing parser, hard constraints, ranking, tie-break, alternatives, and structured response.
- [x] 8.3 Add Monitor tests for attributes, hard filters, price/availability, soft ranking, missing fields, no candidates, and stable ties.
- [x] 8.4 Add cross-category isolation and repeated-input determinism tests.
- [x] 8.5 Add structured response/API/SSE and recommendation-to-canonical-SKU/PendingAction regression tests.
- [x] 8.6 Add frontend Monitor rendering/comparison tests and preserve existing Laptop recommendation tests.
- [x] 8.7 Add Chat retry, HITL, safe-error, RAG semantic, and existing capability regression coverage relevant to recommendation integration.

## 9. Verification, Sync, and archive

- [x] 9.1 Complete implementation-readiness self-review for policy isolation, category resolution, hard/soft semantics, missing attributes, determinism, frontend compatibility, and commerce safety.
- [x] 9.2 Run focused backend tests with LangSmith, Redis, RocketMQ, and external APIs disabled; run PostgreSQL only if correctness proves database-specific.
- [x] 9.3 Run the full non-integration backend suite with writable isolated basetemp and the applicable frontend focused/full Vitest, lint, typecheck, and typecheck:e2e checks.
- [x] 9.4 Run OpenSpec change/main-spec strict validation and `git diff --check`; document scope compliance and any remaining future work.
- [x] 9.5 Sync `recommendation-categories` into its main spec, verify the six existing main specs are unchanged, and revalidate.
- [x] 9.6 Archive with `--skip-specs`, validate specs and archived changes, confirm no active changes, and generate the final review ZIP.
