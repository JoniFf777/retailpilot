## Context

参见 proposal.md 的动机与能力目录，面向人的入口为 `docs/shopmind_agent_upgrade_plan.md`。当前是模块化 Python 单体与 React 前端，HEAD `2198bd5` 上叠加用户拥有的未提交 AI 平台实现。新窗口必须重新记录 HEAD、diff、相关未跟踪文件与摘要；不可仅据 Git HEAD 重建当前运行能力。

现有 AgentPlanner 默认将已选路由编译成计划，LLM 提案不能改变步骤合同。现有 BoundedPlanExecutor 的并行分支只接受无依赖步骤，结构化推荐有单独串行执行器。RuntimeTrajectoryReplayer 比较持久化记录，不能作为断点重新调度器。Evidence 的 revoke 与 legacy Document 查询不联动；Indexer 按 source_path 替换旧片段，活动指针本身不保证在线查询版本一致。Model Gateway、Prompt/MCP Adapter 并未统一接管现有业务。必须把这些当作实现起点，不沿用旧介绍文档的过度承诺。

本地 ragent HEAD `5f3c35e3` 仅提供通道、后处理、查询改写、预算和归因设计参考；不要求运行 Java、不复用其配置/秘密、不修改该仓库。旧变更 `adopt-ragent-engineering-patterns` 作为输入背景保留，新变更有自己的验收规格。

## Goals / Non-Goals

**Goals:**

- 三类任务共用持久化目标、类型化产物、受约束计划、验证反馈和恢复合同：组合选购、兼容排查、售后资格分析/本地草稿。
- 默认 offline 模式可在隔离本地数据库演示；agent 模式通过真实结构化模型调用提出合法计划、有限查询关注点与修订，模型调用失败有明确状态和安全回退。
- 明确区分规则决定、模型建议、用户口述与数据库/资料事实，每次完成有业务证据，而不是只有回答字符串。
- 新工作流复用现有 Harness、身份、Tool Gateway、Catalog、动作与交易服务；通过新增版本 API 隔离旧公共合同。

**Non-Goals:**

- 任意领域自动化、代码生成执行、OS 沙箱、P2P Agent、浏览器代购、外部退款/工单提交、企业文档上传平台。
- 新建另一套模型/身份/幂等/交易底座，或者以 Redis/MQ 为任务最终事实库。
- 无依据的质量/成本收益；外部调用与云 Trace 不因“实施方案”自动获授权。
- 所有已有 Planner 改为自主规划。旧默认路径与历史 single 模式保留兼容。

## Decisions

**D1 — 业务与模块归属。** 新增 `app/shopping_tasks/`（contracts、models、planner、scheduler、verifier、artifacts、worker、service、compatibility、diagnosis、after_sales）、`app/repositories/shopping_tasks.py`、`app/api/routes/shopping_tasks.py`、`app/schemas/shopping_tasks.py`、`frontend/src/features/tasks/`。允许按现有约定细分，禁止第二个 Harness。复用/扩展 `app/ai_platform/model_adapter.py`、`model_registry.py`、`resilience.py`、`app/recommendation/retrieval_pipeline.py`、`app/repositories/shopping_evidence.py` 与既有动作服务。新增 worker CLI 为 `scripts/run_shopping_task_worker.py`，统一启动脚本增加 task-worker 动作，Demo Prepare/Start/Verify 能启用本地 worker。

**D2 — 四类角色，代码与模型职责分开。**

| 角色 | 接收与交付 | 能力限制 |
| --- | --- | --- |
| coordinator | GoalSpec、已有产物、检查问题 → PlanProposal/PlanRevision 或澄清问题 | 可提议白名单只读任务，无直接 SQL、Cart、支付、外部 URL 能力 |
| catalog_analyst | 商品槽位/限制 → CandidateSet、BundleProposal | 调用 Catalog 与确定性求解，不编造 SKU/价格；兼容规则查询只读 |
| evidence_researcher | QuerySpec 与不可扩大的范围 → EvidenceBundle | 共用检索入口，至多有界子问题；不能修改权威范围或写业务数据 |
| reviewer | 方案/证据/规则报告 → VerificationReport 的解释性补充 | 规则否决不可覆盖，不能改价格/约束；不能只凭模型信心批准动作 |

