# Phase 2 Preflight：结构化 HITL 加购与 SKU Cart 迁移审计

日期：2026-08-05
范围：只读审计现有实现与设计；本轮没有修改 Graph、Runtime、推荐算法、Cart、Order、Payment、Redis、RocketMQ、数据库迁移、API 或前端业务代码。

## 1. 结论

当前实现仍是“旧 Product + `product_id` + 分离工具事务”的兼容路径，尚未达到结构化 SKU 加购的安全边界。Phase 2 不应直接把旧 `confirm_add_to_cart` 改成 SKU 写入；必须先建立结构化 PendingAction、Catalog 重查和新的 SKU Cart 服务。

推荐迁移选择 **B：新增 ShopMind SKU Cart 表并行切换**。旧 `cart_items` 保留为兼容读写路径，直到新路径完成验收；不在本轮回填或猜测旧 Product 到 SKU 的映射。

## 2. 真实代码审计

### 2.1 数据模型与迁移

- `app/db/models.py::CartItem` 只有 `user_id`、旧 `product_id`、`quantity`、时间戳；只有 `quantity > 0`，没有 `sku_id`、唯一键、数量上限、版本或金额快照。
- `app/db/models.py::PendingAction` 有 `payload_json`、`metadata_json`、`risk_class`、`preview_text`、`status`、`expires_at`，没有 schema version、source run/recommendation、confirmation result、confirmed cart id 或 `confirmed_at`。
- `alembic/versions/0001_create_structured_business_tables.py` 创建旧 Product FK 的 `cart_items`；`0006_action_registry_fields.py` 扩展 PendingAction 状态/元数据。没有 SKU Cart 表。
- `0008_shopmind_catalog_identity.py` 与 `0009_shopmind_skus_inventory.py` 创建 Catalog 表。Catalog 的 `product_code`、`sku_code` 稳定且唯一，`legacy_product_id` 是 nullable unique 的无 FK 兼容桥；删除旧 Product 不会被 Catalog FK 阻断。
- `app/catalog/models.py` 的 `CatalogSku.money_amount` 是 `Decimal/Numeric(12,2)`；库存有效量是 `on_hand_quantity - reserved_quantity`，本阶段加购不预留库存。

### 2.2 Catalog 与旧身份

`app/repositories/catalog.py` 已提供 `get_catalog_sku`、`get_catalog_product`、`resolve_legacy_product`、`reconcile_legacy_mappings` 和 `list_alternative_skus`。推荐候选来自 active Product/SKU 且有效库存大于零的 Catalog 查询；但 `app/repositories/cart.py::prepare_add_to_cart` 仍只查旧 `Product`，不能证明商品属于当前用户同一线程/运行持久化的 RecommendationResult。

### 2.3 PendingAction、确认和事务

`app/repositories/cart.py::confirm_add_to_cart` 确实对 PendingAction 使用 `SELECT ... FOR UPDATE`，校验 owner、部分 thread、pending 状态和过期时间，并且只允许严格整数 `quantity` 编辑。可是它随后只按旧 `product_id` 查询 `Product`，不重查 Catalog SKU/Product 的 sale status、当前价格或库存；每次确认都 `INSERT cart_items`，没有 SKU 唯一 upsert。

`tools/cart.py` 为准备、确认、取消分别打开 Session 并自行 commit/rollback。Runtime Harness 随后在另一个 Session 持久化 `AgentRun`/幂等记录（`app/runtime/harness.py::_resolve_idempotency`、`_persist_start`、`_persist_finish`）。因此当前 Cart/PendingAction 提交与 Run 结果不是同一事务；工具已提交后 Harness 失败可能产生业务写入与 Run 状态不一致。

`IdempotencyRecord`（`app/db/models.py`）按 `(user_id, operation, idempotency_key)` 唯一并能重放已持久化 Run，但 PendingAction 没有稳定 confirmation result。相同 key 的 Runtime 重放可工作；不同 key 并发同一 action 只能依赖行锁和终态检查，第二次得到冲突而不是同一成功结果，且旧 Cart 仍可被不同 action 重复插入。

### 2.4 API 与前端

- `app/api/routes/chat_confirm.py::confirm_chat` 只返回旧 `ChatResponse`（answer/status/tool calls/pending id），没有 typed `PendingActionView`、`cart_item`、`price_changed`、`current_money` 或 `idempotent_replay`。
- `app/dependencies/agent.py::confirm_pending_action` 通过 Action Registry 校验编辑字段，再调用 `tools.cart`；没有 Catalog/SKU 复核或单事务服务。
- `app/runtime/actions.py::AddToCartActionEdits` 只限制 `quantity > 0`，没有与 Cart 一致的最大值。
- `frontend/src/features/actions/ActionDrawer.tsx` 只显示字符串 preview，数量输入在客户端做正整数检查，提交旧 `/api/chat/confirm`；没有 SKU、价格变更、库存不足和结构化状态视图。当前前端没有 Cart API。

