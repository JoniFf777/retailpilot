## Why

ShopMind 的 Chat/POST-SSE 前端目前在每次 `streamChat()` 调用时生成新的 `Idempotency-Key`，失败重试只保留消息文本，因此一次逻辑用户消息可能被当成多个 execution。后端已有 runtime `idempotency_records`、`agent_runs` 和 request hash，但当前运行中 duplicate 的 claim 不是完整的原子 authoritative-execution 边界，且 persistence failure 会被 Harness 的 start persistence 捕获后忽略，不能安全地证明不会出现第二个 Agent Run 或重复 PendingAction。

这会在网络断线、双击 Retry、代理重复请求和 SSE terminal event 丢失时造成重复执行；如果第一次执行已经创建 PendingAction，后续执行还可能创建第二个 write intent。

## What Changes

- 为每条 frontend logical Chat message 建立稳定的 request idempotency identity；同页面/session 内的 network retry、SSE 中断后 retry 和手动“重试本次消息”复用同一个 key。
- 修改 `streamChat()`/Chat request 调用边界，使 key 由 logical message 持有，而不是每次 fetch attempt 重新生成；用户编辑消息、明确再次发送相同文字、切换 user/thread 时创建新的 logical identity。
- 复用现有 runtime `idempotency_records`、`agent_runs`、request hash 和数据库 unique scope，增加 backend atomic claim/ownership 语义，防止两个相同 key 的并发请求同时进入 Agent execution。
- 明确 same-key 状态语义：running 返回 typed in-progress 与 authoritative run identity；completed/confirmation_required/failed/cancelled 返回或恢复同一个 terminal result，不因 retry 偷偷重新执行。
- 将 browser Stop/AbortController 与 authoritative Run cancellation 分离：停止只停止当前 SSE delivery，保留 logical-message retry identity，不表示后台 Agent 已取消。
- 让 `runtime.idempotency_in_progress` 通过机器可识别的 retry state、runtime error code 和 winner run identity 投影给现有 Chat/Frontend contract；in-progress 不能被当成普通 terminal failed。
- 使 idempotency persistence/claim failure fail closed；不能在无法确认 authoritative identity 时启动第二个 Agent Run。
- 保证一次 authoritative execution 创建的 `pending_action_id` 在 retry/recovery 中原样返回；不重复 prepare，也不自动 confirm 或重构既有 PendingAction confirmation boundary。
- 保持 POST JSON 与 POST-SSE 使用同一 runtime idempotency contract；SSE 仅支持 terminal/current-state recovery，不新增完整 event cursor/resumable stream protocol。
- 保持现有 Chat event-loop/thread/session boundary、RAG failure semantics、canonical Cart、Order expiration 和 PendingAction owner/version/confirm semantics。

## Capabilities

### New Capabilities

- `chat-retry-idempotency`: Defines logical Chat request identity, frontend retry key lifecycle, backend authoritative runtime deduplication, same-key state semantics, disconnect recovery, and duplicate PendingAction prevention.

### Modified Capabilities

- None. `backend-regression-stability`, `commerce-cart`, and `order-expiration` remain independent and unchanged by this proposal.

## Impact

Expected implementation impact is limited to the frontend Chat API/page/message state, the Chat/SSE request boundary, runtime Harness idempotency claim and runtime-run repository behavior, and directly related unit/API/frontend/PostgreSQL tests. Existing runtime persistence tables and unique constraints are intended to be reused; a migration is not expected unless implementation proves the current database contract cannot safely express the atomic claim.

Page-refresh recovery, full chat-history UI, full persisted SSE cursor replay, WebSocket transport, payment idempotency, PendingAction confirmation idempotency, Redis/RocketMQ, authentication redesign, and unrelated commerce/Agent changes remain out of scope.

PostgreSQL integration is required for the correctness proof of concurrent same-key claim/unique conflict if the existing runtime persistence uses PostgreSQL as its authoritative store. Local SQLite tests can prove hash/state/replay behavior but cannot replace the database concurrency test.

## Acceptance Criteria

- One logical user message owns one stable idempotency key until its authoritative result is terminal.
- Automatic/network retry and manual retry of an interrupted message reuse the original key; a new logical message or edited message gets a new key.
- Same key plus same canonical request hash never creates a second authoritative Agent Run, including concurrent duplicate requests.
- Same key plus different request hash returns the existing typed idempotency conflict and never executes the Agent.
- Running duplicate requests do not execute a second Agent and expose the authoritative run identity through the existing typed runtime boundary.
- Completed, confirmation-required, failed, and cancelled same-key requests return/recover the original terminal result without silently re-executing.
- A disconnect after PendingAction preparation cannot create a second PendingAction on same-key retry; recovered action ID/version/preview remain unchanged and confirmation is not automatic.
- Idempotency claim/persistence failure fails closed rather than starting a second execution.
- User/thread identity is part of the logical identity; keys are never reused across switched users or threads.
- Page-refresh recovery and full SSE event-cursor replay are explicitly either out-of-scope or future work, not accidental partial behavior.
- Existing backend-regression-stability, commerce-cart, and order-expiration behavior remains unchanged.
- Focused backend/API/runtime tests, full non-integration backend tests, and relevant frontend Vitest/lint/typecheck pass; isolated PostgreSQL concurrency tests pass when PostgreSQL is required for the claim proof.
