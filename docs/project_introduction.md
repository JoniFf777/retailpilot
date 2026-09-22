# RetailPilot / ShopMind 项目完整介绍

> 更新时间：2026-09-17
>
> 当前正式发布版本仍是 `v3.0.0`；本文同时描述工作区中尚未形成新 Release 的后续实现。

ShopMind 是一个面向中文消费电子选购的全栈 Agent Engineering 项目。它把自然语言需求转换为可解释、可追溯的 SKU 推荐，再通过用户确认衔接购物车、结算、订单、库存预占、模拟支付和事务 Outbox。

项目重点不是“让大模型自动购物”，而是研究怎样把不确定的 Agent 推理安全地接入价格、库存、订单和支付这些确定性业务系统。

兼容测试标识：`SKU-level commerce path`。

## 1. 产品能力

用户可以输入预算、品类、配置和使用场景。系统会：

1. 识别品类并把中文需求转换成结构化约束；
2. 从 Catalog 读取真实商品、SKU、价格、库存和可售状态；
3. 用确定性规则执行硬约束过滤、偏好排序和分项评分；
4. 从商品说明、兼容性资料、选购指南和商城政策中补充证据；
5. 返回最多 3 个 SKU 推荐、差异、解释和引用；
6. 在用户选择后创建 `PendingAction`，明确确认后才写入购物车；
7. 继续完成 Checkout Preview、创建订单、库存预占和 Mock Payment。

读 Agent 不持有购物车、订单或支付写权限。推荐结果只负责提出候选，所有副作用都要经过明确的业务 API、owner 校验和状态机。

## 2. 多轮购物状态

系统不会在每轮对话中重新猜测完整历史，而是保存 owner/thread 隔离的 `ShoppingSessionState`：

- 本轮只 patch 明确出现的预算和属性；
- 显式清空的字段不会从历史消息中恢复；
- 切换品类时重建品类属性；
- 候选序号会过期，避免“第二个”指向已经变化的列表；
- 单调版本与数据库 CAS 阻止旧请求覆盖新状态；
- 有界 patch history 不保存完整聊天正文。

## 3. 多 Agent 与推荐架构

当前主要只读角色包括：

| 角色 | 职责 |
| --- | --- |
| Supervisor | 识别意图并选择读取任务，不持有业务工具 |
| Product Agent | 查询商品、SKU、价格和库存 |
| RAG Agent | 查询商品说明和商城政策 |
| Preference Agent | 读取用户已确认偏好 |
| Decision Agent | 汇总结构化结果，不执行写操作 |

默认关键路径可以确定性运行。LLM Router/Planner 是服务端显式配置的可选能力，输出必须对照结构化合同和 canonical plan 校验。

结构化推荐使用 `RecommendationTaskPlan/Result` 描述 Catalog、Preference、Ranking、Evidence 和 Decision 五个阶段。Category Schema 覆盖 10 类消费电子，定义属性类型、单位、合法范围、硬软约束、缺失值语义和展示方式。

## 4. 购物证据平台

最新工作区把原有脚本式文档索引升级为受信购物证据生命周期。只接收 Product Guide、Compatibility Evidence、Buying Guide 和 Store Policy。

入库执行：

```text
Fetcher → Parser → Chunker → Enricher → Indexer
```

证据版本、任务、节点和活动发布指针持久化在 PostgreSQL。内容指纹、幂等键、租约和节点 CAS 支持失败恢复；只有完整成功后才切换活动版本，旧版本在此之前继续可见。商品、SKU、品类、政策类型、地区、渠道和有效期都会校验。

文档中的价格、库存、订单和支付信息属于非权威信息，不能覆盖 Catalog 或 owner-scoped 交易数据。

项目已经实现 `SearchChannel + PostProcessor` 扩展合同，包括 Vector、Lexical、Normalize、Deduplicate、RRF、CandidateLimit、可选 Rerank、Evidence Gate 和 Citation Projection。当前默认 RAG 兼容路径只复用了公共 RRF；完整 Pipeline 仍用于独立测试和可选/Shadow 接入。图谱和联网检索尚未接入真实后端。

## 5. Agent Runtime 与模型韧性

V4-V6 Runtime 提供：

- 统一 Harness 生命周期和 Run/Event 持久化；
- Memory/Context 选择与 owner 隔离；
- JSON 与 POST SSE 共用的顺序事件；
- Idempotency-Key、截止时间、取消、步骤/工具/token/cost 预算；
- Tool Gateway 的 Schema、Agent allowlist、owner、资源和副作用策略；
- 有界并行 Specialist、重试和本地/HTTP Adapter；
- local/Redis 协调、限流、去重和缓存；
- trajectory replay、确定性评测和发布门禁。

Chat/Confirm 已使用 global、operation、subject 三层 AI Admission。Model Gateway 已实现服务端候选组、首包前切换、故障分类、共享预算和 closed/open/half-open 熔断，并提供 Harness attempt 观测 Adapter；它尚未全面接管默认 Agent/Planner 的全部模型调用。

