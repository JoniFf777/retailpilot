# 库存、订单和支付设计（后续 Phase 3–6）

本设计不在 Phase 0 或 Phase 1 实现。它明确禁止复用 `app/db/models.py` 中关联 `Customer` 的旧
`Order`/`OrderItem`。

相关现有入口为 `app/repositories/cart.py::confirm_add_to_cart`、`get_cart_items` 与
`app/api/routes/chat_confirm.py::confirm_chat`；后续服务必须在这些边界之外新增，不将订单语义塞入
现有 chat confirmation adapter。

## Phase 2 Preflight 补充：结构化 HITL 与 SKU Cart 边界

本文件中的 Cart/Phase 3 方向必须与 `docs/phase2_preflight_report.md` 一致。Phase 2 Preflight 选择新增 `shopmind_cart_items`（迁移方案 B），以 `(user_id, sku_id)` 唯一并在 1..20 范围内原子合并；旧 `cart_items(product_id)` 仅保留兼容路径，不做未经审计的 Product→SKU 回填。加购确认必须从 RecommendationResult 的显式 `sku_id` 创建版本化 PendingAction，确认时锁定 action 并重新读取 Catalog SKU/Product/Inventory；加购不预留库存，价格变化返回当前 Money 与 `price_changed`，库存不足保持 pending 供用户调整，商品不可售返回 rejected。

本补充仍是设计审计，不代表 Phase 2A/2B 已实现；Order、Inventory reservation、Payment、Outbox 仍属于后续阶段。

## Cart

现有 `CartItem` 使用 `user_id`、`product_id`，`confirm_add_to_cart` 会插入新行且没有库存检查。
Phase 3 应迁移到 owner + sku_id：先审计/合并重复数据，再添加唯一约束 `(owner_id, sku_id)`。自然语言
加购继续经过 pending action；页面 `GET/PATCH/DELETE /api/cart` 直接调用 Cart Service。加购与 preview
不预留库存。成功创建订单并完成库存预留后才清理对应 cart 项；创建失败、支付失败、取消或过期不清理，
避免用户丢失购物车。收货地址与配送方式在 Phase 4 保存为订单快照；不实现物流或复杂运费。

## Inventory 和 Order

`shopmind_inventory` 是 PostgreSQL 事实来源。创建订单在一个事务内重新读取 cart/SKU/价格，插入
`shopmind_orders`、`shopmind_order_items` 快照，并用原子条件更新预留每个 SKU：

```text
on_hand_quantity - reserved_quantity >= requested_quantity
```

任意行更新失败则全事务回滚。订单状态为 `pending_payment/paid/cancelled/expired/completed`，与 payment
状态分开；未支付订单有 `expires_at`。支付成功将预留转成正式消耗，取消/过期只释放预留，所有迁移都用
条件更新以保证重复调用和并发安全。多 SKU 在锁定/条件更新前按稳定 `sku_id` 升序排序，避免相反顺序的
死锁。支付失败不会释放预留；预留只持续到订单原始 `expires_at`，失败重试不得静默延长，除非未来有显式
重新报价/延长订单用例。

## Payment

新增 `shopmind_payments`，一个订单可有多次尝试，字段包括 owner、金额、currency、provider、status、
idempotency key、provider reference、failure reason、timestamps。只实现 `MockPaymentGateway`；金额从订单
读取。支付失败保持订单 pending_payment，可再次支付；真实支付不在范围内。支付 attempt API 为
`POST /api/orders/{order_id}/payments` 和 `GET /api/orders/{order_id}/payments`。

## API 和验收

后续增加 checkout preview、orders list/detail/cancel 和 payment attempt API。所有请求通过现有
`IdentityBoundary` 绑定 owner；`Idempotency-Key` 记录于 ShopMind 订单域，不复用只允许 chat/confirm 的
运行时幂等表。必须有最后一件并发购买、多 SKU 回滚、支付/取消并发和 owner 隔离 PostgreSQL 测试。
