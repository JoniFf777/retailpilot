# 改造差距分析

## 已有能力

| 能力 | 状态 | 真实依据 |
| --- | --- | --- |
| 多 Agent 读编排 | 已实现 | `agents/shopmind_multi_agent/graph.py`、`supervisor.py` |
| SSE/取消/生命周期 | 已实现 | `app/api/routes/chat_stream.py`、`app/runtime/streaming.py` |
| HITL 写确认 | 已实现 | `tools/cart.py`、`app/repositories/cart.py`、`chat_confirm.py` |
| 身份、所有权、幂等、治理 | 已实现 | `app/security/`、`app/governance/`、`app/runtime/` |
| 前端技术底座 | 已实现但未跟踪 | `frontend/package.json`、`frontend/src/api/` |

## 目标闭环的差距

1. **结构化商品事实**：无 Category、SKU、属性定义、inventory 数量或 sale status。
2. **结构化推荐**：无 `RecommendationResult`；最终 chat 与 SSE 只有文本和通用事件。
3. **安全 Action 视图**：无含 action type、expiry、version、editable schema 的公开模型。
4. **Cart 用例**：无 owner-bound REST、SKU upsert、唯一约束、可售验证。
5. **交易域**：无 checkout preview、ShopMind orders、库存预留、payment、outbox/inbox。
6. **前端业务视图**：无结构化卡片/比较/cart/checkout/orders；当前 UI 不应继续解析文本。
7. **量化推荐评估**：V6 catalog 证明运行时合约，不证明推荐质量或 Single/Multi 对照。
8. **部署**：当前 compose 不包含 Demo 运行时；RocketMQ Python SDK 尚未 spike。

## 优先级

Phase 1 只交付笔记本 SKU、结构化推荐和卡片数据。HITL 结构化视图、Cart、交易、MQ、支付依次
在后续阶段进行。RocketMQ 只有在独立 Spike 通过后才能绑定交易服务；PostgreSQL 永远是订单和库存
事实来源，Redis 只做协调/缓存。