## 6. Prompt、Skill、MCP 与 AI Operations

Prompt、Skill、MCP 共用版本化 Extension Registry：

- Prompt 使用稳定 slot 和内置安全回退；
- Skill 只服务购物、比较、兼容解释、政策问答和已注册商城动作，并且只能缩小权限；
- MCP 发现受 HTTPS、host allowlist、Schema、大小和超时限制；
- 只读购物工具才能包装成 Tool Gateway capability；写能力必须拒绝或映射为显式 Action Definition。

默认业务路径仍使用内置 Prompt 和已有工具注册。远程 MCP 和动态 Skill 没有进入核心购物流量。

`/admin/ai` 默认关闭，并使用独立管理员授权。后端支持模型健康、证据列表/覆盖率、任务状态、带 expected-version 的扩展发布/证据撤销和 payload-free Trace 投影；当前 React 页面主要展示健康、证据和任务摘要。

## 7. 交易工程

- SKU Inventory 是价格和库存真值；
- 购物车按 owner/SKU 隔离，并使用版本处理陈旧更新；
- Checkout Preview 生成带 owner、Cart/价格指纹和有效期的签名快照；
- Order 创建使用 `Idempotency-Key + request hash` 支持相同请求重放；
- PostgreSQL 行锁、稳定 SKU 锁顺序和条件更新防止超卖；
- 下单预占库存，支付成功后消耗，取消或超时释放；
- Payment Provider 调用发生在事务外，避免网络等待长期持锁；
- 持久化 `provider_succeeded` 支持渠道成功、本地提交失败后的恢复；
- Order/Payment 状态与版本化 Outbox 事件在同一事务提交。

## 8. RocketMQ 边界

RocketMQ 是可选的交易 Outbox Publisher，不是 API、Core Demo 或证据入库的必需依赖。

Outbox worker 使用租约、`FOR UPDATE SKIP LOCKED`、CAS、退避重试、dead-letter 和 redrive。交付语义是 at-least-once；Broker 已接收但本地完成标记丢失时会重复发送。Consumer、Inbox 和消费端去重尚未实现。

购物证据 Pipeline 使用 PostgreSQL 租约/CAS，不复用订单 Topic、SDK、Broker 或 Publisher Worker。

## 9. 身份、治理与运维

- 开发环境兼容 body user；生产参考模式支持 trusted header 和 signed header；
- signed header 使用时间戳、nonce、HMAC-SHA256 与 local/Redis 一次性 claim 防重放；
- owner-data API 支持本人数据盘点、Memory 更正/删除和明确确认的完整删除；
- Governance Audit 只保存 fingerprint 和封闭元数据，不保存原始消息、凭据或任意 payload；
- production preflight、live readiness、service metrics/SLO、发布/回滚/事故检查有独立合同；
- Correlation ID、PII-safe JSON 日志和状态迁移日志用于故障定位。

这些是生产参考能力，不代表系统已经承载真实生产流量。

## 10. 验证体系

默认测试不依赖真实模型。验证覆盖：

- 纯函数、API 和 Repository 合同；
- 真实 PostgreSQL 迁移、锁、事务、并发和回滚；
- 真实 Redis 原子协调；
- Vitest、mocked Playwright 和本地 live 浏览器链路；
- Planner、trajectory、Adapter、Action、Resilience、Governance 和 Release gates；
- 购物证据范围、政策有效期、Catalog 冲突、检索等价性和 AI 平台回滚门禁。

仓库最新全量后端回归为 `978 passed, 68 skipped`；任务 PostgreSQL 专项 `7/7`、生产/回滚专项 `30/30`、前端 Vitest `154/154`。历史 PostgreSQL/Redis 与 V3 API handoff 批次仍有效；这些批次存在重叠，不能相加成独立用例数。

20 条合成需求和 12 条合成检索只证明合同回归，不代表真实线上推荐质量。当前没有可对外宣称的 CTR、转化率、模型收益或 SLA。

## 11. 运行项目

- `docs/development.md`：开发和验证命令；
- `docs/demo_runbook.md`：Core Demo Prepare/Start/Verify；
- `docs/shopmind_directory_structure_guide.md`：代码阅读路径；
- `docs/interview_architecture_overview.md`：秋招架构、完整业务流程和问答入口；
- `docs/documentation_index.md`：当前文档与历史资料分类。

受跟踪文档不包含开发者本机绝对路径或密钥。机器状态放在被 Git 忽略的 `.local/`。

## 12. 明确边界

- 支付是 Mock Provider，不包含真实银行卡、退款、webhook 或自动对账；
- Agent 默认在同一后端进程内协作，不是已上线微服务集群；
- SSE 主要传递生命周期事件，不是完整逐 token 输出；
- RocketMQ 只有可选 Publisher，Consumer/Inbox 未实现；
- 图谱、联网搜索、远程 MCP、ES 和对象存储不是当前核心路径；
- LangSmith 是显式启用的实验旁路，不是默认依赖；
- 工作区后续实现尚未形成新正式 Release 或部署。
