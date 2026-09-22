## Purpose

把已验证的购物任务产物安全衔接到明确的用户确认，支持组合商品加购与本地售后草稿保存，保证并发、重复请求、过期产物及动态业务事实变化时不会发生越权或部分写入。

## ADDED Requirements

### Requirement: Explicit artifact bound actions
系统 SHALL 只从本人当前合法产物创建 add_bundle_to_cart 或 save_after_sales_draft 待确认动作，绑定目标、计划、产物和动作版本及有效期；任何读取或规划角色不得直接执行写入。

#### Scenario: Agent suggests a cart operation
- **WHEN** Agent 为通过验证的组合提议加购
- **THEN** 应用生成具体 SKU/数量/价格预览等待用户确认，购物车仍不改变

#### Scenario: Stale or foreign artifact
- **WHEN** 客户端使用另一用户、旧计划、已失效引用或未通过验证的产物准备动作
- **THEN** 请求被拒绝，不以客户端提供的商品事实重新构造一个可执行动作

### Requirement: Atomic bundle cart confirmation
系统 SHALL 在确认时重验所有组合项、价格、库存、归属与版本，并在同一业务事务中完成整组购物车更新和动作结果；组合加购不预占库存或自动下单。

#### Scenario: One component has insufficient inventory
- **WHEN** 三个组合项中任一项在确认时不可售或可用数量不足
- **THEN** 整组购物车写入回滚，动作返回明确原因，不留下前两项已加购的部分结果

#### Scenario: Price changes after preview
- **WHEN** 确认时任一 SKU 价格与用户看到的预览不同
- **THEN** 要求重新预览并确认，不能静默按新价写入

### Requirement: Replay without duplicate effects
系统 SHALL 保存动作终态和请求身份，相同确认请求重放返回原业务结果；并发确认不能重复增加商品或重复保存草稿。

#### Scenario: Response lost after commit
- **WHEN** 数据库已提交但响应丢失，用户重复发送相同确认
- **THEN** 返回原成功结果，即使任务版本已前进也不再次写入

#### Scenario: Reused key with different edits
- **WHEN** 同一确认 key 被用于不同数量或不同草稿内容
- **THEN** 返回冲突且不改变原已执行事实

### Requirement: Local after sales draft only
系统 SHALL 在明确确认后保存本人订单的本地售后草稿，保留系统事实、用户声明、政策引用及缺失材料的来源；不得改变订单支付状态或声称已提交外部退款。

#### Scenario: Save a conditional draft
- **WHEN** 用户确认一个包含未验证送达声明的条件性售后草稿
- **THEN** 草稿保留 user_reported 标识并显示仅本地保存，订单、支付和外部系统没有副作用

### Requirement: Expiry rejection and legacy compatibility
系统 SHALL 在动作过期、明确拒绝或任务取消时阻止尚未提交的写入，旧单 SKU 动作与既有订单/支付合同保持原语义。

#### Scenario: User declines
- **WHEN** 用户取消组合加购或售后草稿确认
- **THEN** 动作终结而不写 Cart/Draft，已经展示的分析结果仍可查看

#### Scenario: Legacy action regression
- **WHEN** 旧 API 确认单 SKU 加购或保存偏好
- **THEN** 使用原字段与状态合同，不要求提供新 task 或 bundle 标识
