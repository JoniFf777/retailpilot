## Why

ShopMind 已经具备多 Agent、交易安全、运行时合同和确定性评测，也已经维护按商品关联的购物资料和退换货、保修、配送、兼容性等商城政策，但这些购物证据仍通过脚本入库，缺少业务元数据校验、版本发布、失败恢复和覆盖率管理。当前需要在不改变购物业务边界和既有 HITL/交易语义的前提下，吸收 Ragent 中成熟的工程化模式，形成服务购物决策而非通用企业知识库的可观测、可降级、可回滚 AI 平台能力。

## What Changes

- 新增分层运行时韧性：请求准入与公平限流、模型候选路由、首包超时、熔断、重试和显式降级结果。
- 将现有商品资料和商城政策的索引脚本升级为购物证据入库 Pipeline：Fetcher → Parser → Chunker → Enricher → Indexer；仅接收受信的商品说明、兼容性资料、选购指南和商城政策，并持久化任务、节点状态、版本与幂等事实。
- 将推荐证据检索整理为 `SearchChannel + PostProcessor` 扩展模型，按候选商品、品类、兼容组合和当前有效政策限制范围，保留当前向量/词法/RRF/Rerank 行为，并为图谱和联网检索预留默认关闭的扩展点。
- 新增服务端所有的 Prompt、Skill 和 MCP 注册目录；支持受信配置刷新、Schema 校验、权限/副作用分类和 Tool Gateway 适配。
- 新增面向管理员的购物证据覆盖率、失效政策、无效商品引用、入库任务、Prompt、Skill、模型健康与 Trace 控制台；默认只读，敏感变更继续经过认证、审计和明确写边界。
- 扩展生产预检与就绪检查，使新增依赖和降级状态具有机器可读、无敏感信息的健康结论。
- 保持 Product/RAG/Preference/Decision 多 Agent 拓扑、确定性 Planner、Catalog 事实源、PendingAction、购物车、订单、支付和 Outbox 语义不变。
- Catalog 继续拥有 SKU、价格、库存、结构化兼容约束和可售状态；订单/支付数据库继续拥有用户交易事实。文档只提供解释、指南和政策规则，冲突时不得覆盖结构化事实。
- RocketMQ 继续作为交易 Outbox 的可选发布端，不复用订单事件 Topic 驱动入库；文档 Pipeline 首阶段使用 PostgreSQL 租约/CAS，未来只有在规模证据充分时才单独设计 Topic、Consumer 和 Inbox。
- 所有新增远程依赖默认关闭；本地 PostgreSQL/pgvector 基线仍可运行，ES、图谱、联网搜索、远程 MCP 和外部观测平台不得成为核心购物链路的强制依赖。

## Capabilities

### New Capabilities

- `ai-runtime-resilience`: 分层准入限流、模型候选路由、首包探测、熔断、重试和显式降级合同。
- `knowledge-ingestion-pipeline`: 受信购物证据的业务分类、Catalog/政策元数据校验、解析、切块、增强、索引及任务恢复合同。
- `retrieval-extension-pipeline`: 候选商品、品类、兼容组合和有效政策范围内的检索通道、后处理、证据归因和可选外部检索合同。
- `agent-extension-registry`: Prompt、Skill、MCP 工具发现、校验、策略绑定和受控刷新合同。
- `ai-operations-console`: 购物证据覆盖/失效/冲突、模型健康、Trace、Prompt、Skill 和入库任务的管理员可视化合同。

### Modified Capabilities

- `release-readiness`: 新增 AI 平台依赖、注册表一致性、降级状态和可选后端的预检/就绪要求，同时保留核心本地基线。

## Impact

- 主要影响 `app/runtime/`、`app/recommendation/`、`app/repositories/`、`agents/shopmind_multi_agent/`、`data/documents/`、`scripts/`、`evaluation/`、`frontend/` 和 Alembic 迁移。
- 公共聊天、确认、推荐、购物车、订单和支付 API 保持向后兼容；新增能力优先通过内部合同和新的管理员 API 暴露。
- PostgreSQL 继续作为事实存储；Redis 仅用于显式选择的分布式协调/限流；其他检索或观测后端保持可选。
- 不提供任意企业文档库或普通用户上传入口；现有商品/政策语料通过兼容导入迁移到版本化购物证据模型。
- 新增配置必须由服务端拥有、默认安全关闭，并进入静态预检、实时就绪、确定性评测和故障注入验证。
- 实施按独立阶段推进，每阶段可单独回滚，不要求一次性复制 Ragent 的全部基础设施。
