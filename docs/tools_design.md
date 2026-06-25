# ShopMind V1 Tools 设计

## Tool 总览

ShopMind V1 的工具分为四类：

- 商品工具：查询商品列表、详情和对比；
- 文档工具：检索商品文档和政策文档；
- 用户偏好工具：读取和写入长期偏好；
- 购物车和待确认动作工具：创建加购待确认动作、确认/取消加购、读取购物车。

## 工具清单

| Tool | 职责 | 暴露给 Agent | 敏感操作 | 分类 |
| --- | --- | --- | --- | --- |
| `search_products` | 按关键词、类别、价格、库存搜索商品 | 是 | 否 | Safe |
| `get_product_detail` | 查询单个商品 ID/名称的详情 | 是 | 否 | Safe |
| `compare_products` | 对比多个商品价格、类别、库存 | 是 | 否 | Safe |
| `search_product_docs` | 检索商品规格、兼容性、安装、技术说明 | 是 | 否 | Safe |
| `search_policy_docs` | 检索退换货、保修、配送等政策 | 是 | 否 | Safe |
| `get_user_preferences` | 读取用户长期购物偏好 | 是 | 低风险 | Safe |
| `add_user_preference` | 保存用户长期偏好 | 是 | 中等风险 | Sensitive-lite |
| `prepare_add_to_cart` | 创建待确认加购动作，不直接写购物车 | 是 | 中等风险 | Sensitive-gated |
| `get_cart_items` | 查看用户购物车 | 是 | 低风险 | Safe |
| `confirm_add_to_cart` | 确认 pending action，并真正写入购物车 | 否 | 是 | Sensitive |
| `cancel_pending_action` | 取消 pending action | 否 | 是 | Sensitive |
| `clear_cart_items` | 清理用户购物车和 pending action，主要用于测试 | 否 | 是 | Internal/Test |
| `clear_user_preferences` | 清理用户偏好，主要用于测试 | 否 | 是 | Internal/Test |

## Safe Tools

Safe tools 是 Agent 可以直接调用的工具，通常只读取数据，或只创建非最终状态：

- `search_products`
- `get_product_detail`
- `compare_products`
- `search_product_docs`
- `search_policy_docs`
- `get_user_preferences`
- `get_cart_items`

这些工具不会直接产生不可逆业务结果。它们主要用于回答问题、推荐商品、解释政策、读取偏好和查看购物车。

## Sensitive Tools

Sensitive tools 会改变用户状态或业务状态，需要更谨慎：

- `add_user_preference`
- `prepare_add_to_cart`
- `confirm_add_to_cart`
- `cancel_pending_action`

其中 `add_user_preference` 会写入长期偏好，Agent 只有在用户明确表达长期偏好时才应调用。

`prepare_add_to_cart` 会写入 `pending_actions`，但不会真正写入购物车，所以允许 Agent 调用。

`confirm_add_to_cart` 和 `cancel_pending_action` 会改变确认状态或购物车内容，因此不暴露给 Agent，而由 `/api/chat/confirm` 调用。

## Internal/Test Tools

以下工具主要用于测试或维护，不应暴露给 Agent：

- `clear_cart_items`
- `clear_user_preferences`

这些工具具备删除用户数据的能力。如果暴露给 Agent，可能因为模型误判或 Prompt Injection 导致数据被误删。

## 为什么 confirm_add_to_cart 不暴露给 Agent

`confirm_add_to_cart` 会真正写入 `cart_items`，属于敏感业务操作。V1 的安全边界是：

```text
Agent 可以提出待确认动作
API 根据用户显式确认执行敏感动作
```

这样可以避免 Agent 在用户没有明确确认时直接完成加购。

## 为什么 cancel_pending_action 不暴露给 Agent

取消 pending action 也是状态变更。V1 暂时通过 `/api/chat/confirm` 的 `confirmed=false` 来取消，保持所有确认/取消动作都从 API 显式入口进入。

这比让 Agent 自己决定取消更容易审计，也更方便后续升级为 LangGraph interrupt/resume。

## 为什么 clear_cart_items 不暴露给 Agent

`clear_cart_items` 会删除用户购物车和 pending action，主要用于自动化测试清理。它不属于正常购物对话能力，不应暴露给 Agent。

后续如果要实现“清空购物车”业务，也应新增独立的确认流程，而不是复用测试清理工具。
