## Context

ShopMind 当前已经形成两条稳定主线：一条是 Supervisor/Planner 驱动的 Product、RAG、Preference、Decision 多 Agent 读链路；另一条是 PendingAction、Cart、Order、Payment、Outbox 组成的确定性交易链路。运行时已有 Harness、Tool Gateway、预算、重试、事件、轨迹回放、本地/Redis 协调、治理审计和发布就绪检查。

当前 `data/documents/` 已有 104 份按商品标识关联的商品资料和 5 份退换货、保修、配送、兼容性、支持政策，推荐证据路径也已按候选 product_id 和政策意图限制检索。因此本设计不是从零增加“文档功能”，而是把已有购物语料与检索升级为可靠的购物证据生命周期。现有概览仍声明旧的 25 份商品资料，部分指南含硬编码价格，政策元数据缺少完整生效范围，这些漂移正是需要治理的问题。

这次升级不复制 Ragent 的业务模型，也不把 ShopMind 改成单 ReAct Agent 或通用企业知识库。借鉴对象是其工程化组织方式：分层限流和模型韧性、购物证据入库 Pipeline、检索通道/后处理插件、Prompt/Skill/MCP 注册与运维后台。

## Goals / Non-Goals

**Goals:**

- 在不改变现有购物 API 和交易状态机的情况下，形成独立、可复用的 AI 平台层。
- 将模型故障从“异常处理”升级为有候选、有预算、有熔断、有显式状态的运行时合同。
- 将已有商品/政策索引脚本升级为可恢复、版本化、可观察且经过业务元数据校验的购物证据入库任务。
- 将现有推荐证据实现收敛为按候选商品、品类、兼容组合和有效政策限制范围的 Channel/PostProcessor 管线。
- 让 Prompt、Skill、MCP、Trace 和模型健康具有受控管理入口。
- 每个阶段默认关闭新增外部依赖，并能独立上线、回滚和评测。

**Non-Goals:**

- 不替换 ShopMind 的 Supervisor/专业 Agent/Decision Agent 拓扑。
- 不把价格、库存、SKU、购物车、订单或支付交给 RAG、MCP 或模型决定。
- 不引入任意代码执行或宣称 OS 级 Sandbox。
- 第一轮不强制引入 Elasticsearch、Milvus、LightRAG、对象存储、RocketMQ 或 Langfuse。
- 不允许动态 MCP 工具直接写业务状态；写操作仍必须进入 Action Registry 和 HITL。
- 不建设任意企业文档库，不允许普通用户通过聊天上传任意文档或 URL 进入证据库。
- 不使用文档中的价格、库存、可售状态、促销、订单或支付描述覆盖结构化事实。
- 不在同一变更中重做现有用户前台；管理员控制台单独分阶段交付。

## Decisions

### 1. 保留业务 Agent 编排，在其下增加 AI 平台层

目标结构：

```text
React / Public API
        |
        v
Harness + Supervisor + Planner
        |
        +--------------------+---------------------+
        |                    |                     |
   Product Agent        Preference Agent       RAG Agent
        |                    |                     |
     Catalog             Preferences       Shopping Evidence Retrieval
                                                   |
                                      Channels -> PostProcessors
                                                   |
                                             Evidence Result
        \____________________ Decision Agent ______/
                              |
                       PendingAction / HITL
                              |
                   Cart / Order / Payment / Outbox

Shared AI platform:
Admission + Model Gateway + Prompt/Skill/MCP Registry
+ Shopping Evidence Ingestion + Ops
```

AI 平台层提供能力，业务图仍拥有路由、计划、事实冲突处理和最终决策。RAG Agent 只消费证据结果，不获得交易写权限。

替代方案是直接采用单 ReAct Agent。该方案对开放式工具探索更灵活，但会削弱 ShopMind 已有的职责隔离、确定性计划和交易安全，因此拒绝。

### 2. 复用现有协调后端实现限流，不新建第二套 Redis 语义

在 `RuntimeCoordinationBackend` 现有租约、速率窗口和指纹键基础上增加 operation lane：chat、planner、model-provider、ingestion、retrieval-channel。默认仍是立即拒绝模式；公平有界等待作为显式可选模式，不能无限排队。

每个租约都必须有 TTL、唯一 token、续租和 compare-and-release。单机继续使用 local backend；多副本显式选择 Redis。配置失败保持 fail-closed，不静默退回单机。

替代方案是照搬 Ragent 的 Redis ZSET 队列。它能提供公平排队，但会与现有协调边界重复。第一阶段先扩展当前语义，只有真实流量证明需要排队时再增加 ZSET 实现。

