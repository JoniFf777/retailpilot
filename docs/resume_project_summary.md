# ShopMind 简历素材

> 更新时间：2026-09-21
>
> **本文只负责"简历上怎么写"。** 项目架构、业务流程和设计思路见 [架构总讲](interview_architecture_overview.md)，不在这里重复。
>
> 原则：每一条都能在代码里指出来；指不出来的一律不写。

## 1. 怎么用这份文档

| 你要做的事 | 看哪一节 |
| --- | --- |
| 写三条 Agent 岗简历 | §3 推荐写法 |
| 写四五条偏后端/全栈 | §4 完整版 |
| 投不同岗位怎么取舍 | §5 |
| 简历上能写哪些数字 | §6 |
| 确认哪些话不能说 | §7 **投递前必读** |
| 面试时按主题翻代码 | §8 |

## 2. 一句话定位与技术栈

**ShopMind 是一个以 Agent 为交互与决策入口、以确定性规则和 PostgreSQL 事务为安全底座的智能购物决策与交易系统。**

它的价值不在"接入大模型做推荐"，而在把不确定的 Agent 推理与确定性业务系统分层：模型负责理解、规划和解释；Category Schema、Catalog、排序器和证据门控负责约束校验；PendingAction/HITL 把"建议"与"写操作"隔离；PostgreSQL 负责价格、库存、订单和事件的最终事实。

| 方向 | 技术 |
| --- | --- |
| Agent / LLM | LangGraph、LangChain、Pydantic 结构化合同、持久化任务 DAG、AI Admission、Model Gateway |
| Backend | Python、FastAPI、SQLAlchemy、Alembic、Pydantic |
| 数据 | PostgreSQL、pgvector；Redis 为可选协调后端 |
| 检索与证据 | Fetch/Parse/Chunk/Enrich/Index、Vector/Lexical SearchChannel、RRF、Evidence Gate、可选 CrossEncoder |
| 交易与消息 | 行锁、条件更新、乐观 CAS、Idempotency、Transactional Outbox、可选 RocketMQ |
| Frontend | React 19、TypeScript、Vite、TanStack Query、Zod、OpenAPI 类型生成 |
| 测试 | pytest、Vitest、Playwright、真实 PostgreSQL 并发测试 |

简历技术栈栏建议只列：**Python、FastAPI、LangGraph、LangChain、Pydantic、PostgreSQL/pgvector、Redis**。其余留到面试展开。

## 3. 推荐写法：Agent 岗三条

这是当前主推版本。关键是**明确区分 LangGraph 同步图和持久化任务 DAG**——把自研 Worker 说成 LangGraph 是最容易被一句话问穿的地方。

> **项目：基于 LangGraph 与持久化任务 DAG 的智能购物决策与交易系统**
>
> **项目描述：** 面向消费电子选购与购物服务的多 Agent 助手，用 LangGraph 编排商品分析与资料检索，并以持久化任务 DAG 支持跨品类组合选购、兼容性排查及售后资格分析，通过用户确认衔接组合加购和售后草稿准备。
>
> **技术栈：** Python、FastAPI、LangGraph、Pydantic、LangChain、PostgreSQL/pgvector、Redis
>
> **项目功能：**
>
> - **多 Agent 任务编排：** 用 LangGraph 编排会话内只读协作图；复杂目标经校验后持久化为任务 DAG，Worker 按依赖前沿并行执行；通过结果校验、局部重跑和方案修订处理预算、兼容性等冲突，并设置迭代上限避免死循环。
> - **RAG 证据检索：** 围绕商品资料、兼容信息和商城政策构建版本化检索链路，融合 pgvector 语义召回与词法检索并通过 RRF 排序；校验商品范围、证据版本和政策有效期，结果附带引用，关键证据不足时返回澄清或降级结果。
> - **持久化任务执行：** 将任务计划、步骤和中间结果持久化，通过租约、幂等和版本校验支持中断恢复及结果复用；加购和售后草稿采用"生成预览—用户确认—执行前重验"的流程，校验商品、价格、库存及订单归属后再提交业务操作。

### 展开版（篇幅允许时）

