# 测试计划

## Phase 1A

- Catalog：根/子类目 code unique（含 PostgreSQL NULLS NOT DISTINCT）、SKU code unique、SPU/SKU attribute
  scope、非法类型/unit/options、money/currency checks、inventory 非负/`reserved <= on_hand`、seed 幂等且不破坏旧 products、
  legacy mapping validation/dangling report/reconciliation、默认 SKU 和同 SPU 多 SKU；隔离 schema 验证
  `0008→0007→0008` 与 `0009→0008→0009`。
- Recommendation：硬约束绝不进入 Top K、no_match/clarification_required 结构化 outcome、缺失规格、稳定
  tie-break、SKU 层排序/SPU 去重/alternative SKU、中文 CNY 归一化、币种不直接比较、Money 精确字符串序列化、evidence 白名单。Phase 1A 只测
  pure evidence sanitizer/merge；RAG/catalog 冲突优先级的真实集成测试放在 1B。
- 数据库：catalog migration upgrade/downgrade/upgrade 在隔离 PostgreSQL；幂等 seed。

## Phase 1B

- Graph：Catalog + Preference → deterministic node → Top K product/policy RAG → evidence validation → Decision
  的 state 输入/输出；Decision 文本、card 和 evidence 只能引用同一 Top K SKU；写意图和 single Agent
  optional recommendation 兼容。
- Runtime/API/SSE：HTTP/SSE recommendation 等价、result_json 恢复、idempotency replay 等价、response
  fingerprint 包含 output_data recommendation、旧 ChatResponse/OpenAPI 兼容。每条 SSE 恰有一个合法终态：
  `run.result`、`run.cancelled` 或 `run.failed`；取消/失败不要求正常 recommendation。
- 前端：generated type、Money、specifications 动态显示、completed/cancelled/failed，且不解析文本。

现有参照测试是 `tests/api/test_chat_stream.py`、`tests/api/test_chat_confirm.py`、
`tests/runtime/test_tool_gateway.py`、`tests/repositories/test_cart_repository.py` 和
`frontend/src/api/sse.test.ts`；新测试应沿用这些公开边界，而非对内部 debug payload 断言。

## 后续交易测试

Cart 的 owner/SKU upsert、删除/清空幂等、不可售；checkout 的服务端价格和库存差异；多 SKU 订单事务回滚；
最后一件并发购买；预留/释放/消耗幂等；order/payment 状态机；Outbox lease/retry；Inbox duplicate/乱序；
支付成功与取消/过期并发。真实 PostgreSQL 是这些测试的必要层，Redis/RocketMQ 只作为附加集成层。

## 评估和 E2E

先建立 30 条黄金集（预算、硬约束、无库存、澄清、RAG 冲突、HITL），再扩大至 50–100。对比 Single、
Multi、Multi+deterministic ranking，固定/记录模型、temperature、商品/RAG 数据，多次执行并报告质量、
P50/P95、token、成本和写入零绕过。Playwright 覆盖 90 秒链路及失败/取消/重复提交。

## 环境修复门槛

在报告真实全绿前，修复 pytest Temp ACL 和 Playwright `spawn EPERM`，然后重跑：
`pytest tests -p no:cacheprovider`、`npm run e2e`、PostgreSQL integration。不得以历史 668 passed 或本次
聚焦测试替代当前全量结果。

## Phase 4A Regression Baseline

Phase 4A is accepted and closed. The regression suite covers real FastAPI/ASGI owner and
HTTP-response contracts, private-schema PostgreSQL migration introspection/round-trip, and PostgreSQL
reservation concurrency. Phase 4A does not test or implement frontend, payment, automatic expiration,
address/shipping/tax, Redis, RocketMQ, or Outbox/Inbox.

Latest records are: HTTP API/OpenAPI `4 passed`; Phase 2/3 plus Phase 4 focused regression `34 passed`;
Phase 3 PostgreSQL Cart `6 passed`; Phase 4 private-schema PostgreSQL matrix `11 passed`; combined
PostgreSQL suites `17 passed`; and `git diff --check` exit code `0`. The Phase 4 matrix covers migration
round-trip, last-stock/partial rollback, same-key replay and conflict, expired-token replay, truly concurrent
same-key different-request, multi-SKU A+B/B+A, mixed currency, corrupt reservation Cancel rollback, Create
replay vs Cancel, and Create vs Phase 2 PendingAction confirm.

## Phase 5A Mock Payment Backend

Acceptance coverage uses real FastAPI/ASGI requests for the Payment Attempt
endpoints and private-schema PostgreSQL transactions for persistence and
concurrency. The matrix covers migration round-trip and constraints, successful
payment, declined payment, same-key replay and conflict, unknown-provider
reconciliation, true concurrent same-key requests, two concurrent payments for
one Order, payment versus Cancel, paid-order replay/cancellation, multi-SKU
partial finalization rollback, reservation corruption, owner-safe missing Order
handling, exact Inventory reservation/on-hand/version changes, and public
OpenAPI/error response consistency.

Phase 5A Mock Payment Backend is accepted and closed. The server owns provider
scenarios; the request cannot supply `amount`, `currency`, `user_id`,
`scenario`, or force-success/decline/timeout flags. Phase 5B frontend, real
providers, webhooks, refunds/chargebacks, and automatic reconciliation remain
outside the Phase 5A test boundary. Phase 6A has its own Outbox/RocketMQ gate
below.

## Phase 6A Transactional Outbox + RocketMQ

Phase 6A acceptance must use real PostgreSQL in a random private schema with a
private `alembic_version`; the shared `public` schema must remain unchanged.
The migration matrix is `0013 -> 0014 -> 0013 -> 0014` and introspects the
complete Outbox table, nullable lease/published fields, aggregate sequence
unique constraint, status/lease/published CHECK constraints, and required
claim/aggregate indexes.

The PostgreSQL transaction matrix covers:

- Create event commit and rollback, Cancel commit/replay, and Payment success
  same-transaction enqueue;
- finalization rollback, replay without a second event, immutable envelope,
  and PII-safe payload;
- exact Order-version aggregate sequences and same-aggregate ordering;
- different-aggregate parallelism and two real workers competing for one row;
- expired lease reclaim, stale owner CAS, publish failure retry, max-attempt
  dead-letter, and operator dead-letter redrive;
- publish-success/mark-published crash recovery with the same event ID and
  at-least-once delivery semantics.

The transport smoke uses a disposable RocketMQ 5.3.2 NameServer/Broker/Proxy,
the pinned Apache Python SDK, endpoint `127.0.0.1:8081`, an ordered FIFO topic,
and the real `RocketMQPublisher`. It verifies broker message IDs, event-type
tag, Order message group, event-ID key, immutable envelope, and sequence order;
all disposable containers and networks are removed after the run.

Current Phase 6A record: HTTP/API/OpenAPI plus Phase 4/5 focused and Phase 6
unit `15 passed`; Phase 6A PostgreSQL `12 passed`; Phase 3/4/5 PostgreSQL
regressions `6/11/10 passed`; combined PostgreSQL suites `39 passed`.
The stable non-PostgreSQL backend regression scope passed `587 passed, 2
skipped` after excluding the existing artifact/operations temp-ACL group and
cleanup temp-ACL case. A broader run reached `731 passed, 2 skipped` before
24 setup/teardown `PermissionError` results from that same Windows temp-ACL
boundary.
Consumer, Inbox, webhook, automatic reconciliation, Redis, and RocketMQ
consumer orchestration are not part of Phase 6A.