### 3. 建立统一 Model Gateway，但不覆盖确定性策略

Model Gateway 按操作定义候选组，例如 `router`、`planner`、`decision`、`query-rewrite`、`answer-synthesis`、`rerank`。每个候选声明能力、首包/总时长、最大尝试、成本等级和健康状态。

候选状态采用 closed/open/half-open 熔断模型。只有在第一个客户端可见流事件之前，才允许透明切换候选；流已经开始后，上游失败必须终止并发出稳定错误事件，防止两份答案拼接。

所有尝试的 token、成本、耗时和失败类型进入现有 Harness 使用量与事件序列。模型不得扩大 RuntimePolicy。确定性 Router/Planner 仍是默认基线，LLM 方案继续经过 canonical validator。

### 4. 入库 Pipeline 只管理受信购物证据，并先使用 PostgreSQL 租约任务

证据模型限定为四类：

| 证据类型 | 允许内容 | 强制范围 | 业务用途 |
| --- | --- | --- | --- |
| Product Guide | 产品特点、适用人群、限制、安装和非实时说明 | product_id/SKU 或注册品类 | 解释候选为何适合 |
| Compatibility Evidence | 接口、协议、配件要求和组合说明 | 商品组合、品类或结构化规则引用 | 解释兼容结论 |
| Buying Guide | 参数含义、使用场景和选购权衡 | 注册品类 | 帮助理解筛选和比较 |
| Store Policy | 退换、保修、配送、价格保护和售后规则 | 政策类型、版本、生效期、地区、渠道 | 回答规则并提示风险 |

普通用户上传、任意网页抓取和未声明证据类型的资料不进入 Pipeline。第一阶段来源仅包括仓库受控语料、管理员提交的商城资料和服务端允许列表中的供应商资料。

定义五类节点合同：

```text
TrustedShoppingEvidenceSource
   -> Fetcher
   -> Parser
   -> Chunker
   -> Enricher
   -> Indexer
   -> Atomic Publish
```

任务、节点、证据版本和发布指针存入 PostgreSQL。Worker 使用租约/CAS 领取任务；节点输出使用内容指纹保证幂等。Enricher 必须校验 product_id、sku_code、category、policy_type、valid_from、valid_to、region/channel scope 和结构化兼容规则引用。新版本全部成功前，旧版本继续在线；失败、未生效和已失效版本永不进入当前检索。

第一阶段兼容导入现有 Markdown 商品/政策语料，并校验实际清单、概览声明、重复标识和 Catalog 悬空引用。Parser 可以对已规范 Markdown 使用 no-op，但 Enricher 的业务元数据校验不能跳过。对象存储、OCR、PDF SaaS 和 MQ 只作为后续适配器，不进入核心依赖。

现有 RocketMQ 只承担订单创建、取消、过期和支付成功等交易 Outbox 事件的可选发布，目前没有 Consumer/Inbox。不得复用 `shopmind-order-events-v1` Topic 驱动入库。替代方案是新建 Pipeline Topic 和消费者，但当前证据规模不足以证明新增消费幂等、Inbox、背压和部署成本；PostgreSQL 任务队列更符合现有最小运行基线。未来若有规模证据，另行设计独立 Topic、Consumer 和 Inbox。

### 5. 用 Channel/PostProcessor 重构购物证据链，结构化事实不成为文档检索通道

现有向量和词法逻辑先适配到统一 `SearchChannel` 合同；候选携带 channel、evidence_type、document/version、product/category/policy scope、score、latency 和安全元数据。所有通道共享一次请求级预算和范围解析结果。

后处理顺序固定为：

```text
Normalize -> Deduplicate -> RRF Fusion -> Candidate Limit
          -> Optional Rerank -> Scope/Version Filter
          -> Evidence Gate -> Citation Projection
```

检索路由必须符合购物场景：Product Guide 只查询确定性 Top-K 候选；Buying Guide 只查询当前品类；Compatibility Evidence 只围绕候选组合并服从结构化兼容规则；Store Policy 只查询当前生效且适用地区/渠道/商品范围的版本。图谱和联网搜索仅预留接口，默认关闭。联网结果不得直接形成价格、库存或 SKU 事实。Catalog 查询仍由 Product/Recommendation 领域层负责，不注册为 RAG Channel，以免模糊交易事实和文档证据。

具体订单资格问答必须组合 owner-scoped 订单事实与当前政策规则；如果缺少订单事实，只能解释规则，不能宣称该用户具有退货、保修或取消资格。

### 6. 事实权威矩阵固定，任何扩展不得改变优先级