旧 Preference Agent 不更名为当前需求 Agent。已保存偏好按明确读取工具接入，当前 GoalSpec 属于任务状态。预算计算、组合枚举、订单读取、草稿保存不单独建 Agent。售后与排查使用同四角色及专用只读能力。最终答案由可验证产物组织，不能把长篇自由文本作为后续写入参数。

**D3 — 新任务合同与权限。** `ShoppingTaskRequest` 包含 kind（bundle_selection/compatibility_diagnosis/after_sales_assessment）、用户目标文本、结构化已知条件及可选 thread/设备/订单选择器。owner 从现有 IdentityBoundary 绑定，禁止请求选择模型 endpoint、模式、预算、工具清单或角色权限。每条信息带 source（user_reported/catalog/order/policy/derived）、source_id/version、observed_at；用户声明不得被升级为可信订单事实。

`GoalSpec` 区分 required slots、硬条件、软要求、locked selections、excluded SKUs、当前问题与待补信息。`AgentTask/AgentResult` 复用既有身份关联模式，新增 schema_version 和 artifact refs；输出上限由角色能力定义。模型、资料中的指令和工具返回均为不可信输入，Pydantic extra=forbid 与 schema 检查之外还要执行权限、字段来源和事实校验。

**D4 — 计划校验与真实有界规划。** 新 planner 与旧 canonical planner 并存。offline 由规则给计划，agent 由共用 Gateway 调用结构化 Provider。允许模型选择只读能力、合法 dependencies 和带类型产物引用的后续输入，禁止自造 capability、owner、order_id、商品身份和资源 URL。计划最多 12 步、无环、依赖存在、必需验证步骤不可绕过；字段引用仅访问已完成的正确类型产物。Planner 无效输出最多一次修正机会（记预算），仍非法回退规则或返回需要澄清，不强行成功。无有效模型配置时 agent 模式 readiness 不得显示 ready；offline 可运行且 UI 标记模式。不更换用户环境或依赖付费云 Trace。

可执行能力包括 extract_goal、catalog_candidates、lookup_compatibility、retrieve_evidence、solve_bundle、read_owned_order、assess_policy、suggest_diagnostic_check、verify_result、compose_result。提议新增能力须经过服务端注册与测试，不接受模型下发函数名。prepare/confirm 是业务边界，不属于任意 Agent 的可执行工具。

**D5 — 依赖执行与修订。** 每次从当前合法计划选取依赖均已完成的就绪前沿，最多并行 3 个只读步骤。复用旧隔离结果/使用量合同但新增 DAG 调度，不直接把带依赖计划传给旧并行执行器。每一成功输出不可变并记录输入指纹、能力/Prompt/模型配置版本、引用证据版本。Reducer 只能接受当前 task、plan revision、step、lease token 的完成结果，按步骤顺序生成展示投影，不按线程返回顺序决定业务语义。

VerificationReport 包含 status=pass/repairable/needs_input/rejected、问题 code、affected step/artifact/SKU、缺失事实和允许修复动作。规则先检查预算/币种、必需槽位、SKU/库存、兼容三态、有效引用及 owner；Reviewer 只补解释完整性、需求覆盖和引用支撑问题。局部修订使受影响步骤及其依赖后代失效，保留其余有效结果。用户降低预算等行为生成 goal version 与新计划 revision，陈旧行动预览立即失效。未变化产物若可售/证据事实已过期也须重查，不能单靠输入文本指纹复用。

最多 2 次修订。无进展指纹由目标、槽位候选、关键事实版本、验证问题集合与查询集合规范化计算，忽略 run ID、自然语言改写和时间戳。重复出现而没有新事实时进入部分结果/澄清/失败，不另起无限新任务。暂时工具故障最多 2 次尝试；验证不通过是业务修复，不能伪装成传输重试绕过预算。缺乏结构化事实不能靠换模型得到 pass。

**D6 — 可持久化状态与存储。** 从实际 Alembic head 之后增加线性迁移，不预定一定是 0018、不改旧迁移语义。建议对象：

