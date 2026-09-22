## Purpose

让新购物任务从真实受信资料中取得范围一致、版本有效、来源可追溯的证据，并将必需业务校验与可选相关性优化分开，避免过期、撤销或无关资料污染方案和售后判断。

## ADDED Requirements

### Requirement: Shared immutable retrieval scope
系统 SHALL 将每个原问题、子问题与同源业务范围绑定，向量与词法通道共用商品、SKU、品类、兼容组合、政策和有效期条件；模型改写不得扩大该范围。

#### Scenario: Query rewrite preserves product identity
- **WHEN** 模型改写商品 A 的查询时生成了商品 B 的标识或扩大地区范围
- **THEN** 系统拒绝扩大范围并保留原问题/合法范围，不返回越界证据

#### Scenario: Missing scope metadata
- **WHEN** 一条看似相关片段缺少限定查询所必需的型号/范围元数据
- **THEN** 新任务不将它作为该商品的可信证据，不能靠返回时补写请求类型伪造来源

### Requirement: Real hybrid retrieval with bounded failures
系统 SHALL 在新任务路径执行真实资料的向量与词法检索，融合独立通道排名并保留归因；最多 3 个子问题和一次有针对性的补查，遵守共享截止时间与候选上限。

#### Scenario: One optional channel times out
- **WHEN** 一个通道超时但另一个返回业务校验通过的证据
- **THEN** 系统在总时间限制内返回受限结果和 degraded 状态，区分超时与正常空命中

#### Scenario: All channels unavailable
- **WHEN** 所有必要检索均失败
- **THEN** 返回证据不可用状态，涉及必要证据的肯定结论不能通过，纯 Catalog 结果按业务合同保留

### Requirement: Mandatory gates fail closed
系统 SHALL 在引用前检查来源身份、业务范围、活动版本和政策适用性；必需检查失败不能被通用后处理异常兜底跳过，可选重排失败才允许保留已校验候选。

#### Scenario: Scope validator fails
- **WHEN** 商品范围或政策有效期检查抛出错误
- **THEN** 不返回未经检查的片段作为可信引用，并记录稳定的验证不可用原因

#### Scenario: Reranker fabricates a document
- **WHEN** 重排器返回原可信候选集合以外的 ID 或篡改文档内容
- **THEN** 拒绝该重排输出，保留原可信内容并标记降级，不引入新文档

### Requirement: Atomic publication and revocation visibility
系统 SHALL 仅向新任务检索暴露当前已发布且未撤销的片段；新版本失败不得影响旧发布版本，撤销提交后开始的查询必须不再返回撤销版本。

#### Scenario: New indexing fails midway
- **WHEN** 新证据版本的片段写入或嵌入处理失败
- **THEN** 新版本保持不可查询，旧发布版本完整可见，不出现新旧片段混合

#### Scenario: Revoke before a new query
- **WHEN** 证据版本撤销已提交后用户发起新的任务查询
- **THEN** 即使旧物理片段尚未清理，查询也不能将其作为活动证据返回

#### Scenario: Revoke after proposal before confirmation
- **WHEN** 已展示方案的重要引用在确认动作前被撤销
- **THEN** 引用标记失效，动作要求重新验证/预览，不直接使用旧 pass 结果写入

### Requirement: Fact authority and citation projection
系统 SHALL 保留商品数据库和本人订单事实的权威性，引用关联实际证据 ID/版本和子问题；用户可见结果不得泄露原始 Prompt、凭据或其他用户数据。

#### Scenario: Document proposes a lower price
- **WHEN** 商品说明中的价格与当前 SKU 价格不同
- **THEN** 组合预算按 SKU 事实计算，文档价格不改变可购买性或动作金额

#### Scenario: Evidence does not prove compatibility
- **WHEN** 片段仅说明接口名称，没有必要兼容条件
- **THEN** 兼容结果仍是 unknown，不因有引用或高相似度就变为 pass
