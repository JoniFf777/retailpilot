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

V3 multi-agent 路径是 read-only。用户请求加购、下单、清空购物车或保存偏好等写操作时，V3 会先返回 `write_path_handoff` 决策，然后 API dependency 会桥接到原生 V3 write handoff handler。此时业务响应仍然是 `confirmation_required`，但 debug 会保留 V3 guardrail 轨迹。

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
      "to": "v3_write_handoff_path",
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
| `debug.multi_agent_handoff.reason == "read_only_multi_agent_write_intent"` | 说明本次请求先经过 V3 read-only guardrail，再桥接到原生 V3 确认式写入准备路径 |
| `debug.multi_agent_debug.supervisor_decision.safety_flags` 包含 `write_intent_blocked` | 表示 V3 没有执行 read agents，也没有直接调用写工具 |

### V3 add-to-cart handoff 流程

V3 multi-agent 模式下，加购请求会先经过 read-only guardrail，再进入原生 V3 write handoff handler。handler 只在请求足够明确时创建 pending action。

| 用户输入 | API 行为 |
| --- | --- |
| `帮我把 TECH-KEY-001 加入购物车 2 个` | 返回 `confirmation_required`，调用 `prepare_add_to_cart`，生成 `pending_action_id` |
| `帮我把这个键盘加入购物车` | 返回 `completed` 澄清，列出最多 3 个有货候选商品 ID，不调用写工具，不创建 pending action |
| `选 1`，且同一 `user_id + thread_id` 下存在候选上下文 | 返回 `confirmation_required`，使用候选 1 的商品 ID 和原请求数量生成 pending action |
| `选 3`，但当前只有 2 个候选 | 返回 `completed` 澄清，提示候选范围，不调用写工具，不创建 pending action |
| 缺少 `user_id` | 返回 `completed` 澄清，提示需要 `user_id`，不调用写工具 |

候选上下文保存在数据库 `candidate_contexts` 表中，并按 `user_id + thread_id` 绑定。上下文 10 分钟过期，最多保留 100 条，超过后清理最旧记录。调用方应始终在候选澄清和后续选择中传同一个 `thread_id`。

候选澄清响应示例：

```json
{
  "answer": "我还不能确定要加入购物车的具体商品。请回复要加购的商品 ID，可从这些候选中选择：\n1. Test Keyboard（TECH-KEY-001） - $99.00",
  "status": "completed",
  "tool_calls": [],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": null
}
```

候选选择越界响应示例：

```json
{
  "answer": "当前候选只有 1-1，你选择的是 2。请重新选择候选编号，或直接回复明确的商品 ID，例如 TECH-KEY-001。",
  "status": "completed",
  "tool_calls": [],
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
  "thread_id": "demo-thread",
  "include_debug": false
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user_id` | string | 是 | 用户 ID，必须与 pending action 所属用户一致 |
| `pending_action_id` | string | 是 | 待确认动作 ID |
| `confirmed` | boolean | 是 | `true` 表示确认，`false` 表示取消 |
| `thread_id` | string/null | 否 | 会话 ID，V1 主要透传 |

`include_debug` is optional and defaults to `false`. When set to `true`, the response can include confirmation debug metadata.

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

### Confirm Debug Response

When `include_debug=true`, `/api/chat/confirm` can include stable confirmation metadata:

```json
{
  "answer": "Confirmed add-to-cart action.",
  "status": "completed",
  "tool_calls": ["confirm_add_to_cart"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000",
  "debug": {
    "confirmation": {
      "events": [
        {
          "index": 1,
          "event": "pending_action_confirmed",
          "requested_confirmation": true,
          "status": "completed",
          "tool_call": "confirm_add_to_cart"
        }
      ]
    }
  }
}
```

Confirmation event names:

- `pending_action_confirmed`
- `pending_action_cancelled`
- `pending_action_failed`

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