| 对象 | 关键内容与约束 |
| --- | --- |
| shopping_tasks | UUID、owner、kind、thread、goal/version、status、mode/config snapshot、budget ledger、active revision、timestamps、expiry、cancel flag；按 owner 查询 |
| shopping_task_plans | task + revision 唯一、validated plan、reason、fingerprint、parent revision；不可变 |
| shopping_task_steps | task + revision + step key 唯一、deps、typed input refs/hash、status、attempt count、lease token/epoch/deadline、output ref |
| shopping_task_attempts | step + attempt 唯一、run/trace correlation、model/tool/latency/usage、error code、started/finished；晚到 attempt 可记诊断但不得改变业务结果 |
| shopping_task_artifacts | task + version + kind、bounded typed payload、source refs/version/hash、verification status、superseded 标志；禁止任意文件路径或可执行产物 |
| shopping_task_events | task + monotonic sequence 唯一，闭合事件类型、安全投影、created_at；与业务状态迁移同事务 |
| shopping_task_commands | owner+task/operation+Idempotency-Key 唯一、request hash、结果引用；创建任务使用 owner+operation+key |
| shopping_task_actions / after_sales_drafts | 复用 PendingAction 类型扩展或薄关联表，绑定 task/goal/plan/artifact version；本地草稿绑定本人订单且明确 draft_only |
| catalog_compatibility_rules / policy_rules | 固定字段、来源与有效版本，三态兼容/结构化政策；不能存任意模型生成规则后自动执行 |

task 状态 queued/running/waiting_input/awaiting_approval/succeeded/failed/cancelled/expired。step 状态 pending/running/completed/failed/skipped/superseded。允许规则明确的迁移，terminal 不能被旧 worker 改回 running。返回结果 outcome 与任务状态分开：组合可 recommended/no_solution/needs_information；排查可 resolved/unresolved/needs_information；售后可 eligible/ineligible/conditional/unknown。

task.version 是交互/控制版本，在用户命令、计划替换、取消/终态等控制迁移时增长；并行步骤完成、预算记账和普通进度事件不递增它，使用各自 step version 和 event sequence。否则一个合法分支完成会把同前沿其他分支全部变成陈旧结果。Reducer 同事务锁定当前 task，核验交互版本/goal/plan/epoch，再安全合并步骤输出和预算；普通进度不得覆盖交互字段。

终态 succeeded 不等于资格 eligible，也不等于已发生交易。固定迁移：创建 queued→领取 running；缺用户事实 running→waiting_input，合法 inputs→queued；组合方案或可保存本地草稿通过验证后，由应用准备动作预览并进入 awaiting_approval（准备本身不写 Cart/Draft）；确认成功或用户明确拒绝→succeeded，拒绝只结束任务并保留分析，无业务副作用；awaiting_approval 中修改条件先失效旧动作再→queued。排查已解决/有明确未解决解释、组合在已检查范围无解、没有可生成草稿的售后未知分析可直接→succeeded 并返回相应 outcome。fatal/budget→failed，用户取消→cancelled，到期→expired。

终态不接受 inputs/resume；用户要修改已终结任务时 POST 新任务并带经过 owner 校验的 parent_task_id，复制明确条件而不复制预算、授权或已失效产物。新任务有自己的幂等身份，服务端用户/全局准入仍生效，不能作为原任务内部绕过修复次数的自动手段。`actions` 准备接口只在当前 awaiting_approval 返回/更新同一有效预览，过期预览先重新验证再生成；不从 succeeded 重开任务。resume 仅用于 queued/running 且无有效 worker lease 的恢复请求（已有效 running 则返回原状态不重复调度），waiting_input 必须通过 inputs 补齐，不准跳过澄清。旧 worker 永远不能更改终态。

**D7 — worker/恢复/取消的原子性。** API 创建任务/指令后立即提交，返回 202。独立 worker 使用 PostgreSQL SKIP LOCKED 短事务获取任务执行租约，再按就绪步骤领取 attempt；一次任务只允许一个有效 scheduler epoch，其内部步骤可以并行。lease 默认 30 秒，10 秒心跳续租，token-specific CAS 释放。外部模型和 embedding I/O 全在事务外；产物、状态、预算实际结算与事件在短事务中提交。提交检查 task version、plan revision、epoch、lease token、cancel/expiry，失租结果不可提交。

在领取时持久化预算预留与 attempt 标识；worker 崩溃时不能返还已发出的未知外部调用消耗，记录 usage_unknown 并保守计入调用上限。继任者只重试幂等只读步骤，同一业务写入靠 Action Resolution 恢复，不重新调用业务动作。已完成步骤在引用版本仍有效时复用，running 失租重领；没有必要重新执行整次任务。RuntimeTrajectoryReplayer 留作事实对比工具，不承担调度恢复。

