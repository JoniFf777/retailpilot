# Shopping task scenario → test map

Version: `shopmind.task-test-map.v1`

Status: offline/contract mapping; rows marked PostgreSQL or browser require
the corresponding environment gate before they can be called passed.

| Spec scenario group | Case IDs | Current test/evidence | Gate |
| --- | --- | --- | --- |
| Orchestration: legal dependent plan; malicious plan | B01, B04, B05 | `tests/shopping_tasks/test_contracts.py` | offline |
| Orchestration: out-of-order/authority/reviewer/no-progress | B02, B05, B06 | `app/shopping_tasks/verifier.py`, `test_contracts.py` | offline, partial |
| Orchestration: agent proposal/provider unavailable | — | no real adapter yet | open |
| Recovery: owner scope, replay, version conflict | R01, R02 | `test_repository.py`, `test_idempotency.py` | SQLite contract |
| Recovery: two workers/late lease | R01 | `tests/integration/test_shopping_tasks_postgres.py` | PostgreSQL `1/1` |
| Recovery: cancel/expiry/delete fencing | R02 | `tests/governance/test_owner_data.py`, repository expiry code | PostgreSQL action gate open |
| Workspace: valid bundle/bounded search | B01, B02, B06, B07, B08, B09 | `test_contracts.py`, `test_catalog_fixture.py` | offline |
| Workspace: locked/stale/incompatible/unknown | B03, B04, B05, B10 | `test_contracts.py`, compatibility module | offline |
| Workspace: diagnosis feedback/round limit/safe scope | D01–D06 | `app/shopping_tasks/diagnosis.py`, `test_contracts.py` | offline, API continuation open |
| Workspace: owner order/policy missing/conditional | A01–A05 | `app/shopping_tasks/after_sales.py`, `test_contracts.py` | offline, live order gate open |
| Actions: preview/stale/price/inventory/replay | B01, A06, R02 | task action route and idempotency tests | PostgreSQL action gate open |
| Evidence: bounded query/citation/scope | B04, D05, A03 | `tests/shopping_tasks/test_evidence.py`, `evidence.py` | offline; real retrieval open |
| Evidence: publication/revocation/reranker failure | — | existing AI platform evidence tests | new task integration open |
| Acceptance: old public contracts | — | `234 passed` AI/recommendation/API regression; frontend `35/35` mocked E2E | controlled shell |
| Acceptance: task browser/API/worker/database | B01, D01, A01 | no task-specific live browser spec yet | open |
| Acceptance: real model trajectories | — | deliberately not executed | requires explicit model authorization |

This map is intentionally honest about partial rows. A test file or case ID is
not itself a pass result.
