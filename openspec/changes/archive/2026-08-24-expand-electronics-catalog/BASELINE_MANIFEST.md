# expand-electronics-catalog Apply Baseline

Baseline directory: `C:\Users\17937\Desktop\4\expand-electronics-catalog-baseline`

The baseline was created before the first data/seed/test edit. It contains preimages for recommendation core, Registry core, graph/nodes, frontend recommendation renderer, validator, seed script, and existing Laptop/Monitor data. New definitions/catalog/docs/tests have no preimage.

The only intended non-data implementation delta is the seed discovery manifest behavior in `scripts/seed_shopmind_catalog.py`, which changes the default input from a closed two-file tuple to sorted `data/catalog/*_catalog.json` discovery. No recommendation core or renderer file is authorized to change.
