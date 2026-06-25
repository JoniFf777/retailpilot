# ShopMind V1 API 设计

## API 总览

ShopMind V1 提供三个 FastAPI 接口：

- `GET /api/health`
- `POST /api/chat`
- `POST /api/chat/confirm`

其中 `/api/chat` 调用 ShopMind Agent，`/api/chat/confirm` 用于确认或取消待确认动作。

## GET /api/health

用于健康检查。

### Response

```json
{
  "status": "ok"
}
```

## POST /api/chat

用于发送用户消息给 ShopMind Agent。

### Request Body

```json
{
  "message": "帮我把 TECH-KEY-010 加入购物车",
  "user_id": "demo-user",
  "thread_id": "demo-thread"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 是 | 用户输入 |
| `user_id` | string/null | 否 | 用户 ID，用于偏好记忆、购物车和待确认动作 |
| `thread_id` | string/null | 否 | 会话 ID，V1 主要透传，后续可用于多轮状态 |

### completed Response

```json
{
  "answer": "我建议你优先考虑 Logitech MX Keys，因为它适合办公使用。",
  "status": "completed",
  "tool_calls": ["search_products"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": null
}
```

### confirmation_required Response

当 Agent 调用 `prepare_add_to_cart` 创建待确认动作后，返回：

```json
{
  "answer": "我已为你生成待确认加购，请确认是否加入购物车。",
  "status": "confirmation_required",
  "tool_calls": ["prepare_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

## POST /api/chat/confirm

用于确认或取消 `/api/chat` 返回的 pending action。

### Request Body

```json
{
  "user_id": "demo-user",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000",
  "confirmed": true,
  "thread_id": "demo-thread"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user_id` | string | 是 | 用户 ID，必须与 pending action 所属用户一致 |
| `pending_action_id` | string | 是 | 待确认动作 ID |
| `confirmed` | boolean | 是 | `true` 表示确认，`false` 表示取消 |
| `thread_id` | string/null | 否 | 会话 ID，V1 主要透传 |

### confirmed=true Response

```json
{
  "answer": "已确认加入购物车。",
  "status": "completed",
  "tool_calls": ["confirm_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### confirmed=false Response

```json
{
  "answer": "已取消待确认动作 123e4567-e89b-12d3-a456-426614174000。",
  "status": "cancelled",
  "tool_calls": ["cancel_pending_action"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

## status 说明

| status | 含义 |
| --- | --- |
| `completed` | 请求已完成，无需用户继续确认 |
| `confirmation_required` | 已创建 pending action，需要用户调用 `/api/chat/confirm` 确认或取消 |
| `cancelled` | 用户取消了 pending action |
| `failed` | 确认/取消失败，例如用户不匹配、pending action 不存在或状态不可重复确认 |

## 完整加购确认流程示例

### 1. 用户发起加购

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"帮我把 TECH-KEY-010 加入购物车\",\"user_id\":\"demo-user\",\"thread_id\":\"demo-thread\"}"
```

返回：

```json
{
  "answer": "我已为你生成待确认加购，请确认是否加入购物车。",
  "status": "confirmation_required",
  "tool_calls": ["prepare_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### 2. 用户确认加购

```bash
curl -X POST http://127.0.0.1:8000/api/chat/confirm \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"demo-user\",\"pending_action_id\":\"123e4567-e89b-12d3-a456-426614174000\",\"confirmed\":true,\"thread_id\":\"demo-thread\"}"
```

返回：

```json
{
  "answer": "已确认加入购物车。",
  "status": "completed",
  "tool_calls": ["confirm_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000"
}
```
