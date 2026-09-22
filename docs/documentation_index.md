# ShopMind 文档导航

> 更新时间：2026-09-21。当前正式发布版本仍为 `v3.0.0`；工作区中的 Task Workbench 已完成 75/75，但尚未形成新 Release。

## 1. 秋招主读材料

第一次了解项目按顺序读这六份，前四份讲清楚项目本身，第五份抽象成通用能力，第六份取简历素材：

1. [架构总讲：从一次购物任务看懂整个系统](interview_architecture_overview.md)
   —— 定位、术语表、项目量感、总体架构、完整流程、真实请求输入输出、演进史、两分钟口述
2. [亮点一：多 Agent 规划、协作与局部修复](interview_highlight_multi_agent_orchestration.md)
3. [亮点二：RAG 证据检索完整链路](interview_highlight_rag_evidence.md)
4. [亮点三：持久化任务、恢复与安全写入](interview_highlight_durable_execution.md)
5. [横向篇：Agent 工程的十个通用问题与本项目解法](interview_agent_engineering_pitfalls.md)
   —— 把前四篇的做法抽象成通用命题，用于回答"做 Agent 最难的是什么""踩过什么坑"
6. [简历素材](resume_project_summary.md)
   —— 只讲简历怎么写、能写哪些数字、哪些话不能说

这六份对应当前简历版本，明确区分 LangGraph 同步对话图与 PostgreSQL 持久化任务 DAG，并覆盖业务背景、完整流程、难题、取舍、量化边界和高频追问。

需要结合代码阅读时，再看 [项目目录结构详解](shopmind_directory_structure_guide.md)。

## 2. 当前事实来源

发生文档冲突时按以下顺序判断：

1. 当前代码、Alembic head、公开 API Schema 和可执行测试；
2. [当前项目状态](project_status.md)；
3. [项目完整介绍](project_introduction.md)；
4. [当前后端架构](architecture.md)；
5. 专项设计和历史阶段记录。

Task Workbench 的范围、验收和已知限制见：

- [实施方案](shopmind_agent_upgrade_plan.md)
- [最终验收报告](shopmind_agent_upgrade_acceptance.md)
- [验收案例目录](shopmind_agent_upgrade_cases.json)
- [场景与测试映射](shopmind_agent_upgrade_test_map.md)

## 3. 开发与运行文档

| 文档 | 用途 |
| --- | --- |
| [development.md](development.md) | 环境、命令、数据库与 migration `0020` |
| [demo_runbook.md](demo_runbook.md) | 本地 Demo 准备、启动和验证 |
| [frontend_implementation_plan.md](frontend_implementation_plan.md) | React 前端当前状态和实现边界 |
| [frontend_redesign_v2_plan.md](frontend_redesign_v2_plan.md) | 前端重做方案：Tailwind v4、组件层、离线 demo 模式 |
| [operations_runbook.md](operations_runbook.md) | Preflight、readiness、回滚和运维参考 |
| [pr_checklist.md](pr_checklist.md) | 变更提交前检查 |
| [test_plan.md](test_plan.md) | 分层测试范围和历史验收 |

## 4. 深度技术设计

| 主题 | 文档 |
| --- | --- |
| Agent Runtime | [agent_runtime_design.md](agent_runtime_design.md) |
| API 合同 | [api_design.md](api_design.md)、[api_contracts.md](api_contracts.md) |
| 推荐合同 | [recommendation_contract_design.md](recommendation_contract_design.md) |
| Catalog、SPU、SKU | [catalog_and_sku_design.md](catalog_and_sku_design.md) |
| Cart、Order、Inventory、Payment | [inventory_order_payment_design.md](inventory_order_payment_design.md) |
| Tool Gateway | [tools_design.md](tools_design.md) |
| 身份、HITL 与安全 | [safety_design.md](safety_design.md) |
| Outbox 与 RocketMQ | [rocketmq_outbox_design.md](rocketmq_outbox_design.md) |
| LangSmith 边界 | [langsmith_observability.md](langsmith_observability.md) |

## 5. 历史记录

以下文件用于追溯项目演进，不作为当前实现状态来源：

- `baseline_report.md`、`gap_analysis.md`、`current_architecture_audit.md`；
- `implementation_plan.md`、`database_migration_plan.md`、`frontend_rebuild_plan.md`；
- `phase*_report.md`、`phase*_plan.md`；
- `v2_*`、`v3_*`、`v6_release_candidate_notes.md`。

历史报告保留当时的状态、测试数字和语言，不应据此覆盖当前 `project_status.md`。

## 6. 当前边界

- Catalog/PostgreSQL 是 SKU、价格、库存和交易事实源，资料不能覆盖这些事实。
- 新任务功能默认关闭；启用后要求 migration `0020_task_worker_heartbeat` 与新鲜 Worker heartbeat。
- 持久化任务 DAG 是自研 Worker，不是 LangGraph；LangGraph 只负责同步对话图。
- Redis 是可选 Runtime 协调后端，不是 Cart/Order 或任务 DAG 的事实存储。
- RocketMQ 只用于可选 Outbox Publisher，不负责 Agent 通信和任务调度；Consumer/Inbox 尚未实现。
- 售后能力只分析本人订单和保存本地草稿，不创建外部工单或退款。
- 支付是 Mock Provider；项目没有线上 CTR、转化率或生产 SLA 证据。
