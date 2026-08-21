## Why

ShopMind 当前存在两条仍可到达正式购物流程的加购链路。结构化推荐通过 `app/services/pending_actions.py` 写入 SKU-based `shopmind_cart_items`，但旧 Chat Write Handoff 仍经 `tools/cart.py` 和 `app/repositories/cart.py` 创建 legacy PendingAction，并在确认时写入 `cart_items`。正式 Cart API、Checkout Preview 和订单创建只读取 `shopmind_cart_items`，所以旧 Chat 可能返回“已加入购物车”，而用户在正式购物车和 Checkout 中看不到该商品。

这不是 README 层面的假设：当前调用关系和测试都保留了两套事实源。现在需要在继续支持旧 Chat 意图的同时，切断 legacy Cart 对 ShopMind 正式 commerce path 的影响，避免确认成功与用户可见 Cart 不一致。

## What Changes

- 将 `shopmind_cart_items` 明确定义为正式 ShopMind commerce flow 的唯一 canonical Cart truth。
- 为 legacy Chat add-to-cart intent 增加兼容适配：将 legacy product identifier 解析为 CatalogProduct/CatalogSku，再创建与结构化流程兼容的 canonical PendingAction。
- 对未标注 kind 的 identifier 同时检查 `sku_code`、`legacy_product_id`、`product_code`；发生跨 namespace collision 时只在所有命中收敛到同一个 concrete SKU 的情况下继续，否则返回 typed `catalog_identifier_ambiguous`，不按优先级静默选择。
- 让 legacy Chat 的 prepare/confirm 最终复用现有 SKU PendingAction 与 ShopMind Cart mutation boundary，保留 owner、thread、expiry、真实 expected version、quantity、sale-status、inventory 和 replay 语义。
- 为通用 `/api/chat/confirm` 增加 additive `expected_version` 字段；canonical add-to-cart 在业务上必须携带客户端实际持有的 `PendingActionView.version`，不得读取最新版本冒充客户端 token。
- 对部署前遗留的非 canonical legacy add-to-cart PendingAction，confirm 只返回 typed `unsupported_action_schema`/等价 safe failure；不得恢复 legacy writer、静默迁移、猜 SKU 或双写。
- 在 resolver、adapter、Write Handoff 和 presentation 之间使用 machine-readable typed outcome；业务控制流不得解析中文展示文本。多 SKU clarification 不得仅因缺少 `pending_action_id` 被机械标为普通 execution failure。
- 停止正式加购路径调用 legacy `app.repositories.cart.confirm_add_to_cart()`；旧工具名和旧表保留为 compatibility/workshop path，但不得再作为 canonical write 或 fallback。
- 确保确认成功后的 canonical Cart 可立即被当前 Cart API 读取并进入 Checkout Preview，并让前端在 legacy/structured canonical confirmation 成功后刷新 Cart、失效 Checkout Preview。
- 增加 resolver、adapter、Chat→Confirm→Cart→Checkout 和失败/幂等/所有权回归验证；不运行 PostgreSQL integration，本 change 只设计其后续验证。

## Capabilities

### New Capabilities

- `commerce-cart`: Defines the long-term canonical ShopMind Cart boundary, legacy identifier normalization, confirmation semantics, and the prohibition on legacy fallback or dual write.

### Modified Capabilities

- None. The existing `backend-regression-stability` capability remains unchanged; this change must not reintroduce event-loop blocking, cross-thread Session sharing, or the established RAG failure semantics.

## Impact

Expected implementation impact is limited to the legacy add-to-cart adapter, collision-safe Catalog resolver, shared PendingAction/catalog resolution services, typed action/chat contracts, the legacy Chat confirmation integration, generated frontend API contract, the small frontend Cart/Checkout cache invalidation seam, and directly related tests. The existing `app/api/routes/cart.py`, Checkout read path, Order service, inventory reservation, payment, Outbox/MQ, authentication architecture, and database schemas are not redesigned by this proposal.

The legacy `products`, `cart_items`, old `Product`/`CartItem` ORM models, and historical non-canonical PendingAction rows are retained. No destructive migration, automatic bulk backfill, historical PendingAction migration, or dual write is proposed. Existing legacy rows may remain historical/stale data until a separately reviewed migration strategy exists; new supported confirmation writes must go only to the canonical SKU Cart.