累计上限：36 step attempts、24 model attempts（含 planner/reviewer/改写与失败），2 plan repairs、5 人工澄清/排查轮次，artifact 总 payload 512 KiB，单角色结果 64 KiB，首版每任务最多 1000 个公共事件。活跃回合 deadline 默认 120s、上限 300s；人类等待不计活跃墙钟但 task 绝对过期默认 24h，结果 retention 默认 7d，可由服务端收紧。用户恢复不能重置累计预算。token 默认最大 60000；未知 usage 保留 null，不当零；需由 provider 预留上限/服务端调用限制兜底，禁止承诺外部账单硬上限。预算不足返回 budget_exceeded 与可保留产物。

active turn deadline 领取回合时持久化，进程重启或 queued/running resume 沿用原 deadline；只有合法 waiting_input/awaiting_approval 的新用户输入才开始新回合，仍保留任务绝对 expiry 与所有累计计数。超时后迟到调用只作安全诊断，不发布产物。历史 command 结果保留至 task retention 结束以支持响应丢失重放。

取消持久化后停止发出新步骤，迟到只读结果不发布。取消与写动作确认在同一任务锁/版本序列化：取消先提交则确认拒绝，确认先提交则保留已确认事实，取消返回“动作已执行”而不是假装回滚。断开 SSE 只停止观察，不自动取消任务。删除任务/owner 先使 epoch 失效并取消待执行动作，工作进程不得重新创建被删除数据。

**D8 — API 与前端合同。** 新路由前缀 `/api/shopping-tasks`，复用现有身份依赖和 public error projection：

| 方法与路径 | 语义 |
| --- | --- |
| POST `/api/shopping-tasks` | 创建 typed task，必需 Idempotency-Key，202/重放原任务；不能指定执行模式 |
| GET `/api/shopping-tasks`、`/{id}` | 本人分页列表/安全快照；含 version、mode、status、output、pending interaction，不含 Prompt/原始工具参数 |
| POST `/{id}/inputs` | expected_version + 有类型条件 patch/排查反馈/缺失事实回复；提交后排队，陈旧 409 |
| POST `/{id}/cancel`、`/{id}/resume` | 幂等命令；resume 仅用于可恢复暂停/中断且未过期任务，不重置预算；缺待补字段时不得强行恢复 |
| GET `/{id}/events?after_sequence=N` | fetch 流式 SSE，支持受信头认证、Last-Event-ID/游标；历史缺失返回事件过期语义并要求刷新快照 |
| POST `/{id}/actions` | 在 awaiting_approval 获取/更新当前 verified artifact 的白名单预览，客户端只能选 artifact/action type/允许 edits；陈旧或过期内容先重验 |
| POST `/{id}/actions/{action_id}/confirm` | explicit confirmed、expected task/artifact/action version、Idempotency-Key；原子业务写入及结果重放 |

所有 command 相同 key 同 body 返回原结果，不同 body 409；owner mismatch 对资源读取使用同样 404，身份错误沿用 401/403。分页 1..100，游标不授权，公开错误不泄露原始异常。所有写命令更新事件与任务版本，快照含 last_sequence，客户端可先加载快照再订阅其后的事件。SSE 不暴露 chain-of-thought，仅步骤与验证理由。

新增 `/tasks` 列表、`/tasks/:id` 详情，复用现有 UI/Query/client/身份与动作组件。任务页包含目标、计划、步骤与修订、方案对比/总价、证据抽屉、验证问题、澄清/反馈、确认卡片、取消/继续。页面明确区分 offline/agent、规则结果/模型建议、用户口述/已验证事实。旧 Chat 可提供进入任务页入口，不能私自改变旧 ChatResponse；OpenAPI 重新生成。

**D9 — 业务数据与三场景实现。** 增加 `dock` Category Schema/seed/显示字段，使目录为 11 类但旧十类正常。隔离演示种子至少提供 4 个笔记本 SKU、4 个显示器 SKU、4 个扩展坞 SKU（可复用已存在符合条件的 SKU），明确接口输出/输入、供电能力和组合关系，至少覆盖可行、超预算、不兼容、缺字段、缺货、重复型号。兼容规则来源为受控数据，不让模型从 USB-C 名称猜能力。

