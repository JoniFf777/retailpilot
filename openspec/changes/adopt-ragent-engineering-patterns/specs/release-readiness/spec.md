## ADDED Requirements

### Requirement: AI 平台能力必须进入预检和就绪判断
静态预检 SHALL 校验已启用模型候选、购物证据类型、Catalog/政策元数据引用、检索通道、Pipeline 节点和扩展注册表的关系；实时就绪 SHALL 仅探测显式启用且为当前流量所需的依赖，并返回无敏感信息的稳定检查结果。

#### Scenario: 可选能力保持关闭
- **WHEN** 图谱、联网检索、远程 MCP 或外部观测后端未启用
- **THEN** 就绪检查将其报告为 disabled 或 not-applicable，核心 ShopMind 服务仍可 ready

#### Scenario: 必需候选全部不可用
- **WHEN** 某个已启用操作没有任何健康且能力匹配的模型候选
- **THEN** 就绪结果为非 ready，并给出稳定候选组错误分类而不暴露端点或凭据

#### Scenario: 注册表不一致
- **WHEN** 活动 Prompt、Skill、MCP 或 Pipeline 定义引用不存在或不兼容的资源
- **THEN** 静态预检失败，服务不得宣称对应能力可用

#### Scenario: 购物证据引用不存在的商品
- **WHEN** 活动商品证据引用未知 product_id、sku_code 或未注册品类
- **THEN** 证据能力预检失败并报告有界引用错误，Catalog 和交易数据保持不变

#### Scenario: 当前政策没有有效版本
- **WHEN** 已启用政策问答所需的政策类型不存在当前生效版本
- **THEN** 对应政策能力为 degraded 或 not-ready，系统不得回退到已失效版本并伪装为当前规则

### Requirement: 降级状态必须与发布决策一致
发布和运行健康报告 SHALL 区分可服务的降级与不可接流量的故障；离线发布检查 MUST 使用同一封闭状态集合，不得根据原始异常文本做决策。

#### Scenario: 可选重排器降级
- **WHEN** 基础检索可用但可选重排器不可用
- **THEN** 服务可保持 ready，同时健康报告明确标记检索降级

#### Scenario: 核心事实存储不可用
- **WHEN** PostgreSQL/Catalog 事实存储不可用
- **THEN** 服务为非 ready，模型或网页检索不得作为替代事实源

#### Scenario: 可选 RocketMQ 未启用
- **WHEN** 交易 Outbox Publisher、RocketMQ SDK 或 Broker 未启用
- **THEN** 核心购物和购物证据服务仍可 ready，Outbox 健康独立报告 disabled 或 backlog 状态
