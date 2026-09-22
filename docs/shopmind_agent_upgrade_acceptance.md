# ShopMind Agent Task Workbench 验收报告

状态：**实现与验收完成（75/75）**。快照日期：2026-09-21。

本报告只描述当前工作区中已经接线并验证的能力，不把历史 V4-V6
数字、模型替身或离线结果冒充本次真实模型验收。正式版本仍为
`v3.0.0`；本次完成不等于已经提交、推送、打 tag 或部署。

## 1. 最终业务范围

新任务工作台覆盖三类消费电子任务：跨品类组合选购、兼容性排查、
本人订单的售后资格分析与本地草稿。每个任务都持久化 Goal、计划修订、
步骤、尝试、产物、事件和动作预览；Worker 按依赖关系调度最多三个只读
分支，并使用租约、fencing token、预算和幂等键支持中断恢复。

Agent 模式由真实模型提出白名单内的结构化计划，服务端重新投影并校验
能力、角色、依赖和只读边界。确定性规则先检查预算、币种、兼容性、
证据、库存和 owner，模型 Reviewer 只能补充解释、引用和需求覆盖问题，
不能把规则失败改为通过。VerificationIssue 只会使受影响步骤及其后继
节点失效，仍有效的 Catalog、订单或其他分支产物会复用，最多修订两次。

组合加购和本地售后草稿都采用“预览—用户确认—执行前重验”。确认事务
锁定任务、动作及 SKU/库存/Cart 行，整组成功或整组回滚；重复确认、响应
丢失重放、确认/取消竞态和并发确认都由同一事务与 Resolution 结果处理。

## 2. 分层验收结果

| 层次 | 最终结果 | 证明内容 |
| --- | --- | --- |
| Python 全量回归 | `978 passed, 68 skipped, 3 warnings` | 旧 Chat/交易/Runtime 与新任务实现兼容 |
| 任务域单测 | `22/22` | 合同、计划、权限、Reviewer 约束、局部修复、状态与预算 |
| PostgreSQL 专项 | `7/7`，1 个 pgvector 反射 warning | 动作原子性、重放、竞态、任务租约、真实检索和证据撤销 |
| 生产/回滚专项 | `30/30` | preflight、readiness、Worker heartbeat 与 rollback 合同 |
| 前端 | `24 files / 135 tests` | Vitest；lint、普通/E2E typecheck、build、bundle budget 均通过 |
| 回滚演练 | `6/6` cases | 关闭准入、停止领取、等待租约、保留确认事实、不 downgrade、撤销证据不可见 |
| Readiness | disabled 与 enabled 两条真实检查均 ready | 关闭新功能兼容旧 `0017`；开启时要求 `0020` 与新鲜 heartbeat |
| 真实模型 | `3/3` 任务轨迹通过门禁 | 三类任务均有真实 Provider Planner 成功；Reviewer 与局部修订有真实证据 |

前端真实浏览器链路和版本化 24 例业务目录的既有通过证据继续保留在
`frontend/e2e/task-workbench.live-critical-path.spec.ts`、
`shopmind_agent_upgrade_cases.json` 与 `shopmind_agent_upgrade_test_map.md`。

## 3. 真实模型证据

在用户明确授权后，以 `WORKSHOP_MODEL=openai:zai-org/GLM-5.3`、
`SHOPMIND_SHOPPING_TASK_MODE=agent`、LangSmith 关闭的方式运行三条脱敏轨迹。
模型通过现有 Harness 与共享 Model Gateway 调用；任务专用总超时为 180 秒，
Worker 在调用期间续租。模型返回的计划先投影到服务端能力合同，再进行 DAG、
角色、只读和必需校验节点检查。

最终脱敏报告位于
`artifacts/shopping-task-model-acceptance/summary.json`：

- 组合选购：真实结构化 Planner 成功，最终 `recommended`；经历两次有界
  plan revision，其中第一次由受控 `evidence_unavailable` 问题触发，证明
  局部修复路径实际执行。
- 兼容性排查：真实 Planner 和 Reviewer 被使用，最终以
  `needs_information` 安全结束；没有把缺少的设备事实猜成兼容结论。
- 售后分析：真实 Planner 成功并经服务端 policy normalization，最终
  `conditional`。该轨迹的 Reviewer 调用降级，确定性规则结果仍安全完成；
  报告保留 `reviewer_used=false`，没有伪装为 Reviewer 成功。

完成门禁按 OpenSpec D13/C6 执行：三种任务各有真实 Provider 成功计划轨迹、
至少一个真实 Reviewer 结果、至少一次合法局部 revision、没有越权工具或
未确认写入、业务规则 gate 全部通过。未知 token/费用不记为零，也不宣称
模型准确率或延迟提升。

## 4. 生产与回滚证据

当前 Alembic 单一 head 为 `0020_task_worker_heartbeat`。任务功能默认关闭；
关闭时 preflight 返回 not-applicable、readiness 接受旧路径的 `0017` 或当前
head，不阻断现有 Chat。开启任务后 readiness 要求当前 migration、可用
PostgreSQL/协调后端、配置合法的 agent/offline 模式及新鲜 Worker heartbeat。

回滚不是数据库 downgrade：先关闭新任务准入，再停止 Worker 新领取，等待
有效租约结束或显式取消。已确认 Cart/草稿、任务历史、产物和事件继续保留，
证据撤销过滤继续生效。真实 PostgreSQL 测试证明单项失败整组回滚，已确认
动作不会被回滚演练删除。

对应可复现产物：

- `artifacts/shopping-task-readiness/disabled-summary.json`
- `artifacts/shopping-task-readiness/enabled-summary.json`
- `artifacts/shopping-task-rollback/summary.json`
- `artifacts/shopping-task-model-acceptance/summary.json`

## 5. 已知边界

- 新任务功能和 Agent 模式仍由服务端显式启用；默认旧路径不受影响。
- 当前 Provider 的 Planner/Reviewer 延迟较高，真实探针约 100–131 秒；这只
  是本次环境观测，不是性能承诺。超时或熔断时会显式降级到受控离线计划/
  确定性验证。
- 售后只读取本人订单并保存本地草稿，不创建外部工单、不退款、不伪造物流。
- RocketMQ 仍只用于可选 Transactional Outbox 发布，不是任务调度器；
  Consumer/Inbox 仍属独立后续范围。
- 本次没有发布、部署、推送、真实支付或外部履约，也没有启用 LangSmith 云
  Trace。真实模型测试使用的 9 个私有 PostgreSQL schema 已清理，脱敏 JSON
  证据保留。
