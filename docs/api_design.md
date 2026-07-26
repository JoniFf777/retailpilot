# ShopMind API 设计

Updated: 2026-07-26

## V6 Owner-Data API Addendum

Five additive authenticated endpoints implement the privacy and bounded
run-inspection lifecycle without changing default V3 chat payloads:

```text
POST /api/owner-data/inspect
POST /api/owner-data/runs/inspect
POST /api/owner-data/memory/correct
POST /api/owner-data/memory/delete
POST /api/owner-data/delete
```

All bodies are `extra="forbid"` and require `user_id`. Inspection accepts an
optional `memory_limit` from 1 to 100 and returns fixed category counts plus
bounded memory rows. Correction also requires `memory_id` and 1-4000 characters
of replacement `content`. Single-memory deletion requires `memory_id`.

Run inspection accepts exactly one `run_id` or `trace_id` plus an optional
`event_limit` from 1 to 100. Its frozen
`shopmind.owner-run-inspection.v1` projection returns exact-owner run metadata,
typed usage and ordered client-visible event summaries. It never returns
request/result JSON, input/output text, debug/error/metadata, tool or
idempotency records, event payloads, or internal/audit events. Missing and
cross-owner selectors share the same 404 response.

Full deletion requires an explicit UUID and literal confirmation:

```json
{
  "user_id": "demo-user",
  "deletion_request_id": "07bd44fd-2c98-450e-9e1d-6ed963d1192c",
  "confirmed": true
}
```

It returns `status="deleted"` with per-category counts, or
`status="already_deleted"` and zero affected rows when no owner data remains.
Missing/cross-owner authentication returns 401/403 before storage access;
missing memory returns 404; sanitized storage failure returns 503. Products,
documents, inherited customers/orders and fingerprint-only audit records are
never targets of this endpoint.

## V6 Signed Ingress Identity Addendum

`SHOPMIND_IDENTITY_PROVIDER=signed_header` is a server-selected alternative to
the unchanged `development_payload` default and the existing trusted-header
mode. It applies to chat, confirmation, streaming and owner-data routes through
the same dependency and requires four fixed headers:

```text
X-ShopMind-Authenticated-User
X-ShopMind-Identity-Timestamp
X-ShopMind-Identity-Nonce
X-ShopMind-Identity-Signature
```

The signature is a lowercase HMAC-SHA256 hex digest over the versioned
subject/timestamp/nonce assertion documented in `docs/development.md`.
Assertions are short-lived and one-time; replay protection uses the
server-selected local/Redis coordination backend and stores only a fingerprint.
Missing, partial, invalid, expired, replayed or backend-unavailable assertions
all return HTTP 401 with `WWW-Authenticate: ShopMindSignedHeader`. A body owner
different from the authenticated subject still returns HTTP 403 before Agent,
action-confirmation, SSE-admission or owner-data storage execution. No request
body can select this mode or supply roles, scopes, shared secrets or endpoints.

## V6 Governance Audit Operations Addendum

`GET /api/health/governance-audit` is an additive, read-only process metrics
endpoint. It never queries or returns governance audit records. Its versioned
response contains:

- server-owned `audit_enabled`;
- process status `disabled`, `ok`, `warning`, or `degraded`;
- the `shopmind.governance-audit-monitor.v1` process scope and alert threshold;
- cumulative emission/storage/requested/persisted/duplicate/skip/failure
  counters;
- consecutive failures, alert/recovery transition counts, and closed
  status/reason/timestamp values.

The endpoint always returns HTTP 200, including when the optional audit store is
degraded. Operators should keep it on an internal operations boundary, scrape
every API replica and alert on `monitor.alert_active=true`. It has no fields for
subjects, fingerprints, audit IDs, requests, messages, actions, memory,
credentials, exception text or connection details.

`GET /api/health/preflight` returns the frozen
`shopmind.production-preflight.v1` static configuration report. Its six checks
cover identity, coordination, governance audit, RAG transport, retention
cleanup and runtime limits. The response contains only profile/status,
aggregate counts, closed check IDs/categories/statuses/reasons and no
configuration values. Development reports `not_applicable`; a blocked explicit
production profile fails application creation before routes are exposed. This
endpoint performs no external reachability probe and belongs on the internal
operations boundary.

`GET /api/health/readiness` runs the frozen
`shopmind.deployment-readiness.v1` live checks. It returns HTTP 200 when all
applicable checks pass and HTTP 503 when configuration, PostgreSQL connectivity,
exact migration head, selected coordination backend or recent production
cleanup evidence fails. Development marks only the production-specific
configuration and retention checks `not_applicable`; PostgreSQL, migration and
coordination still run. The response contains closed IDs/categories/statuses/
reasons and aggregate counts only—never database/Redis identity, migration
values, evidence paths, credentials or exception text.

`GET /api/health/service-metrics` returns
`shopmind.service-health.v1`, combining a bounded
`shopmind.service-metrics.v1` process snapshot with a closed
`shopmind.service-slo.v1` evaluation. It contains only aggregate
operation/status/replay/usage/tool/step counts, a fixed-capacity numeric latency
window summary, configured SLO thresholds and closed check states. It has no
identity, request, thread, run, trace, action, content, error or arbitrary label
fields. `insufficient_data`, `met` and `breached` all return HTTP 200; admission
and load-balancer routing continue to use `/api/health/readiness`.