组合每槽位最多 5 候选、三个槽位枚举最多 125 组合、最多展示 3 方案，按确定性预算/硬兼容校验与评分排序。同 SKU 按数量汇总，不重复占位；locked SKU 必须保留，若不再可行返回原因。达到候选上限必须记录 search_truncated=true；no_solution 表述限定为当前已检查候选，不能声称全市场/全 Catalog 不存在方案，预算允许时可补一轮候选，否则说明覆盖限制。

排查基于一套 schema 化安全步骤与受信资料，记录 asked/answered/ruled_out/hypothesis refs，最多 5 反馈轮。结论受用户观察和证据约束，不能将模型建议标记为物理测试完成。停顿期间 worker 不占线程/租约。停电/设备损坏/拆机建议不在本期执行范围，给出人工服务方向。

售后使用已有 owner Order/Payment reads；新建最小事实 envelope 区分可信系统事实和 user_reported。明确送达/拆封字段未实现真实物流来源时不可自动判 verified eligible。结构化 policy_rules 与当前发布文档版本关联且经受信导入，不能直接执行 LLM 提取规则；不存在规则/版本/必要事实时 unknown/conditional。修复或隔离现有 `evaluate_order_policy_eligibility` 默认 14 天及未来日期问题。草稿保存为本地业务记录，不调用外部服务，不修改 Order/Payment。

**D10 — RAG 以贯通业务为验收。** 新任务一律经 `RetrievalPipeline`；保留原问题与 validated QuerySpec，最多 3 个子问题，允许一次针对缺口的补查（计入任务/检索预算）。QuerySpec 明确 schema_version、product IDs/SKU、category、compatibility pair、policy type、region/channel 与证据版本策略，所有 Channel 共用范围。不能靠给返回文档补一个 requested evidence_type 就证明原资料属于该类型。

顺序：验证范围/活动版本 → 有界并行 Vector/Lexical → 规范身份并聚合各通道独立名次（保留来源，不先抹掉跨通道排名）→ RRF → 可选 Rerank → 必需业务门控 → CitationProjection。旧兼容 RRF 使用 k=60 时保持，调整需新版本与对照，不能误用 helper 默认 k=20。共享绝对 deadline、通道并发池、候选池与最终条数上限；future 等待不能让每个通道重复获得完整总时间，超时不等于线程已终止，底层连接须有 timeout，晚到结果忽略。

必需门控检查真实商品关联、SKU/品类/兼容组合、政策地区/渠道、valid_from/until、active publication。元数据缺失在已限制范围请求中不能默认 wildcard；旧资料只能经过受信映射导入后参与受限任务。规则异常/来源不明→no trusted evidence，阻止肯定结论；reranker 或一条非必需通道失败可 degraded 保留已验证证据。空命中、超时、不可用、禁用分开记录，不能全部算 empty。

Document 增加 evidence_version_id 的可索引关联（或等价专用 chunk 表），新版本先写 staged chunks，再在一个数据库事务内切 active pointer；任意新请求只读当前发布版本的片段。撤销使新检索立即不可见，异步物理清理可滞后。已有引用保留版本供审计但标 stale，写动作确认前重验。legacy 导入完成前不得默认把旧全库检索结果混入新任务；旧推荐切流需 migration/backfill/fallback 明确可见状态，不隐式退回未校验片段。embedding provider/model/dimension 从真实配置记录，禁止硬编码另一个模型名；embedding I/O 不包长数据库锁事务。

scope gate 前后与 citation projection 都接受 server-owned ids，不接受模型生成 URL/ID；文档/工具中的指令不扩权。正向路径必须实际调用 pgvector/词法 Repository，不只 FakeEvidenceIndexer。无需强制 CrossEncoder/MCP/图谱/ES；真实模型启用后才用模型改写，失败保留原问题与范围。

**D11 — 模型与工程生命周期。** 新 task planner/reviewer/受限改写由应用/worker 生命周期共享 ModelCandidateRegistry/Gateway，正确选择候选对应 Provider（现有 wrapper 若忽略 candidate 必须修复）。熔断状态不能每次创建 Gateway 就重置。OperationAdmission backend 要共享应用生命周期，验证 global/operation/subject 各维度可执行，不把现有“带 operation 的指纹”误当三个独立配额已完成。只读 worker 调用复用预算与 Tool Gateway；租约续租实际接线并覆盖释放异常。

