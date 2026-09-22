## 1. 基线与架构边界

- [x] 1.1 为现有 Agent 拓扑、公共 API、Catalog 事实源和 HITL 写入边界补充静态架构守卫
- [x] 1.2 定义统一的能力状态、故障分类、候选模型、模型尝试和检索候选 Pydantic 合同
- [x] 1.3 为新增合同建立无模型、无网络的序列化与负向单元测试
- [x] 1.4 将现有全量测试、V6 catalog、推荐质量、实际商品/政策语料清单和 Catalog 引用记录为迁移前验收基线
- [x] 1.5 增加服务端默认关闭配置，并验证客户端不能选择 provider、endpoint、预算或扩展目录
- [x] 1.6 增加事实权威架构守卫，确保价格/库存/SKU 来自 Catalog、硬兼容来自结构化规则、订单/支付来自 owner-scoped 交易数据

## 2. 分层准入与 Model Gateway

- [x] 2.1 为现有 RuntimeCoordinationBackend 增加 operation lane 合同和本地实现
- [x] 2.2 为 Redis 后端实现等价的指纹键、租约、TTL、续租和 compare-and-release 语义
- [x] 2.3 增加 global、operation 和 subject 维度的并发/速率配置校验
- [x] 2.4 实现模型候选组、能力匹配和服务端选择策略
- [x] 2.5 实现连接、首包、总时长、空响应和协议错误的封闭分类
- [x] 2.6 实现 closed/open/half-open 熔断与受控恢复探测
- [x] 2.7 实现首个客户端可见事件之前的候选切换，并禁止流开始后的透明拼接
- [x] 2.8 将所有成功/失败尝试的 usage、latency 和状态接入 Harness/Event 持久化
- [x] 2.9 先用一个低风险模型操作完成 Gateway 适配和旧路径等价性测试
- [x] 2.10 增加限流、候选耗尽、熔断、取消和共享预算的确定性故障注入评测

## 3. 购物证据入库 Pipeline

- [x] 3.1 定义 Product Guide、Compatibility Evidence、Buying Guide 和 Store Policy 四类购物证据合同
- [x] 3.2 设计并迁移 pipeline、task、task-node、evidence-version、业务范围元数据和 active-publication 表
- [x] 3.3 实现 Repository 的幂等创建、租约领取、节点 CAS、重试和终态转换
- [x] 3.4 定义 Fetcher、Parser、Chunker、Enricher、Indexer 节点接口与有界结果合同
- [x] 3.5 为当前商品/政策 Markdown 和管理员受信直接文本来源实现第一组节点 Adapter
- [x] 3.6 实现 product_id、sku_code、category、policy_type、有效期、地区/渠道和兼容规则引用校验
- [x] 3.7 实现动态价格、库存、促销、订单和支付字段的非权威标记与输出隔离
- [x] 3.8 实现内容指纹、节点幂等键和失败后安全恢复
- [x] 3.9 实现新版本原子发布、旧版本持续可见及未生效/已失效政策隔离
- [x] 3.10 实现证据撤销/删除及索引清理，不影响其他商品或政策
- [x] 3.11 增加文件类型、大小、页数、块数、时长、增强预算和受信来源限制
- [x] 3.12 实现现有 104 份商品资料与 5 份政策的清单审计、概览漂移检测和兼容导入
- [x] 3.13 提供 Pipeline CLI、只读状态 API 和旧索引脚本的兼容入口
- [x] 3.14 增加真实 PostgreSQL 的重复提交、崩溃恢复、悬空商品引用、政策有效期、旧版本保留和删除集成测试
- [x] 3.15 保持 RocketMQ 仅用于交易 Outbox，并验证 Pipeline 不依赖订单 Topic、SDK、Broker 或现有 Publisher Worker

## 4. 购物证据 Retrieval Channel 与 PostProcessor

