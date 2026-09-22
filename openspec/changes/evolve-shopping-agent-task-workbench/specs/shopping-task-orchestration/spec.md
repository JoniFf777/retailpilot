## Purpose

将消费电子复杂目标转换成权限受限、依赖明确、结果可验证的协作任务，支持有限的补查和方案修订，并让调用方区分规则执行、模型建议和真正完成的业务结果。

## ADDED Requirements

### Requirement: Validated bounded plans
系统 SHALL 在执行前校验任务计划的能力白名单、依赖、资源范围、产物引用和预算；单份计划最多 12 步、最多 3 个独立步骤并行，不得执行未知工具、循环依赖或未经授权的写操作。

#### Scenario: Legal dependent plan
- **WHEN** 组合任务需要先查询商品，再核验组合，且其中存在独立读取步骤
- **THEN** 系统只并行执行已满足依赖的步骤，后续步骤读取正确类型和版本的已完成产物

#### Scenario: Malicious plan rejected
- **WHEN** 模型计划要求执行代码、支付、未知工具、扩大用户数据范围或包含依赖环
- **THEN** 执行前拒绝该计划并记录稳定原因，最多一次计划修正后回退或澄清，不产生工具副作用

### Requirement: Isolated specialist results and source authority
系统 SHALL 将任务身份、版本、角色范围、结果状态和依据作为交接合同，分支结果不得直接覆盖其他角色或较新计划的状态；结构化商品和本人订单事实优先于模型与文档中的冲突声明。

#### Scenario: Results arrive out of order
- **WHEN** 两个合法只读分支逆序返回
- **THEN** 两者结果按计划归属稳定合并，候选与事件不会因完成顺序而被错误覆盖

#### Scenario: Evidence conflicts with price
- **WHEN** 模型或资料返回不同于 Catalog 的价格或库存
- **THEN** 方案使用当前 Catalog 值并保留冲突原因，不引入新 SKU 或虚构可售数量

### Requirement: Verification directed local repair
系统 SHALL 为方案返回可定位的验证报告，规则失败不能被模型检查覆盖；只允许对受影响步骤及其后续依赖进行修订，最多 2 次，并检测重复且无新事实的进展指纹。

#### Scenario: Replace incompatible component
- **WHEN** 组合存在明确扩展坞兼容失败且还有合法替代候选
- **THEN** 系统针对冲突部分修订并重新验证，保留用户锁定商品和仍有效的其他产物

#### Scenario: Reviewer cannot override a failed rule
- **WHEN** 硬预算或兼容规则失败但模型 Reviewer 认为方案可接受
- **THEN** 结果仍不能通过或进入业务写入，系统返回冲突或澄清

#### Scenario: No progress terminates
- **WHEN** 相同目标、候选、事实版本、查询和失败问题再次出现，或修订次数已耗尽
- **THEN** 系统停止修订并解释无进展/预算原因，不无限重试或暗中放宽条件

### Requirement: Honest model and offline modes
系统 SHALL 由服务端选择 offline 或 agent 模式，在 agent 模式中通过实际模型适配调用生成计划或检查建议，并记录实际候选、尝试和失败；模式和回退状态必须可见。

#### Scenario: Agent mode produces a proposal
- **WHEN** 配置有效且 agent 模式任务进入规划
- **THEN** 系统实际调用受控模型适配、校验返回计划并记录模型使用，不把预制规则结果标记为模型输出

#### Scenario: Provider unavailable
- **WHEN** agent 模式缺配置或模型调用失败
- **THEN** 系统标记配置不可用或明确规则回退，不展示虚假的模型成功或将缺失 usage 记作零

### Requirement: Cumulative execution bounds
系统 SHALL 在等待、修订、重启和 resume 后保留累计预算；默认上限为 36 次步骤尝试、24 次模型尝试、每步临时失败最多 2 次尝试、5 轮人工交互，活跃回合默认 120 秒且不超过服务端 300 秒上限。

#### Scenario: Resume does not replenish budget
- **WHEN** 用户恢复已消耗大部分预算的任务
- **THEN** 任务继续使用原累计账本，额度不足返回明确结果而不是重新获得完整预算

#### Scenario: Permission failure is not retried
- **WHEN** 工具拒绝原因是权限或非法参数
- **THEN** 系统不通过换角色、反复调用或新建子任务绕过拒绝