## 3. 必须修正的正确性与并发问题

1. 任意旧 `product_id` 可创建 action，绕过 RecommendationResult 的 owner/thread/run 归属。
2. 确认信任 payload 中的旧产品 ID/数量，不读取 Catalog 的 active 状态、价格和库存。
3. 旧 Cart 允许同一用户同一商品重复行；无原子合并、数量上限或 SKU 身份。
4. payload/preview 混合执行输入和自然语言快照，无法进行版本化审计；不得从自然语言解析 SKU。
5. 工具事务与 Harness 事务分离，失败恢复和 HTTP/SSE 状态可能不一致。
6. thread 校验在 action thread 非空而请求 thread 为空时是宽松的；新推荐 action 必须要求精确 thread/owner。
7. 当前金额存在 Decimal→float 的 `_money_to_float` 转换，不可作为新 Cart 金额事实。

已有保护：确认/取消有 row lock、owner 检查、pending/expiry 检查，编辑 schema 禁止额外字段；这些应保留并移入新的单事务服务。

## 4. Phase 2 目标链路与状态机

```text
RecommendationResult (explicit sku_id)
  -> create structured PendingAction
  -> PendingActionView
  -> confirm/edit quantity
  -> one transaction: lock action, owner/thread/status/expiry check,
     re-query SKU/Product/Inventory, validate quantity, upsert SKU Cart,
     persist confirmation result, mark confirmed
```

PendingAction 状态：`pending -> confirmed | cancelled | expired | rejected`；现有 `failed` 作为兼容终态保留。终态不可再次执行。价格变化不阻断确认：返回 `price_changed=true` 与当前 Money，Cart 不写入旧价格。库存不足保持 pending 并要求用户减少数量/重试；SKU/Product inactive 或删除返回稳定 `rejected`，不创建 Cart 行。加购绝不预留库存。

## 5. PendingActionView 与 payload 契约

公开 View 建议字段：

```text
pending_action_id, action_type, risk_class, status, expires_at,
editable_fields=["quantity"], preview, confirm_label, cancel_label
```

`preview` 为结构化 `AddToCartPreview`：`sku_id`、`sku_code`、Catalog `product_id`/`product_code`、名称、严格整数 `quantity`（1..20）、`Money(amount: string, currency: /^[A-Z]{3}$/)`、sale/inventory 快照。公开响应不暴露原始 `payload_json` 或可写的 `user_id`。

内部 payload 使用版本字符串 `shopmind.pending_action.add_to_cart.v1`：

```json
{
  "schema_version": "shopmind.pending_action.add_to_cart.v1",
  "sku_id": "<uuid>", "quantity": 2,
  "source_run_id": "<run-id>",
  "source_recommendation_schema_version": "shopmind.recommendation.v1",
  "source_product_id": "<catalog-product-uuid>",
  "price_snapshot": {"amount": "5999.00", "currency": "CNY"},
  "sku_code_snapshot": "LAP-001-16G"
}
```

`sku_id`/`quantity` 是执行输入；source、价格、名称和 code 是审计快照。确认时只信任 sku_id/编辑后的 quantity，并重新读取 Catalog；快照不决定价格、sale status、inventory，也不能把 Top K 外商品带入执行。

## 6. Cart 迁移决策（B）

新增 `shopmind_cart_items`，至少包含 `id`、`user_id`、`sku_id` FK、`quantity`、`created_at`、`updated_at`，`UNIQUE(user_id, sku_id)`、`quantity > 0`、`quantity <= 20`。按 `sku_id` 排序锁定相关 Cart 行，使用 PostgreSQL 原子 upsert/row lock 合并数量；不添加库存 reservation 字段，不读取旧 Product 价格作为事实。

保留旧 `cart_items(product_id)` 和旧工具作为兼容适配器，不自动猜测或批量回填 Product→SKU。只有在独立数据库完成 mapping 审计、人工确认默认 SKU 规则后，才制定可回滚的迁移/并行读取计划。

## 7. API 草案（本轮未实现）

```text
POST /api/pending-actions/add-to-cart
GET  /api/pending-actions/{pending_action_id}
POST /api/pending-actions/{pending_action_id}/confirm
POST /api/pending-actions/{pending_action_id}/cancel
GET  /api/cart
```

创建请求只接收同一 owner/thread/run 的 `sku_id`、quantity 和 source run；身份由服务器绑定，不接收客户端 user_id、最终价格、库存或旧 product_id。confirm 请求只允许 `quantity` 与 `Idempotency-Key`。响应统一包含 `pending_action`、可选 `cart_item`、`price_changed`、`current_money`、`idempotent_replay` 和结构化错误。

