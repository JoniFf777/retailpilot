# Architecture Proof: `test_accessory`

## Claim

The proposed architecture is Apply-ready only if a third ordinary category can be exercised end-to-end by adding a test-only CategoryDefinition, catalog Product/SKU/inventory/document fixtures, and tests, without editing recommendation core, graph, validator core, or React recommendation production code.

## Test-only inputs

The proof fixture will define:

- category code `test_accessory`, display name `Test accessory`, and aliases `accessory`/`配件测试`;
- `battery_wh`: `number`, `gte`, hard, `higher_is_better`, `reject_if_hard`, unit `Wh`;
- `connection`: ordered `enum`, `enum_match`, soft, `preference_match`, neutral when missing;
- `waterproof`: `boolean`, `eq`, soft, `exact_match`, deterministic penalty when missing;
- declared comparison/display metadata for those fields;
- two or more canonical test Product/SKU candidates with money, inventory, typed attributes, and document identity.

No production category file is added by the proof. The fixture is injected into a test registry instance or loaded from a test-only definition directory supported by the registry test seam.

## Required proof flow

```text
test_accessory intent/alias
  → CategoryRegistry resolves test_accessory
  → schema-guided request validation
  → category-parameterized canonical candidate fixture
  → battery_wh hard filter
  → connection/waterproof generic signals
  → bounded normalization and deterministic tie-break
  → typed comparison_fields
  → canonical sku_id/sku_code and existing recommendation context
```

The assertions must cover:

1. alias resolution returns `test_accessory` and never Laptop;
2. wrong type, unknown key, invalid enum, missing hard field, and cross-category field fail safely;
3. candidates below `battery_wh` or outside budget are eliminated before scoring;
4. missing soft values use the declared neutral/penalty rule;
5. repeated runs with the same request/snapshot produce identical score breakdown and order;
6. the result contains typed, ordered generic comparison fields and canonical SKU identity;
7. the existing SKU-to-PendingAction context can consume the result without a category-specific write path.

## No-core-code proof guard

The Apply test suite must scan/inspect the generic Gate, parser, constraint, ranking, service, graph, catalog validator, and React recommendation renderer and fail if the implementation contains a `test_accessory` or `battery_wh` special case. It must also fail if adding the fixture requires a new ordinary-category scorer/policy, category map, graph node, or React category conditional.

## Router thought experiment

After the proof, a future Router addition is expected to touch only:

```text
categories/router.json
data/catalog/router_catalog.json
data/documents/products/<Router document ids>.md
tests/.../router fixtures and regression tests
```

It must not touch `gate.py`, parser/ranking/service core, graph routing, `RecommendationPanel.tsx`, or the validator's generic logic. If an Apply implementation needs one of those edits for ordinary Router semantics, the change is not ready to close and the design must be corrected before Archive.
