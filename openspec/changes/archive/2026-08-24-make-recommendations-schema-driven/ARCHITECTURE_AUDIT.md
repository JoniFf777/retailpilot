# Architecture Audit — make-recommendations-schema-driven

Audit date: 2026-08-24

## Result

PASS. The ordinary recommendation path is registry-driven and generic. The source/AST guard tests pass and found no `test_accessory` or `battery_wh` literal in the generic request, constraint, ranking, gate, graph, validator, or frontend renderer paths.

## Generic path findings

- `app/recommendation/categories/models.py` and `registry.py` own typed definition loading, validation, alias resolution, schema lookup, catalog attribute validation, and deterministic discovery.
- `app/recommendation/request.py` iterates the selected definition; it has no Laptop/Monitor parser branch and no business-attribute-name branch.
- `app/recommendation/constraints.py` implements the common type/operator matrix; `ranking.py` implements generic filtering, bounded signals, missing semantics, weighted score, and stable ordering.
- `app/recommendation/service.py` resolves a definition and calls generic ranking/projection. `build_laptop_recommendation` and `build_monitor_recommendation` are thin released-entry adapters; they do not implement selection, filtering, or scoring.
- `agents/shopmind_multi_agent/recommendation_nodes.py` uses one `structured_recommendation` graph path and rejects missing category rather than selecting a fallback.
- `scripts/validate_shopmind_catalog.py` loads the registry and contains no `REQUIRED_ATTRIBUTES[category]` map or category-specific enum validation branch.
- React recommendation production components iterate returned metadata. No `category === ...` render branch remains in the recommendation feature.

## Allowed compatibility surface

The following remaining category strings are explicitly outside the generic engine:

1. `app/recommendation/compatibility.py` translates the released Laptop-shaped `LaptopConstraints` projection. It is not used for category resolution, candidate filtering, ranking, or ordinary-category registration. Removal condition: once released persisted/public consumers no longer require `structured_constraints`.
2. `app/recommendation/constraints.py::parse_laptop_constraints` delegates to the generic parser and only adapts its typed request to the released Laptop model. Removal condition: old direct callers migrate to `parse_recommendation_request`.
3. `build_laptop_recommendation`, `build_monitor_recommendation`, and Laptop-named provider/repository wrappers preserve released call sites. They delegate to generic APIs and are not called by the generic graph.
4. Existing Laptop/Monitor seed filenames and test fixtures remain data/test references, not semantic maps.

No complete `LaptopPolicy`, `MonitorPolicy`, `RouterPolicy`, `PhonePolicy`, or other ordinary-category production scorer exists.

## Router thought experiment

With current implementation, an ordinary Router using existing generic capabilities requires:

```text
app/recommendation/categories/router.json
data/catalog/router_catalog.json
data/documents/products/<Router documents>.md
tests/.../router fixtures and regression tests
```

It does not require modifying Gate, parser, constraints, ranking, service, graph, validator core, or React recommendation renderer. A production definition file is trusted configuration; the proof fixture uses only a test registry and test Catalog/SKU/document data.

## New attribute thought experiment

`battery_wh` works through the declared type/operator/ranking/bounds/missing/unit metadata. The generic engine never tests that literal key. The architecture proof and source guard cover this assertion.

## Scope check

No Phone/Tablet/Keyboard/Mouse/Headphones/Speaker/Camera/Router production catalog data was added. Existing Laptop/Monitor catalog data and documents were not edited. `v3.1.0` was not moved or recreated.
