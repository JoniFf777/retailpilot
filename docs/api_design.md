# ShopMind API 设计

## API 总览

ShopMind 提供三个 FastAPI 接口：

- `GET /api/health`
- `POST /api/chat`
- `POST /api/chat/confirm`

其中 `/api/chat` 调用 ShopMind Agent，`/api/chat/confirm` 用于确认或取消待确认动作。V3 multi-agent 模式保持同一 API 合约，并可通过 `include_debug` 返回额外调试元数据。

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
  "thread_id": "demo-thread",
  "include_debug": false
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 是 | 用户输入 |
| `user_id` | string/null | 否 | 用户 ID，用于偏好记忆、购物车和待确认动作 |
| `thread_id` | string/null | 否 | 会话 ID，V1 主要透传，后续可用于多轮状态 |
| `include_debug` | boolean | 否 | 默认 `false`。设为 `true` 时返回精简调试元数据 |

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

### 可选 debug Response

当请求设置 `"include_debug": true`，且后端运行在 V3 multi-agent 路径时，响应会额外包含精简 `debug` 字段。默认响应不包含该字段，也不会暴露完整 `raw_result`。

```json
{
  "answer": "可以考虑测试键盘。",
  "status": "completed",
  "tool_calls": ["search_products"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": null,
  "debug": {
    "supervisor_decision": {
      "routes": ["product_agent"],
      "router_type": "deterministic"
    },
    "agent_steps": [
      {
        "index": 1,
        "node": "supervisor",
        "event": "routed",
        "router_type": "deterministic"
      }
    ],
    "routes": ["product_agent"],
    "executed_routes": ["product_agent"]
  }
}
```

V3 read-only multi-agent 的常见 debug 字段：

| 字段 | 含义 |
| --- | --- |
| `supervisor_decision` | supervisor 的结构化路由决策，包括 `intent`、`routes`、`routing_reasons`、`confidence`、`router_type` 等 |
| `agent_steps` | 执行轨迹，记录 supervisor、route dispatcher、各 read agent 和 decision agent 的步骤 |
| `routes` | supervisor 计划执行的 read agent 路由 |
| `executed_routes` | 实际已执行的 read agent 路由 |
| `decision` | decision agent 的最终结构化决策，例如 `answer_type`、`used_summaries`、`requires_followup` |
| `safety_flags` | 安全标记，例如 `rag_prompt_injection_detected` 或 `write_intent_blocked` |

当 `SHOPMIND_SUPERVISOR_ROUTER=llm` 时，`supervisor_decision` 和 `agent_steps` 可能额外包含：

| 字段 | 含义 |
| --- | --- |
| `router_provider` | LLM router provider 类型，例如 `langchain_structured_output` |
| `router_model` | LLM router 使用的模型名 |
| `fallback_reason` | LLM router 回退原因，例如 `provider_error`、`invalid_routes` |
| `fallback_router_type` | 回退使用的 router 类型 |

### V3 write-intent handoff debug Response

V3 multi-agent 路径是 read-only。用户请求加购、下单、清空购物车或保存偏好等写操作时，V3 会先返回 `write_path_handoff` 决策，然后 API dependency 会桥接到现有确认式写入路径。此时业务响应仍然是 `confirmation_required`，但 debug 会保留 V3 guardrail 轨迹。

```json
{
  "answer": "我已为你生成待确认加购，请确认是否加入购物车。",
  "status": "confirmation_required",
  "tool_calls": ["prepare_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000",
  "debug": {
    "multi_agent_handoff": {
      "from": "multi_agent_read_path",
      "to": "single_agent_write_path",
      "reason": "read_only_multi_agent_write_intent",
      "status": "confirmation_required"
    },
    "multi_agent_debug": {
      "supervisor_decision": {
        "intent": "write_path_unsupported",
        "routes": [],
        "router_type": "deterministic",
        "safety_flags": ["write_intent_blocked"],
        "handoff_reason": "read_only_multi_agent_write_intent"
      },
      "routes": [],
      "executed_routes": [],
      "decision": {
        "status": "handoff_required",
        "answer_type": "write_path_handoff",
        "requires_followup": true,
        "followup_reason": "read_only_multi_agent_write_intent",
        "safety_flags": ["write_intent_blocked"],
        "tool_calls": []
      },
      "safety_flags": ["write_intent_blocked"]
    }
  }
}
```

调用方可按以下规则处理：

| 条件 | 建议处理 |
| --- | --- |
| `status == "confirmation_required"` 且有 `pending_action_id` | 展示确认 UI，并调用 `/api/chat/confirm` 完成确认或取消 |
| `debug.multi_agent_handoff.reason == "read_only_multi_agent_write_intent"` | 说明本次请求先经过 V3 read-only guardrail，再桥接到确认式写入路径 |
| `debug.multi_agent_debug.supervisor_decision.safety_flags` 包含 `write_intent_blocked` | 表示 V3 没有执行 read agents，也没有直接调用写工具 |

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
