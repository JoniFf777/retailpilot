# API 契约演进

## 保持兼容

`POST /api/chat`、`POST /api/chat/stream`、`POST /api/chat/confirm` 的既有字段和状态不变。所有新字段是
optional，加性 OpenAPI/Pydantic 字段；不公开 audit、原始 action payload、RAG payload 或任何浏览器签名
secret。

## Phase 1

- `ChatResponse.recommendation?: RecommendationResult` 和可选 `projection_error`。
- JSON 与 `run.result` 通过同一个 API Response Builder 投影，不由 Runtime 自动转换。
- 推荐终态数据带 `schema_version=shopmind.recommendation.v1`；中间 SSE 事件不可作为商品事实。已持久化
  completed run 的损坏 recommendation 不改变 run status，两个传输都返回 `recommendation=null` 和稳定
  `projection_error.code=recommendation_projection_corrupt`；Graph/Service 验证失败才在持久化前成为 failed run。

idempotency response fingerprint 只覆盖规范化公开字段和 canonical RecommendationResult，不包含原始
`output_data`、debug 或 recommendation diagnostics。

## Phase 2

`ChatResponse.pending_action_view?: PendingActionView`，包含 action_id、action_type、risk_level、
expires_at、status、preview、version、editable_fields。editable field 指明 name/type/required/min/max/enum；
确认请求仍提交 `updated_arguments`，服务端在 row lock 下重新校验 owner/thread/version/status/expiry。

## 后续 REST

```text
GET /api/cart
PATCH /api/cart/items/{cart_item_id}
DELETE /api/cart/items/{cart_item_id}
DELETE /api/cart
POST /api/checkout/preview
POST /api/orders
GET /api/orders
GET /api/orders/{order_id}
POST /api/orders/{order_id}/cancel
```

Cart/checkout/order 统一由 `IdentityBoundary` 得到 owner，不信任 body 中价格或 owner。创建订单/支付使用
`Idempotency-Key`；删除/清空保持幂等。统一错误模型在实施时应继承现有 FastAPI `detail` 风格并增加稳定的
机器码，不能以自然语言字符串作为前端分支条件。

Phase 4A only adds Checkout Preview and pending-payment Order reservation/cancellation. It does not
accept or persist address, shipping, tax, payment, automatic expiration, coupon, discount, FX, Redis,
RocketMQ, Outbox/Inbox, or frontend contracts. `checkout_invalid` is a typed 409, while token expiry and
unavailable signing configuration are typed 410 and 503 respectively.

## Phase 5A Mock Payment

Phase 5A adds the isolated Mock Payment Attempt contract:

```text
POST /api/orders/{order_id}/payments
GET  /api/orders/{order_id}/payments
```

The POST body is limited to `provider: "mock"` and an opaque
`payment_method_ref`. `Idempotency-Key` is required and identity, amount and
currency come from the owner-bound Order snapshot. Public responses do not
expose internal request hashes, provider idempotency keys or provider payment
identifiers. A successful attempt transitions the Order from
`pending_payment` to `paid` and consumes its active Inventory Reservations;
declined attempts remain `pending_payment` with active Reservations.

Provider calls are server-owned and occur outside the database transaction.
Provider success is persisted before local finalization so a same-key retry can
resume finalization without charging again. Phase 5A does not include a real
provider, webhook, refund/chargeback, automatic reconciliation, frontend Phase
5B, Redis, RocketMQ, Outbox or Inbox.
