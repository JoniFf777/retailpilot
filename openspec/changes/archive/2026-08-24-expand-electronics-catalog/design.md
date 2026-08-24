## Context

The previous `make-recommendations-schema-driven` Change introduced the trusted JSON CategoryRegistry and a generic parser, constraint engine, bounded ranking engine, comparison-field projection, generic renderer, and Registry-driven validator. The current repository has two trusted definitions and two managed catalog files. This Change adds only definition/data/document/test inputs plus the smallest seed-discovery adjustment needed to discover all catalog files.

## Goals / Non-Goals

**Goals:**

- Register Phone, Tablet, Keyboard, Mouse, Headphones, Speaker, Camera, and Router using existing generic schema capabilities.
- Add realistic managed data coverage and evidence documents for all eight categories.
- Prove all ten categories resolve, validate, rank, project generic fields, and preserve Catalog authority.
- Prove at least three new categories through the Agent path and at least two through existing Commerce/HITL.
- Prove the recommendation core, graph, frontend renderer, validator core, and existing Laptop/Monitor files are unchanged by this Change.

**Non-Goals:**

- No new generic operator/ranking semantic, no category-specific Python policy, no React category branch, and no recommendation-core refactor.
- No payment/order/cart/HITL/RAG/auth/deployment/Redis/RocketMQ/PostgreSQL migration work.
- No exact product-count requirement in a long-term spec; counts are data/report facts.

## Decisions

### 1. Definitions use only already-supported primitives

Each new JSON definition uses `number`, `enum`, `boolean`, and multi-valued enum fields with existing operators, roles, ranking strategies, missing semantics, weights, bounds, aliases, and display metadata. Where a product concept is not a good fit, the field is omitted or represented by an existing generic enum/number shape rather than adding engine code.

### 2. Catalog data remains factual and documents remain evidence

Each category receives a managed `*_catalog.json` with canonical Product/SKU identity, price, inventory, status, and structured attributes. Each Product receives one matching document named by legacy identity. The validator and recommendation engine continue to treat Catalog as authority; document prose cannot override it.

### 3. Seed discovery is data-index behavior, not recommendation logic

The default seed path will discover sorted `data/catalog/*_catalog.json` files so a future data-only category is included automatically. No category code is added to the seed loop. Existing Laptop/Monitor seed files are preserved byte-for-byte.

### 4. Coverage is designed into fixtures, not production branches

Each new category has approximately nine Products, multiple price bands, available and unavailable rows, hard no-match inputs, soft preference differences, at least one omitted optional soft field, and stable SKU codes/prices for tie tests. Tests construct requests through the generic registry and use data fixtures; they do not add category dispatch logic.

### 5. Agent and Commerce verification use existing boundaries

Phone, Keyboard, and Router will run through the same multi-agent graph with fake providers and the generic Registry. Phone and Router will also exercise recommendation context into the existing PendingAction/expected-version/canonical Cart boundary. No direct write path is added.

### 6. Architecture guard compares core preimage to final worktree

The Apply baseline stores preimages for recommendation core, graph/nodes, frontend recommendation renderer, validator core, seed script, and existing Laptop/Monitor data. After Apply, a test/report compares those paths. Any difference outside the explicitly approved seed-discovery file is a blocker; any category-specific branch is a blocker.

## Risks / Trade-offs

- **[Risk]** A new attribute cannot be expressed by existing primitives. → Stop Apply and report the abstraction gap; do not edit generic engine code.
- **[Risk]** Product documents drift from Product identity. → Use legacy-id filenames and validator identity checks.
- **[Risk]** Data rows accidentally omit hard fields. → Registry validator and per-category data-quality tests fail before seed acceptance.
- **[Risk]** Category aliases collide or create ambiguous resolution. → Registry fail-fast validation and ten-category alias tests.
- **[Risk]** Large fixtures become artificial. → Keep nine varied Products/category, realistic variants only, and report counts without making them permanent requirements.
- **[Risk]** New seed discovery changes existing behavior. → Preserve existing two seed files, test deterministic sorted discovery, and run SQLite seed regression; PostgreSQL remains Not Required unless SQL behavior changes.

## Migration Plan

1. Add and validate the eight trusted definitions.
2. Add eight managed catalog files and matching documents.
3. Make the seed default discover sorted catalog files if the existing static tuple blocks data-only onboarding.
4. Add category, recommendation, Agent, Commerce/HITL, data-quality, and architecture-proof tests.
5. Run validator, focused/full backend, frontend, OpenAPI/static unchanged-core checks.
6. Sync the approved capability deltas, validate, archive with `--skip-specs`, and package the final review ZIP.

Rollback is data/configuration-level: remove or disable the eight definition/data/document files and revert only the seed discovery change. No schema or Commerce rollback is needed.

## Open Questions

None block the approved design. Exact product names/descriptions and fixture prices are managed data details, not architecture decisions.