| 事实 | 权威来源 | 文档作用 |
| --- | --- | --- |
| SKU、价格、库存、可售状态 | Catalog | 不得覆盖，只能提供非实时说明 |
| 硬兼容约束 | 结构化品类/兼容规则 | 解释原因，不得推翻 |
| 用户偏好 | Preference/Memory 边界 | 不得从公共文档推断 |
| 购物车、订单、支付 | owner-scoped 交易数据库 | 不得作为文档事实 |
| 退换、保修、配送规则 | 当前有效 Store Policy | 提供规则与引用 |
| 商品用途、限制、操作说明 | 受信 Product/Buying Guide | 提供解释性证据 |

冲突处理发生在确定性边界：结构化事实胜出，冲突文档被排除或标记非权威，不交给 LLM 自由裁决。

### 7. Prompt、Skill、MCP 使用同一个版本化 Extension Registry

Registry 保存定义、版本、启用状态、兼容性、策略元数据和内容指纹。每个运行取得不可变快照；刷新仅影响新运行。

- Prompt：按稳定 slot 管理，发布前运行对应合同评测，可回滚。
- Skill：只允许商品选购、比较、兼容解释、政策问答和已注册商城动作，由说明、适用条件和允许工具组成，只缩小能力视图，不能放宽策略。
- MCP：服务端配置 endpoint/认证/allowlist；发现结果必须经过 Schema、大小、超时、副作用和资源范围校验，再包装为 Tool Gateway capability。

MCP 写工具只有两种结果：映射为已注册 Action Definition，或拒绝注册。不能因为远端声明 `readOnlyHint=false` 就自动获得写权限。

### 8. 运维后台与消费者前台分离

新增 `/admin/ai/*` 管理域和前端 `/admin/ai` 路由，不混入购物工作台。第一阶段只读展示模型健康、运行分类、入库任务、检索归因、Registry 版本，以及按商品/SKU/品类/政策类型聚合的证据覆盖、失效版本、悬空 Catalog 引用和语料概览漂移。

由于现有 owner identity 不等于管理员 RBAC，管理 API 在管理员授权适配器完成前默认关闭。管理写操作后续单独启用，并要求版本检查与治理审计。

Trace 默认只展示阶段、状态、耗时、token/成本区间和安全分类；不返回完整用户消息、Prompt、工具参数、文档正文、凭据或签名。

### 9. 显式采用“可选依赖不影响核心，启用依赖必须真实就绪”原则

每个能力具有 `disabled / ready / degraded / not_ready` 状态：

- 未启用的图谱、联网、远程 MCP、外部 Trace 不影响核心 readiness。
- 启用但无健康候选的必需模型组使对应能力 not-ready。
- 可选 reranker 故障允许 retrieval degraded，但不能伪造 rerank 成功。
- PostgreSQL/Catalog 不可用时整个购物服务不接流量，外部搜索不能顶替。
- 可选 RocketMQ Publisher 未启用不阻断购物或证据服务；Outbox backlog 由独立健康报告呈现。

静态 preflight 校验配置关系，live readiness 验证必要依赖，service health 反映运行质量，release operation 只消费这些封闭报告。

## Data and Contract Boundaries

建议新增或扩展的数据集合：

- shopping evidence pipeline、task、task node、evidence version、业务范围元数据和 active publication；
- prompt/skill/MCP definition、version 和 active pointer；
- 模型尝试与通道归因优先复用现有 AgentEvent/Run persistence，只增加封闭安全字段；
- 熔断状态默认进程/Redis 临时保存，不作为业务事实；
- 管理审计复用 GovernanceAuditRecord，不保存定义正文和秘密。

公共 Chat、SSE、Confirm、Recommendation、Cart、Order、Payment 合同不删除字段、不改变状态语义。新增降级信息优先以可选字段和事件提供。

## Implementation Phases

### Phase 0: 基线与合同冻结

- 固化现有 public API、Agent 拓扑、Catalog/RAG 事实边界和 HITL 回归。
- 建立故障分类、能力状态、模型候选与检索候选的 Pydantic 合同。
- 增加架构守卫，禁止 MCP/Skill 直接注册业务 writer。
- 记录现有商品/政策语料实际清单，修正 25/104 等概览漂移，并建立 Catalog 引用与动态事实冲突基线。

验收：现有全量测试和 V6 catalog 不变；新增合同可在无模型、无网络下测试。

### Phase 1: Admission 与 Model Gateway

- 在现有协调后端增加 operation lane 和有界准入。
- 实现候选选择、首包/总时长、熔断和 attempt accounting。
- 先接入一个低风险操作，再逐步覆盖 planner/decision/rewrite。