- [x] 4.1 定义包含 evidence_type、商品/品类/兼容组合/政策范围的 SearchRequest、SearchChannelResult、EvidenceCandidate 和归因合同
- [x] 4.2 将现有向量检索适配为 VectorSearchChannel
- [x] 4.3 将现有词法检索适配为 LexicalSearchChannel
- [x] 4.4 实现共享范围、请求级预算、并行 fan-out 和单通道超时
- [x] 4.5 实现 Normalize、Deduplicate、RRF 和 CandidateLimit 处理器
- [x] 4.6 适配现有 lexical/CrossEncoder reranker，并校验只能重排可信候选子集
- [x] 4.7 实现候选商品、品类、兼容组合、政策有效期/地区/渠道过滤、EvidenceGate 和 CitationProjection
- [x] 4.8 增加图谱与联网搜索 Fake Channel 及默认关闭的配置/就绪语义
- [x] 4.9 为旧/新检索路径建立固定语料 shadow/equivalence gate
- [x] 4.10 增加商品 A/B 跨范围泄漏、未入选商品证据和无关政策污染测试
- [x] 4.11 增加文档价格/库存与 Catalog 冲突、兼容文档与结构化硬规则冲突测试
- [x] 4.12 增加过期政策、无当前政策和具体订单资格必须组合 owner-scoped 交易事实的测试
- [x] 4.13 以候选商品命中、品类范围、政策当前版本、兼容组合、引用有效性和动态事实冲突建立业务检索评测

## 5. Prompt、Skill 与 MCP Extension Registry

- [x] 5.1 设计并迁移定义、版本、活动指针和兼容性元数据表
- [x] 5.2 实现 Registry 校验、不可变运行快照、内容指纹和并发发布/回滚
- [x] 5.3 将现有代码 Prompt 映射为稳定 slot，并保留内置安全回退
- [x] 5.4 为 Prompt 发布接入适用的确定性评测门禁
- [x] 5.5 实现 Skill 定义、适用条件和只缩小权限的工具视图
- [x] 5.6 限定 Skill 为商品选购、比较、兼容解释、政策问答和已注册商城动作，并拒绝无关企业流程
- [x] 5.7 实现 MCP Server 服务端配置、发现、Schema/大小/超时/allowlist 校验
- [x] 5.8 将通过校验的购物只读 MCP 工具包装为 Tool Gateway capability
- [x] 5.9 增加写工具拒绝或显式 Action Definition 映射守卫
- [x] 5.10 增加 MCP/Skill 返回价格、库存或交易状态冲突时的事实隔离测试
- [x] 5.11 增加刷新竞态、非法 Schema、未知工具、策略扩大和远端故障测试

## 6. AI Operations Console

- [x] 6.1 定义独立管理员授权适配器，并在未配置时关闭全部管理 API
- [x] 6.2 实现模型健康、熔断、限流和运行分类的有界只读 API
- [x] 6.3 实现入库任务、检索归因、Registry 版本和按商品/SKU/品类/政策类型证据覆盖率的分页只读 API
- [x] 6.4 实现不含正文、Prompt、工具参数、凭据和原始身份的 Trace 投影
- [x] 6.5 在 React 中增加独立 `/admin/ai` 路由和只读页面
- [x] 6.6 为发布、回滚、启停和重试操作增加 expected-version 与治理审计
- [x] 6.7 展示失效政策、悬空 Catalog 引用、缺失证据和语料概览漂移，不展示用户交易数据
- [x] 6.8 增加普通用户拒绝、资源不可枚举、分页上限和敏感字段缺失测试

## 7. Readiness、评测与渐进发布

- [x] 7.1 扩展静态 preflight，校验候选组、四类购物证据、Catalog/政策元数据、Pipeline、Channel 和 Registry 关系
- [x] 7.2 扩展 live readiness，仅探测已启用且为当前流量必需的依赖
- [x] 7.3 扩展 service health/SLO，区分 disabled、ready、degraded 和 not-ready
- [x] 7.4 扩展 release operation gate，使其使用同一封闭能力状态集合
- [x] 7.5 为新增能力建立含购物证据范围/有效期/事实冲突案例的离线 catalog suite、accepted baseline 和故障轨迹回放
- [x] 7.6 运行 focused、full、PostgreSQL、Redis、smoke、frontend 和 release 验证矩阵
- [x] 7.7 更新语料概览、architecture、runtime design、development、project status、RocketMQ 边界和购物证据运维文档
- [x] 7.8 按 Phase 1–5 分别以 default-off/shadow 模式启用并记录独立回滚证据
- [x] 7.9 基于真实 Recall/MRR、延迟、成本和流量数据决定是否另提 ES、图谱、联网搜索或对象存储变更
