## Purpose

定义由服务端控制且限定于购物决策与商城操作的 Prompt、Skill 与 MCP 扩展目录，使能力可以受控演进，同时继续服从 ShopMind 的 Agent 分工、权限、预算、HITL 和审计边界。

## ADDED Requirements

### Requirement: 扩展目录必须版本化并使用不可变快照
系统 SHALL 为 Prompt、Skill 和工具定义保存版本、启用状态、兼容性、购物能力类别、适用 Agent 和内容指纹；每次运行绑定一个不可变目录快照，刷新不得改变在途运行。

#### Scenario: 管理员发布新版本
- **WHEN** 新定义通过校验并被明确发布
- **THEN** 后续运行使用新快照，在途运行继续使用原快照

#### Scenario: 定义校验失败
- **WHEN** 定义存在重复名称、非法 Schema、未知工具或不兼容版本
- **THEN** 发布失败且当前活动快照不变

### Requirement: MCP 发现不得绕过 Tool Gateway
远程 MCP Server 地址、认证和允许的工具 MUST 由服务端配置。发现的工具 SHALL 经过名称、Schema、大小、超时、资源范围和副作用分类校验后，才能通过现有 Tool Gateway 注册。

#### Scenario: 发现只读工具
- **WHEN** 允许列表中的 MCP Server 返回合法只读工具
- **THEN** 系统以受限能力注册该工具并应用调用预算和审计

#### Scenario: 发现直接写工具
- **WHEN** MCP 工具会修改购物车、偏好、订单、支付或其他业务状态
- **THEN** 系统不得让 Agent 直接执行该写操作；支持的写意图必须映射到 Action Registry/HITL，否则拒绝注册

### Requirement: Skill 只提供受控指令和能力视图
Skill SHALL 是服务商品选购、商品比较、兼容性解释、政策问答或已注册商城动作的版本化说明、适用条件和允许工具集合，不得创建绕过 Supervisor 的隐藏 Agent，也不得扩大运行时策略。

#### Scenario: 加载 Skill
- **WHEN** 当前任务匹配一个启用 Skill
- **THEN** 系统加载有界说明并仅展示该 Skill 与基础策略共同允许的工具

#### Scenario: Skill 声明无关企业流程
- **WHEN** Skill 尝试引入人事、财务审批、任意数据库管理或其他非购物能力
- **THEN** Registry 拒绝发布并保持当前活动快照不变

### Requirement: Prompt 变更必须可回滚和可评测
活动 Prompt SHALL 具有稳定槽位、版本和回滚目标；发布前 MUST 通过适用的确定性合同评测，Prompt 不得改变公共 Schema 或安全策略。

#### Scenario: Prompt 候选未通过评测
- **WHEN** 候选 Prompt 破坏结构化输出、路由或安全基线
- **THEN** 系统拒绝激活并继续使用当前版本

### Requirement: 扩展不得改变业务事实所有权
Prompt、Skill 和 MCP 工具 SHALL 把 Catalog、结构化兼容规则、owner-scoped 交易数据和当前有效政策作为各自既定事实源。扩展不得通过提示词或工具结果覆盖价格、库存、订单、支付或 PendingAction 状态。

#### Scenario: MCP 返回不同库存
- **WHEN** MCP 工具返回的库存与 Catalog 不一致
- **THEN** 系统不得将该值写入推荐或交易合同，并记录稳定的事实冲突结果