验收：故障注入覆盖首包超时、空响应、协议错误、熔断、半开恢复、预算耗尽和流开始后失败。

### Phase 2: Shopping Evidence Ingestion Pipeline

- 建立迁移、Repository、节点合同、Worker 和原子发布。
- 用当前 Product Guide 和 Store Policy Markdown 做第一组 Adapter，并补齐四类证据元数据。
- 提供 CLI 与只读状态 API，保留旧索引脚本作为受控兼容入口。

验收：重复提交、节点重试、进程重启、旧版本保留、删除、部分失败、悬空商品引用、政策有效期和语料清单漂移均有 PostgreSQL 集成测试。

### Phase 3: Shopping Evidence Channel/PostProcessor

- 将当前向量/词法/RRF/Rerank 迁入新合同，先做等价性测试。
- 增加通道超时、归因、证据闸门和显式降级。
- 图谱/联网仅提供 fake adapter 和默认关闭配置，不急于接真实供应商。

验收：旧/新实现对固定语料结果等价；单通道故障不丢成功结果；跨商品证据不泄漏；过期政策不返回；Catalog/结构化兼容规则冲突始终以结构化事实为准。

### Phase 4: Extension Registry

- 先实现 Prompt 版本与回滚，再实现 Skill，最后实现 MCP discovery。
- MCP 先支持只读工具；写工具映射在后续独立变更中逐个审核。
- Registry 快照进入运行事件和评测 artifact。

验收：非法 Schema、目录刷新竞态、未知工具、策略扩大和远端超时全部 fail-closed。

### Phase 5: AI Operations Console

- 完成管理员身份边界后开放只读 API 与 React 页面。
- 展示模型健康、购物证据覆盖/失效/冲突、入库、检索归因、Registry 和 Trace 摘要。
- 管理写操作另设开关、版本控制、审计和回滚。

验收：普通用户不可枚举管理资源；响应无正文/凭据；分页和时间窗口有硬上限。

### Phase 6: 可选高级后端

- 依据真实质量数据决定是否接入 ES、图谱、联网检索、对象存储或外部观测。
- 每次只引入一个后端，并提供离线等价测试、live readiness 和独立回滚。

## Risks / Trade-offs

- [平台抽象过早导致代码量上升] → 每阶段先迁移一个真实调用点，并要求等价性证据后再扩展。
- [动态扩展扩大攻击面] → 服务端 allowlist、不可变快照、Schema/大小/超时校验和 Tool Gateway 双重约束。
- [多候选重试增加成本] → 所有尝试共享预算并计量失败用量，默认尝试数保持小且按操作配置。
- [首包切换产生重复输出] → 仅在第一个客户端可见事件前允许透明切换。
- [入库重试生成重复块] → 内容指纹、节点幂等键、版本发布指针和事务 CAS。
- [商品文档复制价格/库存后迅速过期] → 入库标记动态字段非权威，输出投影只从 Catalog 获取结构化值。
- [政策文档与具体订单资格混淆] → 政策只提供规则，资格结论必须组合 owner-scoped 订单事实。
- [兼容性文档与硬规则冲突] → 结构化兼容规则优先，文档只解释且冲突证据被排除。
- [可选依赖拖垮本地体验] → 全部默认关闭；PostgreSQL/pgvector 保持唯一核心开发依赖。
- [后台暴露 PII 或 Prompt 秘密] → 默认元数据视图、固定字段白名单、指纹关联和有界查询。
- [一次性迁移影响现有推荐质量] → 新旧检索并行 shadow/equivalence，达到基线后再切换，保留快速回退开关。

## Migration Plan

1. 仅合入合同、现有语料清单/业务元数据审计、Fake、评测和配置默认值，不改变运行路径。
2. 先把现有 Product/Policy Markdown 以兼容方式导入购物证据模型，再按 Phase 1–4 分别以 default-off 或 shadow 模式部署。
3. 每阶段先在确定性测试和隔离 PostgreSQL 中验证，再启用单一调用点。
4. readiness、health、SLO 和 release gate 稳定后逐步扩大流量。
5. 回滚时关闭对应能力开关并恢复旧 Adapter/旧活动证据指针；数据库迁移优先保持向后兼容，旧列/表不在同一版本删除。
6. 控制台和高级后端在核心链路稳定后单独发布。

## Open Questions

- 公平等待队列只有在真实并发数据证明立即拒绝影响体验后再选择 Redis ZSET；不影响前五个阶段。
- 第一种真实高级检索通道由离线 Recall/MRR、延迟和成本数据决定，不预先指定图谱或联网搜索。
- 文档二进制对象存储在出现 PDF/图片等需求前保持可插拔，不成为本次基线依赖。
