## Why

ShopMind 已有购物、交易和运行时基础，但默认 Agent 主链路仍偏固定查询与推荐，缺少复杂目标的计划执行、结果验证、局部调整及真正的步骤恢复。此次将项目升级为面向消费电子的选购与服务协同 Agent 工作台，让复杂业务驱动多 Agent、RAG、状态和安全执行，而不是继续增加孤立组件。

## What Changes

- 增加三个有界任务：组合选购（笔记本、显示器、扩展坞）、连接兼容排查、本人订单售后资格分析与本地申请草稿；组合选购为主验收场景。
- 新增任务工作台：任务目标、计划进度、证据、方案版本、澄清问题、检查结果和待确认动作可见，并支持断线重连、暂停后继续和工作进程重启。
- 在现有 Harness/Adapter/Tool Gateway 上增加任务级编排：模型提出白名单内的计划，服务端校验依赖和权限；规则与 Reviewer 检查产物；限定轮次、预算和进展指纹的局部修复，不放开任意代码执行。
- 为复杂任务提供持久化任务、步骤、尝试、产物、计划修订和事件，使用 PostgreSQL 租约与 fencing/CAS 领取和提交；不把既有轨迹比较称为步骤恢复。
- 借鉴本地 `D:/java/ragent` 的通道与后处理、查询改写、预算和归因设计，把 Python 检索真正接到新业务路径；补齐活动版本/撤销可见性、业务范围门控及真实文档检索验证。
- 增加受控组合加购与本地售后草稿动作；重复确认幂等、绑定任务及方案版本、确认时重验事实。保留已有单 SKU 加购、订单、模拟支付与 Outbox 语义。
- 保留离线规则模式用于回归与演示；新增可选真实模型任务模式并记录实际调用轨迹，不用 Fake 结果宣称自主规划完成。
- 将验收重点改为真实业务闭环和可核对的产物/数据库结果；模型质量指标只写实测值，外部模型与云追踪遵守显式授权边界。

## Capabilities

### New Capabilities

- `shopping-task-orchestration`: 类型化计划、依赖执行、角色能力隔离、验证、有限局部修复与模型调用合同。
- `shopping-task-recovery`: owner-scoped 持久任务、事件、租约、步骤恢复、预算与取消一致性。
- `shopping-task-workspace`: 三种购物服务任务、任务 API、组合兼容事实、前端任务工作台与连续交互。
- `shopping-evidence-grounding`: 新任务共用的范围受限混合检索、版本化证据可见性、引用归因和降级。
- `shopping-task-actions`: 任务产物绑定的组合加购与本地售后草稿确认动作。
- `shopping-agent-acceptance`: 可执行场景验收、离线/真实模型证据分离、回归与可复现交接。

### Modified Capabilities

无。新增任务 API 与动作类型走独立版本合同；既有 chat、单商品推荐、购物车和确认 API 保持兼容。本变更内复用与修复现有模块时必须通过旧合同回归，不改变其公开要求。

## Impact

- 新增 `app/shopping_tasks/` 领域模块、Repository、Schema/API、Alembic 线性迁移和 `frontend/src/features/tasks/`；复用现有身份、Catalog、RAG、动作与交易服务。
- 改造 `app/recommendation/retrieval_pipeline.py`、证据索引/仓库、模型适配与协调工厂；不建立第二套独立 Harness/身份/交易系统。
- 新增 dock 品类和明确的接口/兼容关系数据、受信购物语料与隔离演示种子；不批量清空共享数据库。
- 新增 PostgreSQL 任务 worker；RocketMQ 继续只发布交易 Outbox，不成为任务或证据调度依赖。
- 不引入 Java 运行时服务，不强制 ES/图谱/联网/MCP，不实现任意 Coding Agent、真实退款或生产部署。
- 当前仅创建方案。总入口为 `docs/shopmind_agent_upgrade_plan.md`，详细合同由本变更 design/specs/tasks 定义；实现由新窗口在用户发起后执行。