本文件描述当前 V3 兼容的公开 API。V4/V5 运行时、持久化、SSE 与多 Agent
执行都位于该边界之后；远程 specialist 端点和凭据永远不是公开请求字段。

## API 总览

ShopMind 提供以下 V3 兼容及 V6 加性 FastAPI 接口：

- `GET /api/health`
- `GET /api/health/governance-audit`
- `GET /api/health/preflight`
- `GET /api/health/readiness`
- `GET /api/health/service-metrics`
- `POST /api/chat`
- `POST /api/chat/confirm`
- `POST /api/chat/stream`
- `POST /api/owner-data/inspect`
- `POST /api/owner-data/runs/inspect`
- `POST /api/owner-data/memory/correct`
- `POST /api/owner-data/memory/delete`
- `POST /api/owner-data/delete`

其中 `/api/chat` 调用 ShopMind Agent，`/api/chat/confirm` 用于确认或取消待确认动作，`/api/chat/stream` 以 SSE 返回同一次 Harness 执行产生的有序事件。V3 multi-agent 模式保持同一 JSON 合约，并可通过 `include_debug` 返回额外调试元数据。

三个 POST 接口都接受可选 `Idempotency-Key` 请求头。该值只用于服务端运行或确认幂等；请求体不能覆盖运行时策略、预算、工具权限、specialist 端点或凭据。

V6 身份边界由服务端 `SHOPMIND_IDENTITY_PROVIDER` 选择。默认
`development_payload` 保持现有 `user_id` 行为。显式 `trusted_header`
模式要求受信入口清除客户端同名头后注入
`X-ShopMind-Authenticated-User`：缺失返回 401，请求体 `user_id` 与主体
不一致返回 403，且拒绝发生在 Agent、确认处理或 SSE admission 之前。
请求 JSON 不接受 identity provider、roles、scopes 或凭据。

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

当请求设置 `"include_debug": true`，且后端运行在 V3 multi-agent 路径时，响应会额外包含精简 `debug` 字段以及不透明的 `run_id`、`trace_id`。这两个
标识符仅用于带身份绑定的运行投影查询，本身不授予访问权限。默认响应不包含
这些字段，也不会暴露完整 `raw_result`。

```json
{
  "answer": "可以考虑测试键盘。",
  "status": "completed",
  "tool_calls": ["search_products"],
  "user_id": "demo-user",
  "thread_id": "demo-thread",
  "pending_action_id": null,
  "run_id": "run-opaque-id",
  "trace_id": "trace-opaque-id",
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

## POST /api/chat/stream

请求体与 `/api/chat` 相同，响应媒体类型为 `text/event-stream`。每个事件都包含
单调递增的 `sequence`、稳定 `event_type`、可选 `trace_id`、`visibility` 和
结构化 `payload`。运行事件、plan/step/attempt 生命周期事件均来自同一 Harness
事件序列，可被持久化并实时消费；终止事件为 `run.result` 或安全化的
`run.failed`。

当原请求设置 `include_debug=true` 时，终止 `run.result` 的 payload 会额外带
不透明 `run_id` 和 `trace_id`，供随后调用
`POST /api/owner-data/runs/inspect`。默认流终止 payload 保持原状。

服务端使用有界事件缓冲区和并发限制。客户端断开或缓冲区耗尽时触发协作式
取消；已经进入同步调用的工作不会被强制终止。最终事件入队前会等待已接收的
worker 事件刷新，避免完成事件越过先前的 attempt/step 事件。

```text
event: plan.step.attempt.started
data: {"sequence":4,"event_type":"plan.step.attempt.started",...}

event: run.result
data: {"sequence":9,"event_type":"run.result","payload":{"status":"completed",...}}
```

## POST /api/chat/confirm

该端点保持 V3 请求/响应 schema，但内部不再假定所有 action 都是加购。服务端先按
`pending_action_id + user_id + thread_id` 解析持久化记录，再由 Action Registry
选择唯一注册的 confirm/cancel handler。目前支持 `add_to_cart` 和
`save_preference`；客户端不能提交 `action_type`、风险等级或 handler 名称。

`save_preference` 只有确认成功后才写入长期偏好。取消、过期、重复确认、跨用户/
线程访问或未注册 action 都不会产生偏好写入。未传任何新字段的既有加购请求保持
原行为。

Slice 36 adds the optional `updated_arguments` object for confirm requests.
The Registry validates it against the persisted action definition before any
handler runs: `add_to_cart` accepts only a positive integer `quantity`, and
`save_preference` accepts only `preference_type` and/or a non-blank
`preference_value`. Extra fields, empty edits, edits on cancellation, or attempts
to change product/action/owner/thread/risk/expiry/handler fail closed. A valid
edit and confirmation execute under the same row lock and transaction.

用于确认或取消 `/api/chat` 返回的 pending action。

### Request Body

```json
{
  "user_id": "demo-user",
  "pending_action_id": "123e4567-e89b-12d3-a456-426614174000",
  "confirmed": true,
  "thread_id": "demo-thread",
  "updated_arguments": {"quantity": 2},
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

`include_debug` is optional and defaults to `false`. When set to `true`, the
response can include confirmation debug metadata plus opaque `run_id` and
`trace_id` selectors. Default confirmation responses remain unchanged.

`updated_arguments` is optional. Omitting it preserves the V3 request behavior.
The `pending_action_id` remains the only resume token across process restarts;
clients never send `action_type` or a handler name.

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
  "run_id": "run-opaque-id",
  "trace_id": "trace-opaque-id",
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
