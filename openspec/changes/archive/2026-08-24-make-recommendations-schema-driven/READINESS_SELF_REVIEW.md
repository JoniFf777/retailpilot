# Readiness Self-Review

## Adversarial question 1: “I am adding Router. What files change?”

Target answer after Apply:

```text
categories/router.json
data/catalog/router_catalog.json
data/documents/products/<Router documents>.md
tests/.../router fixtures and regression tests
```

No `gate.py`, `parser.py`, `ranking.py`, `service.py`, `graph.py`, `RecommendationPanel.tsx`, or validator category map may be required. The active Change's tasks and `ARCHITECTURE_PROOF.md` make this a testable acceptance condition.

## Adversarial question 2: “Can `battery_wh` work without the engine knowing its name?”

Yes. The registry supplies type `number`, allowed operator `gte`, role, ranking strategy, bounds/weight, missing strategy, unit, and display metadata. The generic engine reads the definition record and never compares the literal string `battery_wh`. The architecture proof adds this exact assertion.

## Adversarial question 3: “Does this secretly recreate PhonePolicy/RouterPolicy?”

No. Ordinary categories use one `GenericRecommendationEngine`; definitions select only the closed generic primitives. A future custom hook is explicitly non-standard and may be added only when a new semantic is reusable across categories. Laptop/Monitor history is not justification for a policy hierarchy.

## Adversarial question 4: “Is the Registry really the only category source of truth?”

Target answer: yes for recommendation semantics. Gate resolution, request schema, candidate validation, ranking/display metadata, graph routing, and catalog validator consume the registry. Catalog DB attribute rows are projections/facts checked against it. React consumes result metadata and does not maintain the list. The remaining public compatibility enum/field is a migration projection, not an independent resolver.

## Adversarial question 5: “How does parsing expand without parser Python changes?”

One schema-guided extractor receives the active definition's keys, types, units, enums, aliases, and operators. It returns a bounded machine-readable envelope; the registry validates it. `camera.sensor_size`, `router.wifi_standard`, and `battery_wh` are data records, not parser branches. An LLM may extract request intent but cannot create or override catalog facts.

## Adversarial question 6: “Can a schema become another hardcoded mud ball?”

Controls are: a closed generic vocabulary; no expressions/code/imports/callbacks in definitions; fail-fast type/operator/reference validation; bounded weights/penalties/metadata; source/AST guards against literal attribute and category branches; a rule that new semantics modify the generic engine once and add cross-category tests; and the `test_accessory` proof. If a definition needs custom code, it is not an ordinary category addition and must be separately reviewed.

## Laptop/Monitor migration decision

Laptop CPU/GPU tier ordering, memory/storage/weight/screen constraints, and use-case matching are representable as ordered enums, numbers, multi-valued enums, generic operators, and generic ranking rules. Monitor size/resolution/refresh/panel/use-case behavior is likewise representable. The only allowed residual is a small compatibility projection for released Laptop-shaped fields or a proven historical TECH heuristic, with a removal condition. Retaining complete `LaptopPolicy`/`MonitorPolicy` implementations is rejected.

## Public schema decision

The public result gains additive generic comparison fields and keeps released Laptop-compatible fields during migration. OpenAPI/generated types are regenerated only if the final additive envelope requires it. The frontend does not infer facts from text and does not replace unresolved categories with Laptop.

## Scope and safety check

- No Apply has run.
- No production, existing tests, frontend source, catalog data, or main spec has been modified.
- No Sync or Archive has run.
- No commit, push, tag, release, or deployment has run.
- `v3.1.0` exists and is not moved.
- Bulk category/product expansion is out of scope.
- Commerce/HITL and Agent write boundaries remain explicit compatibility constraints.

## Readiness conclusion

**Ready For Apply: Yes, planning-only.** The proof is implementable without core category edits, the generic semantics are fully specified, the remaining decisions are bounded implementation details, and the task list covers registry, typed definitions, parsing, constraints, normalization/ranking, projection, frontend, Laptop/Monitor migration, validator, architecture proof, regressions, and OpenAPI. This is not a claim that implementation or runtime tests have already passed; those belong to Apply.