旧 `/api/chat/confirm` 继续作为兼容 adapter，不应成为新 RecommendationResult 的唯一入口；JSON 与 SSE 使用同一 projection。

## 8. Phase 2A / 2B 文件级计划（仅计划）

### Phase 2A：Backend foundation

- `app/db/models.py`：PendingAction 版本/结果字段与 `ShopMindCartItem` ORM。
- 新 Alembic revision（预计 `0010_shopmind_cart_items`）：表、FK、唯一键、数量约束；不改旧表语义。
- `app/schemas/actions.py`、`app/schemas/cart.py`：PendingActionView、preview、Money、transition/error contracts。
- `app/repositories/pending_actions.py` 或拆分现有 `app/repositories/cart.py`：推荐归属校验、Catalog re-query、状态机、同事务 upsert。
- `app/repositories/cart.py`：保留 legacy adapter，禁止新路径继续写旧 Product Cart。
- `app/api/routes/pending_actions.py`、`app/api/routes/cart.py` 及 router 注册：新端点和 identity/idempotency 绑定。
- `app/dependencies/agent.py`、`app/runtime/actions.py`：仅接入 typed service，不让工具自行 commit。
- `tests/pending_actions/`、`tests/cart/`、`tests/api/`、`tests/integration/`：迁移/约束/事务/并发/重放/owner-thread/catalog 状态矩阵。

### Phase 2B：Frontend/cutover

- `frontend/src/api/contracts.ts`、`frontend/src/api/client.ts`：生成/手写兼容的 typed pending/cart API。
- `frontend/src/features/actions/actionTypes.ts`、`ActionDrawer.tsx`：只消费 PendingActionView，只编辑 quantity，展示 price/inventory/rejected/expiry/idempotent replay。
- `frontend/src/features/recommendation/RecommendationCard.tsx`、`ChatPage.tsx`：只能从 RecommendationResult 的 explicit sku_id 创建 action；不得解析 answer/summary 文本。
- 新 `frontend/src/features/cart/`：SKU cart 列表与数量展示。
- `frontend/src/**/__tests__`、`frontend/tests/e2e/`：JSON/SSE、stale result、owner/expiry、price change、库存不足、同 SPU 多 SKU。

## 9. 测试矩阵

| 层 | 必测事实 |
|---|---|
| Schema/migration | 新表、FK、`UNIQUE(user_id,sku_id)`、1..20、旧表不变、upgrade/downgrade |
| PendingAction | 必须来自已持久化同 owner/thread/run 的 recommendation；过期、终态、错误 action、编辑白名单、schema version |
| Confirm transaction | `FOR UPDATE`、Catalog active/product active、当前价格、可用库存、price_changed、库存不足保持 pending、inactive/deleted rejected、失败全回滚 |
| Concurrency/idempotency | 同 action 同 key、同 action 不同 key、同 SKU 不同 action、不同 SKU 锁顺序、重复 upsert、结果重放 |
| Cart API | owner isolation、SKU 返回、quantity 上限、无库存预留、无旧价格事实、GET 一致 |
| Compatibility | legacy chat/confirm adapter、旧 Product 映射不可猜测、无自然语言 SKU 解析 |
| Frontend | typed view、只能编辑 quantity、JSON/SSE 相同投影、stale-result、price/inventory/expiry/rejected、最多/明确 SKU |

## 10. 未解决问题与进入实施前门槛

1. 当前持久化 `AgentRun.result_json` 尚未提供“RecommendationResult → owner/thread/run”专用查询服务；Phase 2A 必须先定义权威 lookup。
2. 需要在隔离 PostgreSQL 报告 `legacy_product_id` resolved/dangling 实际数量；不能以 seed 假设替代映射审计。
3. 新 Catalog migrations 0008/0009 的部署状态需在目标环境确认，不能假定生产已升级。
4. 数量上限固定为 20。价格变更采用不阻断确认的 UI 文案；inactive/deleted 采用 rejected；库存不足采用保持 pending 的策略，均需 API 验收锁定。
5. 需要决定 action-level idempotency result 的字段（建议 `confirmation_result_json`、`confirmed_cart_item_id`、`confirmed_at`）及 retention；不能只依赖 Runtime `IdempotencyRecord`。
6. 需要明确 identity header 与 `user_id` 的最终绑定方式；新端点不应信任 body 中 user_id。

## 11. 本轮验收与状态

- 只读审计：完成；上述结论均对应当前代码路径。
- 设计文档：本报告及 `docs/implementation_plan.md`、`docs/inventory_order_payment_design.md` 已同步 Phase 2 预检决策。
- 未实现数据库、API、Graph、Runtime、Cart、前端业务或迁移。
- 未 stage、未 commit、未触发远程 workflow。
- Phase 2 状态：**Preflight complete; implementation not started**。
