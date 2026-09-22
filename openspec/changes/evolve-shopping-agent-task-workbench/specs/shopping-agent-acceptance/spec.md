## Purpose

用可复现的业务场景、数据库事实和用户界面行为证明 Agent 工作台已经贯通，分开记录规则、模型替身、真实检索和真实模型结果，避免将组件存在、历史任务勾选或模拟指标误报为产品完成。

## ADDED Requirements

### Requirement: Scenario based acceptance catalog
交付 SHALL 包含至少 24 个独立固定任务案例：组合选购 10、兼容排查 6、售后 6、跨场景安全/恢复 2，并为每例保存输入、隔离数据、预期产物/状态/依据和允许副作用；另行覆盖必要负例和并发存储测试。

#### Scenario: Case result is reviewed
- **WHEN** 某案例被标记通过
- **THEN** 可以检查真实结果、关键规则、引用、计划/步骤与数据库副作用，不能仅凭 HTTP 200 或一段回答判定

#### Scenario: No solution is correct
- **WHEN** 固定候选数据确实没有满足要求的组合
- **THEN** 明确且范围准确的无解结果算该案例正确，不以任务必须推荐商品作为唯一成功标准

### Requirement: Real persistence and retrieval gates
交付 SHALL 运行隔离 PostgreSQL 的迁移、任务恢复、并发、动作原子性和真实片段检索门禁；模型替身和内存仓库不能替代这些验证。

#### Scenario: Restart gate
- **WHEN** worker 在完成部分步骤或失租后重启
- **THEN** 独立数据库会话验证完成产物复用、陈旧提交拒绝、预算不重置和动作不重复

#### Scenario: Real document retrieval
- **WHEN** 新任务执行证据查询
- **THEN** 使用实际索引片段及 PostgreSQL/pgvector/词法仓库，报告匹配与排除依据，不预置排名结果冒充检索

### Requirement: Actual model evidence is separate
系统 SHALL 为模型模式提供实际 Provider 调用与轨迹；真实外部调用须遵守授权，未执行时报告待验证，不能使用替身、固定计划或合成指标宣称真实模型能力完成。

#### Scenario: Authorized model acceptance
- **WHEN** 获得授权并进行模型验收
- **THEN** 每种任务至少保存一条去敏实际轨迹，包含模型/配置/Prompt/数据版本、计划、校验、使用量与业务结果，并覆盖一次合法局部修订

#### Scenario: External evidence unavailable
- **WHEN** 没有授权、凭据、额度或模型不可达
- **THEN** 继续独立工程验收并将真实模型项明确列为未完成，不编造成功率或把整个变更标为全部验收完成

### Requirement: Live user workflow and regressions
交付 SHALL 包含三个任务类型的真实前端/API/数据库验收，并通过既有购物推荐、身份、确认、订单和模拟支付回归；新任务可配置关闭且回滚不暴露撤销证据。

#### Scenario: Workbench live session
- **WHEN** 用户创建任务、补充条件、观察修订、刷新页面并确认动作
- **THEN** 页面展示真实状态和产物，刷新后恢复进展，数据库副作用符合预期且无重复

#### Scenario: Feature rollback
- **WHEN** 停止新任务准入并排空或取消 worker
- **THEN** 既有路径保持可用，已提交动作不丢失，历史数据不自动删除，证据撤销约束仍然成立

### Requirement: Honest implementation handoff
实施者 SHALL 交付场景与任务清单对应的验收报告、复现命令、实际工作区版本证据、运行说明及剩余限制，历史通过数不得替代本次结果。

#### Scenario: Final completion review
- **WHEN** 实施者准备声明变更完成
- **THEN** 所有要求有对应证据，未执行项仍未勾选，模型与工程完成状态分开，简历数字来自实际记录而非预设收益
