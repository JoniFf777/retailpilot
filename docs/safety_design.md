# ShopMind 安全设计

Updated: 2026-07-26

## V6 Governance Addendum

- Identity providers are selected only by server configuration. The compatibility
  default is `development_payload`; explicit `trusted_header` mode binds the
  ingress subject, while `signed_header` additionally verifies a short-lived
  timestamp/nonce/HMAC assertion and one-time local/Redis replay claim. Both
  reject missing/mismatched ownership before execution.
- `shopmind.governance-audit.v1` stores only domain-separated fingerprints and
  closed allowlisted metadata in `governance_audit_records`.
- `SHOPMIND_GOVERNANCE_AUDIT_ENABLED` is server-owned and defaults to `false`.
  When enabled, identity allow/deny decisions and Harness-projected typed tool,
  action-lifecycle and selected-memory facts are emitted. Request text, memory
  content, tool arguments/results, credentials, headers and URLs are excluded.
- Runtime persistence and governance emission use separate transactions.
  Audit failure is reduced to sanitized `storage_unavailable`, rolls back only
  the audit batch and cannot change an identity decision, Agent result or
  sensitive-action transition.
- `shopmind.governance-audit-monitor.v1` keeps only process-local counters,
  closed status/reason values and timestamps. Consecutive-failure active/recovery
  alerts never include records, identities, payloads, credentials, exceptions
  or URLs. The operational health endpoint remains HTTP 200 so audit failure
  cannot become business liveness failure.
- Owner-data inspection/correction/deletion is authenticated and exact-owner
  scoped. Memory deletion and explicitly confirmed full deletion are hard
  deletes; full deletion is transactional and cannot target catalogs,
  inherited customer/order seeds, or independently retained audit facts.
- A full deletion body must contain a UUID request ID and literal confirmation.
  When audit is enabled, PII-safe request/execute facts survive raw owner-row
  deletion under their own retention. Storage failure returns a stable 503
  without backend details.
- Production signed-ingress identity is implemented without remote IdP/JWKS
  calls. Sanitized audit monitoring is implemented; explicit catalog baseline
  acceptance and deployment rollout remain V6 Slice 4 work.

## 当前 V3-V5 安全边界

V1 的确认式加购原则仍然有效，但当前实现已经扩展到 PostgreSQL、V3
read-only multi-agent、V4 Harness/Tool Gateway 和 V5 plan/adapter policy：

- Supervisor 与 Decision Agent 不持有工具；Product、RAG、Preference Agent
  只拥有各自声明的只读 capability。
- 写意图先被 read graph 拒绝，再进入独立 handoff；只有
  `/api/chat/confirm` 可以确认或取消 Action Registry 中的待确认动作。
- pending action 按用户、线程、状态、过期时间和幂等键校验，并在事务中加行锁；
  重复确认、跨用户确认和过期动作都不能写购物车。
- Action Registry 现在注册 `add_to_cart` 和 `save_preference`。确认端点从服务端
  pending record 解析类型并选择 handler，调用方不能伪造类型；Preference Agent
  仍是只读，偏好保存只有经过同一显式确认边界才执行。
- 每个 action definition 声明精确的可编辑 schema。加购只能修改正整数数量，偏好
  只能修改规范化类型/非空值；未知字段、空编辑、取消时编辑均在 handler 前拒绝。
  合法编辑与最终确认共享同一行锁和事务，不能修改 action 类型、owner、thread、
  risk、expiry 或 handler。
- Tool Gateway 根据 server-owned manifest 检查 Agent、参数、资源、预算和副作用，
  并生成结构化审计记录；调用方不能通过 prompt 或 API 扩权。
- V5 specialist adapter 必须进入 policy-required Registry。共享 guard 在调用前
  执行 step/delegation/time 预算，在结果或失败后核对 usage；重试由 Plan Executor
  独占，默认仍为一次。
- HTTP specialist transport 只接受服务端固定的 HTTPS 主机白名单、超时、响应
  上限和凭据；API 请求不能选择端点，错误不会记录 token、响应正文或 provider
  异常细节。

下文保留 V1 原始确认机制说明，作为现行边界的基础，而不是完整现状。

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

## 当前剩余安全工作

- 服务端身份模式、主体 owner binding 和签名入口认证已经接入；默认
  `development_payload` 仍仅用于兼容开发，生产多进程签名入口必须保护共享
  密钥并启用 Redis replay coordination。
- Action Registry 已完成多 action 强确认、schema-bounded edit 与 PostgreSQL
  restart/resume/replay 轨迹，V5 安全退出条件已满足。
- 还没有支付、订单、库存扣减等商业交易能力；这些也不属于当前 Agent
  Engineering 项目的完成条件。
- Tool Gateway 是能力/资源/副作用策略边界，不是 OS 级任意代码沙箱。
- V6 仍需完成 PII 脱敏、审计查询、retention/deletion、部署密钥管理和
  多进程协调安全测试。
