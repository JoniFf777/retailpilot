# Phase 2B-Frontend / HITL Cutover acceptance report

Status: **Phase 2B-Frontend / HITL Cutover accepted**.

Scope is limited to generated OpenAPI frontend contracts, structured PendingAction selection/Drawer, legacy chat confirmation compatibility, JSON/SSE stale-result handling, read-only SKU Cart, Vitest and Playwright. No Phase 3 work is included.

## Contract and client

- `scripts/export_openapi.py --output frontend/openapi.json` is the source export.
- `cd frontend; npm run generate:api` regenerates `src/api/openapi.generated.ts`.
- Dedicated pending-action endpoints disable `Idempotency-Key`; chat, chat-confirm and chat-stream retain it.
- Recommendation selection uses only the assistant message `recommendation_context` and sends SKU identity, thread/run identity and quantity.

## Acceptance commands

Final observed results:

- Vitest: **13 files / 41 tests passed**.
- Playwright: **8/8 passed**.
- `npm run lint`, `npm run typecheck`, `npm run typecheck:e2e`, `npm run build` and `npm run check:budget` passed.

```text
frontend: npm run lint
frontend: npm run typecheck
frontend: npm run test
frontend: npm run typecheck:e2e
frontend: npm run build
frontend: npm run check:budget
frontend: npm run e2e:list
frontend: npm run e2e
backend: conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\api\test_openapi_schema.py tests\api\test_phase2a_pending_actions.py tests\cart\test_phase2a_service.py -q -p no:cacheprovider
```

The focused backend command returned **12 passed**; the complete affected API regression `conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\api -q -p no:cacheprovider` returned **74 passed**. Documentation tests returned **10 passed**. Playwright additionally ran `npm run e2e:list` and listed 8 scenarios before `npm run e2e` returned 8/8. The first sandboxed Vitest/build attempt hit Windows `spawn EPERM` while starting esbuild; rerunning those commands with the approved external runner succeeded. This is an environment collection issue, not an application failure.

## Boundary

Phase 2B does not modify recommendation ranking, Graph, Runtime, Cart management, Order, Payment, Redis, RocketMQ or Outbox. No files are staged or committed by this acceptance activity.