本期默认非逐 token 模型结果，先验证再发布可见产物；SSE 只报告阶段，避免展示未验证的模型内容。必须区分阶段事件已发送与模型文本开始发送，不能因为 run.started 就误禁所有候选回退。如果未来 token streaming 才增加不可拼接语义。本期网关连接/调用 timeout 用真实 transport 配置而非仅返回后计时；不可强杀同步调用的边界需显式处理并丢弃迟到结果。

**D12 — 写动作及旧安全边界。** 新 action type：add_bundle_to_cart、save_after_sales_draft。只由应用从 verified current artifact 创建预览，绑定 owner/task/goal version/plan revision/artifact hash/action version/TTL；默认 30 分钟，任务失效、目标改变或关键证据撤销使动作失效。禁止把原单 SKU confirm 循环调用三次模拟原子组合写入。组合确认锁 task/action，按稳定 SKU 锁读取可售、价格、库存，任何一项失败整组回滚；同事务 Cart upsert、resolution/event 提交。确认时价格变化返回 stale/price_changed 要重新预览，不能悄悄按更高价写入。Cart 仍不预占库存。

明确拒绝/过期/取消不写业务；相同确认重放必须先找到原成功 resolution，即使当前 task version 已因成功推进也返回原结果；不同 body 同 key 冲突。业务写不能在无有效 task/action fence 的后台旧 epoch 中执行。保存草稿不修改支付和售后资格，字段来自 artifact 与允许用户确认的声明；草稿结果不得使用“退款已提交”等措辞。既有 chat confirm、单商品 pending action、订单、支付和 Outbox 回归不变。

草稿的 verified/pass 表示内容完整、来源标注正确且允许本地保存，不表示售后资格 eligible；conditional/unknown 的分析也可形成明确标注待补事实的合法草稿。确认时对关键证据活动指针与规则版本执行事务内校验/适当锁定，与撤销形成确定的先后关系，不能只在事务外读一次后直接写入。组合数量校验必须包含已有 Cart 数量，沿用现有数量上限和合并语义。

**D13 — 验收层次与量化。** 新增至少 24 个固定任务案例（10/6/6/2），另加上述安全、并发、恢复、索引撤销负例；每例有数据快照、expected outcome、必要规则与引用、允许写入、plan/step/artifact 检查和复现命令。offline 回归、Provider stub、真实 PG 检索、真实 API/browser、获授权真实模型分层报告。至少三种任务各保留一条真实模型轨迹，外部调用必须获授权；未获授权列为阻塞实测，不阻塞其他实施但不能勾整体验收全完成。模型建议与最终执行轨迹须能证明不同任务的步骤/依赖/局部修复不同，不用输入关键词返回预制 JSON 冒充 agent 模式。

可选 single-agent 对照使用相同模型/工具/数据/预算，结果据实，不要求 multi 必胜；不以旧 synthetic-ablation 成本系数代替测量。本期交付门槛是明确业务场景正确、动作安全和可恢复，非虚构成功率或成本下降。

## Risks / Trade-offs

- [范围扩大] → 三种固定任务、三个组合槽位、固定能力白名单；外部执行与通用 coding 不在范围。
- [数据缺口导致模型猜兼容] → dock/接口受信样例和三态规则先行，缺事实必须 unknown。
- [旧完成清单过度描述] → A 阶段建立调用链证据与缺口回归，逐项证明接入而非只统计类。
- [双 worker/旧请求覆盖] → 持久 task epoch、step lease token、goal/plan versions，多条件提交与事务事件。
- [取消与确认竞态] → 共用锁序与版本序列化，已提交事实不假装撤回。
- [晚到模型调用与费用] → transport timeout、迟到拒绝、累计调用上限、usage unknown 标识，不宣称硬杀调用或绝对成本上限。
- [检索降级放过关键检查] → mandatory gates fail closed，可选排名才降级；撤销过滤由数据库事实保证。
- [售后数据缺失] → user_reported 与已验证事实分离，条件性分析与本地草稿，不假造物流或退款。
- [删除后 worker 复活数据] → 先 fence/cancel，所有后续写关联仍存活 task；owner-data/retention 处理新增表及产物。
- [过早平台化] → 复用现有单体、PostgreSQL worker、版本 API，复杂业务真实贯通后再考虑扩展依赖。

