# Phase 2A Backend Acceptance Report

日期：2026-08-07

状态：**Phase 2A Backend Acceptance Gate 通过；Phase 2B 未开始。**

## 范围与补丁

- PendingAction GET、confirm、cancel 在 owner/thread 校验后锁定同一行；终态只写入一次。
- `result_json` 使用 `shopmind.pending_action.resolution.v1`，保存公开 PendingAction 快照、Cart 快照、金额、数量、错误和时间；replay 不重新查询 Catalog、Inventory 或 Cart。
- 创建时保存 product/SKU、价格和 availability 快照；预览不依赖 live Catalog。legacy 预览保留旧字段，但没有可信币种或实时库存时返回 null。
- `initial_quantity` 不变，`quantity` 表示当前请求；响应明确 `requested_quantity` 与 `cart_quantity`。
- 错误使用 `ActionErrorResponse` 与 Literal code；confirm 专用端点不再声明未使用的 `Idempotency-Key`。
- Cart projection 返回 `product_sale_status`、`sku_sale_status`、`effective_sale_status`，库存缺失使用 `inventory_missing`；Repository 不 commit。

没有修改推荐算法、Graph、RAG、Runtime Harness 主链、前端业务组件、Order、Checkout、Payment、Redis、RocketMQ 或 Outbox。`frontend/openapi.json` 仅作为生成的契约工件更新。

## PostgreSQL 环境与 migration

- PostgreSQL：16.13（pgvector/pg16 容器）。
- 隔离数据库：`retailpilot_phase2a_20260807`；共享 `retailpilot_v2_smoke` 未修改。
- 脱敏 DSN：`postgresql+psycopg://postgres:***@127.0.0.1:5432/retailpilot_phase2a_20260807?connect_timeout=5`。
- 创建方式：`docker exec postgres psql -U postgres -d postgres -c "CREATE DATABASE retailpilot_phase2a_20260807"`；本次保留该隔离库用于复核。清理方式：确认没有连接后执行 `docker exec postgres psql -U postgres -d postgres -c "DROP DATABASE retailpilot_phase2a_20260807"`，不会触碰共享 smoke 库。
- 实际序列及结果：

```text
alembic upgrade 0009       OK
alembic upgrade 0010       OK
alembic downgrade 0009     OK
alembic upgrade 0010       OK
alembic upgrade 0011       OK
alembic downgrade 0010     OK
alembic upgrade 0011       OK
alembic upgrade head       OK
alembic current             0011_shopmind_cart (head)
```

数据库元数据确认五张 Catalog 表、`pending_actions` 新字段和 `shopmind_cart_items` 均存在；downgrade 后 0010 字段和 cart 表被删除，再次 upgrade 无残留冲突。`shopmind_categories` 实际约束为 `UNIQUE NULLS NOT DISTINCT (parent_id, code)`。旧 `products`、`cart_items` 和其他旧表仍存在；以 `products` 为被引用表的 ShopMind FK 数为 0。

## 真实约束验收

真实 PostgreSQL 事务测试通过：根类目重复 code、同父子类目重复 code、product_code、sku_code、legacy_product_id 重复均被拒绝；不同父类目允许相同子类目 code；多个 NULL legacy_product_id 合法。Money 非正数、低写 currency、库存负数、reserved 超过 on-hand 均被拒绝；零库存合法。Catalog SKU 到旧 Product 没有数据库 FK。

## 并发与事务验收

命令：

```text
$env:RUN_POSTGRES_INTEGRATION='1';
$env:TEST_DATABASE_URL='<isolated DSN>';
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\integration\test_phase2a_postgres_acceptance.py -q -p no:cacheprovider
```

结果：**5 passed**。覆盖同 action 同 hash replay、同 action 不同数量 conflict、两个 action 争用同一 SKU、confirm/cancel 竞态、GET expire/confirm 竞态，以及 Cart flush 后上层 rollback。竞态中仅一个终态成功，另一方得到稳定 conflict/expired/quantity-limit 结果。

## 回归命令与结果

```text
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\cart\test_phase2a_service.py tests\api\test_phase2a_pending_actions.py tests\api\test_openapi_schema.py tests\repositories\test_cart_repository.py -q -p no:cacheprovider
24 passed

conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\catalog tests\recommendation tests\db\test_models.py tests\docs -q -p no:cacheprovider
41 passed, 2 skipped

conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\repositories -q -p no:cacheprovider
40 passed

conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\api -q -p no:cacheprovider
73 passed

conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\export_openapi.py --output frontend\openapi.json
48 schemas
```

`git diff --check`：exit code **0**。

## 未解决问题与边界

本轮未运行完整仓库 pytest（历史上受 Temp ACL/运行时间影响）；直接受影响目录、真实 PostgreSQL migration、约束和并发验收均通过。Seed/legacy mapping 与 Phase 1A 数据验收沿用已通过的独立 gate，不在本轮重复改动。Phase 2B、前端业务切换和后续 Cart/Order/Payment 工作均未开始。