> - **多 Agent 规划与协作：** 使用 LangGraph 组织同步只读角色，并设计持久化任务 DAG 执行复杂购物目标；模型在白名单能力内提出步骤与依赖，服务端完成环路、权限和预算校验，对独立步骤进行有界并行，通过确定性规则、受限 Reviewer 和最多两次局部修订处理预算、兼容及证据冲突。
> - **RAG 证据检索：** 围绕商品说明、兼容资料和商城政策构建版本化证据链路，融合 pgvector 语义召回与词法检索并使用 RRF 排序；对商品范围、活动版本、政策地区/渠道/有效期及引用来源进行校验，关键证据不足时返回补查、澄清或显式降级。
> - **持久化任务与安全执行：** 将任务、计划、步骤、尝试、中间产物和事件持久化，通过租约、fencing token、幂等键与版本 CAS 支持进程中断恢复和有效结果复用；组合加购与本地售后草稿采用"生成预览—用户确认—执行前重验"，在事务中校验价格、库存、证据和订单归属，保证整组原子提交。

## 4. 完整版：偏后端 / 全栈四到五条

技术栈栏写：**FastAPI、LangGraph、PostgreSQL/pgvector、SQLAlchemy、Redis、React/TypeScript、RocketMQ**

1. 设计并实现面向中文消费电子选购的多 Agent 系统：用 LangGraph Supervisor 编排 Product、RAG、Preference、Decision 等只读角色处理同步对话，另设计 PostgreSQL 持久化任务 DAG 承载组合选购、兼容排查与售后分析；通过 Pydantic Schema 与确定性 Catalog 过滤/排序生成可解释的 SKU 级推荐，覆盖 10 类商品。
2. 构建四类购物证据的版本化入库 Pipeline，以内容指纹、PostgreSQL 租约/CAS 和活动发布指针支持幂等恢复及原子发布；将 pgvector/词法召回抽象为 SearchChannel，经 RRF、可选重排和 Evidence Gate 限定候选、兼容组合及政策有效范围。
3. 建立 Agent 安全写入机制：以角色能力白名单、Tool Gateway、owner/thread 隔离和 PendingAction/HITL 阻断未确认副作用；用三层准入、服务端候选路由与熔断控制容量与降级；以版本化 ShoppingSessionState 支持多轮条件修改与并发陈旧覆盖防护。
4. 打通 Cart—签名 Checkout 快照—Order—Inventory Reservation—Mock Payment—Transactional Outbox 交易链路，利用 PostgreSQL 行锁、稳定加锁顺序、条件更新、请求哈希幂等和持久化 `provider_succeeded` 状态处理超卖、重复请求、支付/取消竞态及响应丢失恢复。
5. 搭建分层交付门禁，覆盖 trajectory replay、模型故障、证据冲突、检索等价性、真实 PostgreSQL 并发与浏览器链路；后端 181 个测试文件跨 20 个模块，前端 Vitest 154 个单测加 Playwright 离线与 live 两套 e2e。

**空间紧张时保留 1、2、3、4**，把第 5 条压缩成一句并入末尾。

## 5. 不同岗位怎么取舍

| 目标岗位 | 优先写 | 面试重点 |
| --- | --- | --- |
| Agent / LLM 应用 | §3 三条 | 受约束规划、Tool Gateway、RAG 证据充分性、失败分类与降级、评测边界 |
| Python 后端 | §4 的 1、3、4、5 | FastAPI 契约、PostgreSQL 事务、幂等、并发竞态、Outbox、租约与 fencing |
| 全栈 | §4 的 1、3、4 + React | POST SSE、OpenAPI 类型生成、恢复型 UX、真实浏览器链路 |
| 平台 / Agent Infra | §4 的 2、3、5 + Runtime | Harness、typed adapter、预算/取消/回放、Redis 协调、readiness 与回滚 |

投后端岗时弱化第 2 条，强化第 4 条的数据库并发与一致性；投 Agent 岗时反过来。

## 6. 简历上能写哪些数字

### 当前代码快照可写（投递前仍应重新核对）

- 数据表 **46 张**：基础业务与 Runtime 17 + 任务工作台 12 + Catalog/交易/AI 证据平台 17
- Alembic 迁移 **20 个**，head 为 `0020_task_worker_heartbeat`
- API **13 个业务路由模块**，另有 1 个内部辅助模块
- 后端测试 **181 个 `test_*.py`**，分布在 20 个子目录
- 前端 Vitest **154** 个单测；Playwright 离线 + live 两套 e2e
- Category Schema 覆盖 **10 类**消费电子
- 任务侧上限：计划 ≤12 步、并行前沿 ≤3、局部修订 ≤2 次、模型尝试 ≤24、用户交互 ≤5 轮

### 写之前必须重跑确认

全量回归的 `N passed / M skipped` 这类数字会随每次提交变化。**投递前跑一次最新 CI 再填**，不要沿用文档里的历史数字。不同专项批次之间有重叠，不能相加成独立用例数。

### 永远不能写

CTR、转化率、推荐准确率提升、响应时间 SLA、线上用户量——项目没有承载过真实流量，这些数字没有来源。面试官追问一次就会暴露。