## Migration Plan

按总方案 A→F 和 tasks 执行。新增迁移先在私有 schema 验证 upgrade/downgrade/upgrade，现有 shared DB 不自动清库。变更 Document 版本关联需要受信回填与覆盖报告，不能 delete-all 重建索引。新 dock 数据以可复现隔离 seed 提供，已有用户数据不被重写。新配置建议 `SHOPMIND_TASKS_ENABLED=false`、`SHOPMIND_TASK_EXECUTION_MODE=offline|agent`，值仅服务端设置；新功能关闭不影响旧 Core Demo，任务 Demo 显式开启。

发布顺序：baseline → schema/数据 → worker 与新 API → offline 新路径 → 原子动作 → UI → 模型模式授权验证 → 旧 RAG 受控切流。全程保持一个 migration head，更新 health/readiness/OpenAPI/文档。agent 模式必须检查配置和能力可用性；禁用可选后端保持 disabled。worker 不可用时任务保持 queued 且 UI 显示，不用 API 同步强跑绕过恢复合同。

回滚先关闭新任务准入，取消/排空新 worker，保留历史产物/动作已提交事实；降回旧应用仅在 schema 向后兼容与旧检索资料仍有效时进行。不要自动 downgrade 有业务数据的表。RAG 回滚仍需活动版本/撤销检查，不能恢复到会暴露已撤销证据的路径。记录配置回滚、queued/running/waiting/confirmed 各状态和数据库断言，作为交接的一部分。

## Remaining Closeout Plan（67/75 → 75/75）

本节只规划当前未完成的 8 项，不改变既有 specs。实施严格按 C1→C6 顺序推进；上游门禁未通过时不得勾选下游任务。

### C1 — 旧推荐检索受控切流（2.13）

**目标。** 让旧推荐 RAG 与新任务共享 `RetrievalPipeline` 的 scope、活动版本、mandatory gate 和 CitationProjection，同时保持旧 `RecommendationResult` 字段、排序与错误合同不变。

**代码触点。** `app/recommendation/rag.py` 增加 server-owned `legacy|shadow|shared` 模式；`shared` 只消费通过活动发布/version/scope gate 的候选，`shadow` 同时执行旧路径但只记录脱敏差异。`app/repositories/documents.py` 保留旧查询函数作为显式 rollback adapter，不允许 shared 失败时静默回退未校验片段。

**验证。** 固定语料比较旧/shared 的 product IDs、evidence IDs、policy applicability 与 public schema；真实 PostgreSQL 验证 revoked/version-stale 文档在 shared 和 rollback 后都不可见。回滚只切配置，不改索引、不移动活动指针。

**完成门禁。** 旧 API/OpenAPI 零漂移；shadow 报告标明差异；shared 与 rollback 都通过撤销测试；task 2.13 才可勾选。

### C2 — 动作并发与草稿事务闭环（4.11）

**目标。** 将 task action 的 prepare/confirm 从路由内逻辑收敛到事务 service，统一 task→action→SKU/draft 锁序和 ResolutionRecord。

**代码触点。** 新增/完善 `app/shopping_tasks/actions.py`：确认入口先按 owner/action/idempotency key 查已提交 resolution，再检查 expected versions；组合锁序固定为 task、action、排序后的 SKU/inventory/cart；草稿锁序固定为 task、action、owner-order、draft。所有业务写、action 终态、resolution、event 在同一事务提交。

**验证矩阵。** 两连接并发确认、取消先/确认先、提交成功响应丢失重放、同 key 不同 body 冲突、第三个 SKU 库存失败全回滚、价格变化拒绝、草稿重复确认只生成一行、草稿确认不改变 Order/Payment。

**完成门禁。** 私有 PostgreSQL 全部竞态有数据库断言；无部分 Cart、重复 Draft 或假回滚；task 4.11 才可勾选。

### C3 — 结果工作台与 SSE 客户端闭环（4.15、4.16）

**目标。** 用类型化 UI 代替 raw JSON，并实现断线恢复、409 刷新和稳定幂等键。

