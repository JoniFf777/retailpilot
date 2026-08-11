# 当前架构审计（Phase 0）

## 已实现

- FastAPI 装配位于 `app/main.py`，公共路由由 `app/api/router.py` 注册。
- V3 读路径位于 `agents/shopmind_multi_agent/`：Supervisor、Product、RAG、Preference、Decision 和 Write Handoff 均已存在。
- `app/runtime/harness.py` 提供运行生命周期；`app/runtime/tool_gateway.py` 提供工具权限边界；`app/api/routes/chat_stream.py` 提供有序 POST-SSE。
- `app/db/models.py` 已有 `Product`、`CartItem`、`PendingAction`；`app/repositories/cart.py` 有 `prepare_add_to_cart`、`confirm_add_to_cart`、`get_cart_items` 和取消逻辑。
- 身份绑定在 `app/dependencies/security.py`，owner-data 在 `app/governance/owner_data.py`；确认入口为 `app/api/routes/chat_confirm.py`。
- 未跟踪 `frontend/` 已提供 JSON/POST-SSE chat、取消、HITL、Privacy、Runs、Status；`frontend/src/api/sse.ts` 是可复用 SSE 边界。

## 部分实现及不匹配

| 领域 | 实际状态 | 影响 |
| --- | --- | --- |
| 商品 | `Product` 仅有 product_id/name/category/price/in_stock | 无 SKU、规格、可配置属性、数量库存 |
| 推荐 | `product_agent.py` 把工具文本压缩为 `product_summary`；`decision_agent.py` 输出文本 | 无公开结构化约束、评分、卡片或比较数据 |
| HITL | PendingAction 已有 owner、expiry、status、精确编辑校验 | `ChatResponse` 仅公开 action id；前端需从 tool name/文本推断预览 |
| Cart | 可确认插入和读取 | 同 owner/product 可重复插入；不检查库存；无 REST cart API |
| Order | `Order`/`OrderItem` 关联历史 `Customer`，仅供旧数据查询 | 不能承载 ShopMind owner、预留、支付或幂等 |
| 部署 | Compose 只定义 postgres | 无前后端、Redis、RocketMQ 或 worker 组合 |

## 可安全拆分边界

2026-08-03 当前工作区实际统计：`app/runtime/harness.py` 1285 行、`app/db/models.py` 719 行、
`app/runtime/contracts.py` 622 行、`app/core/settings.py` 561 行、
`agents/shopmind_multi_agent/write_handoff.py` 561 行、`app/runtime/plan_executor.py` 613 行、
`app/dependencies/agent.py` 492 行。前四类 V4–V6 合约、治理和装配逻辑不能整体替换。Phase 1 新增
`app/recommendation/` 与 `app/catalog/`，经由现有 repositories、Pydantic、Harness 接入；
不移动 Runtime 文件，不改变 V3 公开字段。Phase 3 后再将 cart 用例从
`app/dependencies/agent.py` 抽到服务层。

## 兼容策略

所有新 HTTP 字段和 SSE 终态字段均为可选加性字段；旧 `answer`、`status`、`tool_calls`、
`pending_action_id` 不变。旧 Customer 订单、V1 single Agent、V3 读图和 V6 owner/audit
边界保持原样。
