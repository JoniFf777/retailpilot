## Purpose

使购物任务在网络中断、进程重启、用户等待、并发修改和取消后仍保持可解释的状态与副作用边界，通过持久事实恢复未完成工作，而不是仅重新展示历史日志。

## ADDED Requirements

### Requirement: Owner scoped durable lifecycle
系统 SHALL 持久化任务目标、计划版本、步骤、尝试、产物、事件和结果；任务的读取、命令、恢复与动作全部绑定认证 owner，其他用户不得枚举资源。

#### Scenario: Task survives process restart
- **WHEN** 任务已有完成步骤和未完成步骤，执行进程退出并重启
- **THEN** 系统重新领取合法未完成工作，复用仍有效的完成产物，并保留任务身份和累计使用量

#### Scenario: Wrong owner access
- **WHEN** 另一个用户获取已知 task、artifact、event 或 action 标识
- **THEN** 读取返回与不存在资源一致的结果，命令不能改变状态或触发模型/工具调用

### Requirement: Lease fencing and safe completion
系统 SHALL 保证每个任务只有有效的调度所有者，步骤完成提交同时检查任务、目标、计划和执行租约版本；外部调用期间不持有长期数据库锁。

#### Scenario: Two workers compete
- **WHEN** 两个独立 worker 同时领取同一个待执行任务
- **THEN** 只有一个有效调度者提交该版本产物，步骤可按允许的并行度执行但不会重复发布结果

#### Scenario: Late result from expired lease
- **WHEN** 原 worker 失去租约，继任 worker 已接管，原调用迟到返回
- **THEN** 迟到结果不能覆盖当前产物、状态、动作或公共完成事件，诊断与未知使用量按原尝试归属记录

### Requirement: Command idempotency and version conflicts
系统 SHALL 对创建、反馈、取消、恢复、动作准备与确认提供 owner/operation 作用域的幂等身份及输入比较；状态改变命令必须检查期望版本。

#### Scenario: Same command replay
- **WHEN** 同一用户以相同 key 和相同 body 重试一个已处理命令
- **THEN** 返回原处理结果，不重复创建任务、步骤、消息或业务副作用

#### Scenario: Conflicting command
- **WHEN** 同 key 输入不同或期望任务版本已过时
- **THEN** 返回稳定 409 冲突，不覆盖较新条件，已成功命令的相同重放仍能返回原结果

### Requirement: Waiting cancellation and expiry
系统 SHALL 在等待用户输入或确认时释放执行资源；取消与过期后不得派发新工作，取消与动作提交须形成确定的先后结果。

#### Scenario: Waiting task resumed
- **WHEN** 用户在未过期的等待任务中提供所需事实
- **THEN** 系统记录信息来源并继续相关步骤，保留已问问题和预算，不重复处理已有效完成的工作

#### Scenario: Cancel races with confirmation
- **WHEN** 取消命令与动作确认并发
- **THEN** 取消先提交则确认被拒绝；确认先提交则返回真实已执行事实，不能宣称已回滚

#### Scenario: Expired task
- **WHEN** 任务达到服务端绝对有效期
- **THEN** 系统使未执行动作和工作失效，恢复被拒绝且已提交的历史业务事实保留

### Requirement: Observable reconnect and bounded projections
系统 SHALL 提供持久有序事件和快照，支持带游标的重连，公开投影不包含原始 Prompt、模型内部推理、凭据或任意工具参数。

#### Scenario: Browser disconnect and reconnect
- **WHEN** 浏览器断开后使用快照序号重连
- **THEN** 系统返回有序后续事件或明确游标过期并要求刷新快照，不自动取消后台任务或重复操作

#### Scenario: Event retention expires
- **WHEN** 请求游标早于保留范围
- **THEN** 返回明确事件过期语义，不能静默伪装成完整历史

### Requirement: Deletion prevents worker resurrection
系统 SHALL 将新任务与产物纳入 owner-data 删除和 retention，并在删除前使有效工作与待执行动作失效。

#### Scenario: Owner deletion during execution
- **WHEN** 用户删除本人任务数据时仍有外部只读调用运行
- **THEN** 迟到调用不能重建任务或产物，独立脱敏审计按既有保留规则处理
