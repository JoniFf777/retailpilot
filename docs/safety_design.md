# ShopMind V1 安全设计

## 为什么加购属于敏感操作

加购虽然不是支付，但它已经改变了用户的购物状态：

- 会写入购物车；
- 可能影响后续推荐、结算和订单流程；
- 用户可能误触或被模型误解；
- 如果 Agent 被 Prompt Injection 诱导，可能执行用户没有明确确认的操作。

因此 V1 不允许 Agent 直接完成加购，而是采用待确认动作机制。

## pending_actions 表如何工作

`pending_actions` 表用于保存“待用户确认”的敏感动作。

字段包括：

- `id`：pending action ID；
- `user_id`：所属用户；
- `thread_id`：可选会话 ID；
- `action_type`：动作类型，例如 `add_to_cart`；
- `payload_json`：动作参数，例如 `product_id` 和 `quantity`；
- `status`：`pending`、`confirmed`、`cancelled`；
- `created_at` / `updated_at`：时间戳。

流程：

```text
prepare_add_to_cart
  → 写入 pending_actions(status="pending")
  → 返回 pending_action_id

/api/chat/confirm confirmed=true
  → confirm_add_to_cart
  → 写入 cart_items
  → pending_actions.status = "confirmed"

/api/chat/confirm confirmed=false
  → cancel_pending_action
  → pending_actions.status = "cancelled"
```

## prepare_add_to_cart 的职责

`prepare_add_to_cart` 只负责准备动作：

- 校验 `user_id`；
- 校验 `quantity > 0`；
- 校验商品是否存在；
- 写入 `pending_actions`；
- 返回 `pending_action_id` 和中文确认提示；
- 不写入 `cart_items`。

它可以暴露给 Agent，因为它不会直接改变购物车最终状态。

## confirm_add_to_cart 的职责

`confirm_add_to_cart` 负责真正执行加购：

- 根据 `pending_action_id` 查找 pending action；
- 校验 `user_id` 是否一致；
- 校验状态必须是 `pending`；
- 校验 `action_type` 必须是 `add_to_cart`；
- 读取 `payload_json`；
- 写入 `cart_items`；
- 将 pending action 改为 `confirmed`。

它不暴露给 Agent，只由 `/api/chat/confirm` 调用。

## 如何防止 Agent 直接执行敏感操作

V1 通过工具暴露边界防止 Agent 直接执行敏感操作：

- Agent 可以调用：`prepare_add_to_cart`、`get_cart_items`；
- Agent 不能调用：`confirm_add_to_cart`、`cancel_pending_action`、`clear_cart_items`。

也就是说，Agent 只能“提出待确认动作”，不能“直接完成敏感动作”。

## 如何防止重复确认

`confirm_add_to_cart` 要求 pending action 的状态必须是 `pending`。

如果同一个 `pending_action_id` 已经是：

- `confirmed`：不能再次确认；
- `cancelled`：不能确认已取消动作。

这样可以避免重复写入购物车。

## 如何防止跨用户确认

`confirm_add_to_cart` 和 `cancel_pending_action` 都会校验请求中的 `user_id` 是否与 `pending_actions.user_id` 一致。

如果不一致，会返回中文错误提示，不执行状态修改，也不会写入购物车。

这可以防止用户 A 确认或取消用户 B 的 pending action。

## 当前 V1 的局限性

V1 仍然是教学/简历项目级实现，有一些明确局限：

- 没有登录认证，`user_id` 由调用方传入；
- 没有支付、订单、库存扣减事务；
- 没有 LangGraph interrupt/resume，确认流程由 API + pending_actions 表实现；
- 没有并发锁或强事务隔离设计；
- 没有 pending action 过期时间；
- 没有审计日志和权限系统；
- SQLite 适合 V1 演示，不适合高并发生产环境。

V2 可以引入认证、PostgreSQL、事务、过期策略、LangGraph HITL 和更完整的审计能力。
