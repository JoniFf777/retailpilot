## Why

ShopMind 的 V3 Multi-Agent 读图已经把 Preference Agent 限制为 `get_user_preferences`，并通过 `write_handoff` 为加购和保存偏好创建 PendingAction；但真实仓库仍保留一条 V1 Single Agent 直写路径：`agents/shopmind_agent.py:25,65-72` 将 `tools.preferences.add_user_preference` 暴露给 LLM，而 `tools/preferences.py:101-121` 直接调用 repository 并提交 `UserPreference`。这使同一类“保存用户偏好”操作在 Single 与 Multi 两种 runtime 下拥有不同的安全边界。

当前还存在 legacy `clear_user_preferences` direct-write tool（`tools/preferences.py:137-150`）以及 legacy preference PendingAction confirmation（`app/repositories/cart.py:355-430`）。后者虽然经过用户确认，但 payload 没有 canonical schema version，历史 action 仍可能进入旧确认实现。本 Change 统一 Agent 写操作边界，确保 Agent/LLM 永远只能读取，或准备一个可审计、可确认、可重放的 PendingAction；真正的用户/业务状态写入只能由确定性的 confirmation service 完成。

## What Changes

- 建立正式 Agent/tool write-boundary inventory，并明确 read-only、write-intent preparation、confirmation write、runtime metadata write 的区别。
- 从 active Single Agent tool set 中移除 preference direct-write 能力；Single 与 Multi 的 preference intent 都进入同一个 `prepare_save_preference` PendingAction handoff。
- 将新 preference action 统一到最小、machine-readable、versioned 的 canonical payload；保留现有 `save_preference` action type、owner/thread/version/expiry/replay 边界。
- 让 confirmation service 根据 persisted PendingAction payload 和客户端 `expected_version` 确定性追加一条 preference；confirm 阶段不调用 LLM，也不重新解释用户文本。
- 对 cancel/reject、expired、stale version、owner/thread mismatch、invalid/legacy action schema fail closed，保证不会产生 preference/cart mutation。
- 保持已经完成的 canonical ShopMind Cart prepare/confirm flow 不变，只把它作为统一 HITL boundary 的既有参考实现。
- 禁止 active Agent 使用 `clear_user_preferences`、legacy `clear_cart_items` 或 legacy direct Cart writer；历史非 canonical preference actions 可读/取消时保留兼容性，confirm 要求 typed `unsupported_action_schema` 并重新 prepare，不做 destructive migration。
- 增加 static inventory、pre-confirm DB unchanged、exactly-once confirm/replay、owner/thread/version、Single/Multi parity 及 canonical Cart 回归测试。

## Capabilities

### New Capabilities

- `agent-write-hitl`: Defines the long-term boundary that separates Agent reads, write-intent preparation, human confirmation, and deterministic persistence for user/business state.

### Modified Capabilities

- None. `backend-regression-stability`, `commerce-cart`, `order-expiration`, and `chat-retry-idempotency` remain independent and unchanged by this proposal.

## Scope

In scope: active ShopMind Single Agent and Multi-Agent write paths; preference save/clear exposure; `write_handoff`; Action Registry and Tool Gateway policy; PendingAction payload/lifecycle; deterministic confirmation service; Chat JSON/SSE confirmation compatibility; legacy preference action safety; directly related tests and minimal frontend confirmation compatibility.

Out of scope: payment, Order expiration, reservation lifecycle, recommendation ranking, RAG behavior, localization, multi-category support, authentication redesign, Redis/RocketMQ, page-refresh Chat recovery, and broad Agent architecture refactoring. Runtime run/event/audit/candidate-context persistence remains system-owned execution metadata, not user/business domain mutation, and is not converted into user HITL.

## Impact

Expected implementation impact is limited to `agents/shopmind_agent.py`, `tools/preferences.py`, the preference/write-handoff and PendingAction service boundary, Tool Gateway/permission declarations, confirmation API adapters, and focused tests. The existing first-party frontend `ActionDrawer` already supports `save_preference` typed editable fields; frontend changes should be additive/minimal only if the canonical payload changes the existing API contract. No migration is planned: legacy non-canonical preference actions fail safely on confirm and require re-preparation.

## Acceptance Criteria

- No active Agent tool set can directly commit a `UserPreference`, legacy `CartItem`, or other user/business domain write.
- Read-only tools remain directly executable without unnecessary HITL.
- Preference intent from both Single and Multi runtime creates a typed `save_preference` PendingAction and leaves `UserPreference` unchanged before confirmation.
- Confirmation validates owner, thread, pending status, expiry, expected version, action schema, and deterministic payload before one caller-owned transaction writes the preference and resolves the action.
- Confirm replay with the same transition does not create a second preference write; cancel/reject/stale/expired/unauthorized paths do not write.
- Legacy non-canonical preference actions cannot be dynamically converted or confirmed into a write; they fail with a stable typed error and require re-preparation.
- Existing canonical Cart HITL behavior, Chat retry/PendingAction replay, backend regression stability, RAG failure semantics, and Order/payment safety remain unchanged.
- Relevant focused tests and the full non-integration backend suite pass; PostgreSQL integration is designed/run only where transaction or concurrency correctness requires it.
