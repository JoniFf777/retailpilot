## Purpose

为用户提供组合采购、连接排查和售后分析三类可连续交互的购物任务，以可验证方案、检查记录和本地草稿替代仅返回聊天文本，并在页面展示任务进展与等待原因。

## ADDED Requirements

### Requirement: Bounded bundle selection
系统 SHALL 支持笔记本、显示器、扩展坞三个槽位的组合方案，按明确总预算、币种、可售状态、数量、兼容规则及锁定选择验证，最多返回 3 个完整方案。

#### Scenario: Valid bundle
- **WHEN** 当前库内候选存在满足总预算与已知兼容约束的三件套
- **THEN** 返回明确 SKU/数量/总价/依据和验证结果，不用模型生成的价格替代商品事实

#### Scenario: Infeasible bounded search
- **WHEN** 已检查候选无法构成合法组合
- **THEN** 返回限制条件及搜索范围，不擅自增加预算或声称已穷尽未检查的全库/全市场

#### Scenario: Missing compatibility facts
- **WHEN** 某设备只有 USB-C 名称而没有必要视频输出或供电事实
- **THEN** 返回兼容未知或补充信息要求，不将接口外形当作支持证明

### Requirement: Versioned follow up decisions
系统 SHALL 维护本次条件、候选、锁定选择和排除项，并通过版本与有效期处理后续修改，已保存偏好不能覆盖明确本轮要求。

#### Scenario: Preserve locked monitor
- **WHEN** 用户降低总预算并要求显示器不变
- **THEN** 新方案保留明确锁定 SKU，仅修订允许部分；锁定项已不可售则说明冲突

#### Scenario: Old selection reference
- **WHEN** 用户使用过期或被替换方案中的相对序号
- **THEN** 要求重新确认明确商品，不按新列表位置猜测原意

### Requirement: Interactive safe diagnosis
系统 SHALL 在明确设备与症状范围内提出安全的连接排查步骤，记录用户观察和已排除原因，最多 5 轮人工反馈，不访问或控制用户设备。

#### Scenario: Continue after user feedback
- **WHEN** 用户反馈换线无效并继续任务
- **THEN** 系统保留该观察来源，推进其他有依据检查，不重复询问同一已回答问题或宣称已实际检测硬件

#### Scenario: Diagnosis cannot progress
- **WHEN** 缺少资料、连续无新信息或达到交互上限
- **THEN** 返回未解决原因与安全下一步建议，不编造故障结论或要求危险拆机

### Requirement: Evidence based after sales assessment
系统 SHALL 将本人订单/支付事实与当前适用政策结合，明确区分已验证事实、用户声明、缺失字段和条件性结论；无当前规则时不得采用隐藏默认期限。

#### Scenario: Missing delivery fact
- **WHEN** 订单库没有可信送达日期，用户声称已收货十天
- **THEN** 声明保存为 user_reported，分析标记 conditional/unknown，不直接宣称退货资格已经验证

#### Scenario: Policy missing or invalid
- **WHEN** 没有有效政策、期限数据非法或日期位于未来
- **THEN** 系统明确指出不能判定，不使用默认十四天或模型常识输出 eligible

### Requirement: Task workbench and compatibility
系统 SHALL 在任务页面展示目标、可读计划、步骤状态、证据、验证问题、版本化产物、输入等待和确认入口；既有 Chat、单商品推荐、购物车、订单与模拟支付公共合同必须保持兼容。

#### Scenario: All three task types are reachable
- **WHEN** 用户从任务列表创建三种类型之一
- **THEN** 前端调用真实任务 API 并展示该类型产物和合法后续操作，不以静态假数据替代执行

#### Scenario: Legacy workflow remains available
- **WHEN** 新任务功能关闭或用户使用旧单商品/交易入口
- **THEN** 旧公开响应和确认语义正常，不能强制依赖新 worker、模型或 RocketMQ