**代码触点。** `frontend/src/features/tasks/` 增加 BundleComparison、EvidenceDrawer、VerificationIssues、DiagnosisFeedback、AfterSalesAssessment、TaskActionCard；每种事实显示 source/status/version。新增 task event client：先 GET snapshot，使用 `last_sequence` 订阅 SSE；按 sequence 去重，网络断开指数退避；410 清 cursor 后重新拉 snapshot。mutation 的 idempotency key 存于 sessionStorage，收到终态或 body 变化才清理；409 自动刷新 snapshot，不自动重放不同 body。

**失效语义。** goal/plan/artifact version 改变时旧方案和 action 卡片标为 stale；offline/agent/fallback 必须显式显示。浏览器不展示 Prompt、CoT 或原始工具参数。

**完成门禁。** Vitest 覆盖 reducer/idempotency/409/410；mocked Playwright 覆盖重连去重和旧方案失效；tasks 4.15、4.16 才可勾选。

### C4 — 三场景真实浏览器链路（5.7）

**环境。** 使用 `scripts/prepare_shopping_task_demo.py` 创建唯一私有 schema，显式 seed task-only dock/compatibility/policy 数据；API、worker、Vite 全部绑定该 schema。测试完成只停止进程，不删除 schema，保留可复查事实。

**场景。** Bundle：缺预算→waiting_input→补预算→兼容冲突→局部 revision→刷新/重连→确认加购并核对 Cart。Diagnosis：安全问题→用户观察→不重复提问→刷新继续→resolved/unresolved。After-sales：本人订单/政策→缺送达事实→user_reported 补充→conditional draft→确认/重放并核对 Order/Payment 不变。

**完成门禁。** 三场景都必须经真实 UI→API→worker→PostgreSQL；检查 task/plan/step/artifact/event/action/draft/cart 行；task 5.7 才可勾选。

### C5 — 生产门禁与回滚演练（5.9、5.10）

**Preflight/readiness。** 当 task 功能 disabled 时返回 not_applicable 且旧路径 ready；enabled+offline 要求 migration head、worker heartbeat、PostgreSQL 和 coordination ready；enabled+agent 还要求 Model Gateway 至少一个 structured planner/reviewer candidate ready。公开 health 只返回闭合 reason，不泄露 URL/model key/异常。

**回滚演练。** 先关闭新准入，再停止 worker 新领取，等待有效 lease 结束或明确取消；保留已确认 Cart/Draft 和历史 task/artifact/event；不得自动 downgrade `0018`。RAG 回滚切到受控 legacy adapter，但继续执行 revoked/version gate。分别断言 queued、running、waiting_input、awaiting_approval、succeeded 的结果。

**完成门禁。** preflight/readiness 单元与真实 DB/Redis 检查通过；release-operation gate 记录演练结果；tasks 5.9、5.10 才可勾选。

### C6 — 获授权真实模型验收（5.11）

**配置。** `WORKSHOP_MODEL` 必须带 LangChain provider 前缀，例如 `openai:deepseek-ai/DeepSeek-V4-Flash`；OpenAI-compatible provider 使用 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。`SHOPMIND_SHOPPING_TASK_MODE=agent` 仅由服务端设置，LangSmith 保持关闭，除非另行授权云 Trace。

**执行。** 三种 task 各运行至少一条去敏轨迹；至少一条必须因具体 VerificationIssue 产生合法局部 revision。每条记录 candidate/model/config/prompt/corpus 版本、Gateway attempts、fallback、usage（未知保持 null）、plan/steps/artifacts 与业务结果。

**失败处理。** provider 不可用、模型 ID 不存在、结构化输出不合法或额度不足时保持 5.11 未完成；不得用 stub/offline fallback 冒充成功。修正配置后复跑同一固定案例，不改 expected outcome 迎合模型。

**完成门禁。** 三条真实 provider 成功轨迹、一次真实局部 revision、无越权工具/写入、所有规则 gate 通过后，task 5.11 才可勾选。

### Closeout order and stopping rule

1. C1、C2 可并行开发，但各自 PostgreSQL 门禁独立通过。
2. C3 依赖稳定的 API/action schema；完成后再执行 C4。
3. C5 在 C1–C4 完成后演练，避免门禁覆盖未稳定行为。
4. C6 最后执行；外部 provider 失败只阻塞 5.11，不回滚已通过的工程项。
5. 仅当 75/75、OpenSpec strict validation、单一 migration head、全量后端/前端/PG/Redis/browser 门禁全部通过时，才能声明 change 完成并进入 archive；发布、部署和 tag 仍需独立授权。