宁可写"覆盖 X 类验证场景"，也不要写"准确率提升 X%"。

## 7. 不能夸大的边界

**这一节是本文档最重要的部分。** 投递前通读一遍，面试前再读一遍。

- **支付是 Mock Provider**，不含真实银行卡、退款、webhook 或自动对账。
- **RocketMQ 只有可选 Publisher**；Consumer、Inbox 和消费端去重尚未实现，交付语义是 at-least-once，不能说全链路 exactly-once。
- **RocketMQ 不调度购物证据入库**，也不是 Agent 通信总线；Pipeline 用 PostgreSQL 租约/CAS。
- **Redis 是 Agent Runtime 的可选协调后端**，不是 Cart/Order 或任务 DAG 的事实存储。
- **售后能力只分析本人订单并保存本地草稿**，不创建外部工单、不退款、不改订单状态。简历必须写"售后资格分析/草稿准备"，不能写"自动办理售后"。
- **持久化任务 Worker 不是 LangGraph**。LangGraph 负责同步对话图，任务 DAG 是自研调度器。这是最容易被问穿的一条。
- **AI 管理面和远程扩展默认关闭**；Model Gateway、完整 Retrieval Pipeline 和动态 Extension 已实现并有门禁，但尚未全面接管默认模型、RAG、Prompt 和工具路径。
- **图谱、联网搜索、远程 MCP、ES 和对象存储不是当前核心路径**，不能写成已投产能力。
- **评测包含合成数据和本地 live 验收**，只证明合同与回归稳定，不代表真实推荐质量提升。语义 reranker 没有可宣称的线上收益。
- **LangSmith 是可选实验旁路**，正常开发、Demo 和默认测试不依赖云端 Trace。
- **项目未经真实生产流量验证**，用"生产参考能力/工程化设计"而不是"生产级系统"。
- **Agent 默认在同一后端进程内协作**，不是已上线的微服务集群。
- **SSE 主要传递生命周期事件**，不是完整逐 token 输出。

主动说出这些边界，比被面试官问出来好得多——它证明你清楚自己做了什么、没做什么。

## 8. 代码索引

面试时被问到某个主题，直接翻这里。

| 主题 | 主要位置 |
| --- | --- |
| LangGraph 同步图与路由 | `agents/shopmind_multi_agent/graph.py`、`planning.py`、`supervisor_router.py` |
| 持久化任务 DAG | `app/shopping_tasks/`：`contracts.py`（类型与上限）、`planner.py`、`worker.py`、`repository.py` |
| 计划校验与局部修订 | `app/shopping_tasks/planner.py::validate_plan`、`repair.py`、`verifier.py` |
| 确认与原子写入 | `app/shopping_tasks/actions.py`、`app/services/pending_actions.py` |
| 推荐解析与排序 | `app/recommendation/request.py`、`constraints.py`、`ranking.py`、`service.py` |
| 多轮购物状态 | `app/recommendation/session_state.py`、`app/repositories/runtime_shopping_state.py` |
| RAG 检索与证据门控 | `app/recommendation/rag.py`、`retrieval_pipeline.py`、`app/repositories/documents.py` |
| 证据入库 Pipeline | `app/ai_platform/ingestion.py`、`indexing.py`、`app/repositories/shopping_evidence.py` |
| Runtime / Tool Gateway | `app/runtime/harness.py`、`tool_gateway.py`、`plan_executor.py`、`coordination.py` |
| 模型韧性与准入 | `app/ai_platform/resilience.py`、`model_registry.py`、`app/shopping_tasks/model_gateway.py` |
| Cart / Order / Payment | `app/services/cart.py`、`checkout.py`、`orders.py`、`payments.py` |
| Outbox | `app/outbox/` |
| 身份与治理 | `app/security/`、`app/governance/` |
| HTTP API | `app/api/routes/`、`app/schemas/` |
| React 前端 | `frontend/src/features/` |
| 评测 | `evaluation/`、`tests/` |

## 9. 投递前检查清单

- [ ] 三条功能里没有把持久化 DAG 说成 LangGraph
- [ ] "售后"写的是资格分析或草稿准备，不是自动办理
- [ ] 技术栈里 PostgreSQL 后面带了 pgvector
- [ ] 全量测试数字已按最新 CI 更新，或已改成结构性描述
- [ ] 没有出现准确率、转化率、SLA 类数字
- [ ] 项目名称一致（仓库 `pyproject.toml` 的 name 字段别还是模板名）
- [ ] §7 边界清单通读过一遍，每条都能当场解释
