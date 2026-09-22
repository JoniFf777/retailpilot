## 1. 基线、合同与持久任务基础（阶段 A/B）

- [x] 1.1 阅读 AGENTS/本机 runbook/本变更全部材料，记录实际 HEAD、相关 dirty diff/未跟踪文件摘要与工具版本，保护既有用户改动。
- [x] 1.2 运行现有模型无关聚焦回归、记录数据库/API/前端基线；复核旧 72/72 清单与实际调用链差异，建立 gap-to-test 表。
- [x] 1.3 定义三种任务的 GoalSpec、PlanProposal、PlanRevision、StepResult、Artifact、VerificationReport、ActionPreview 合同与来源/版本字段。
- [x] 1.4 定义四类角色与能力/工具权限矩阵，校验禁止 arbitrary code/URL/owner/model 参数和额外字段。
- [x] 1.5 固定任务/步骤/动作状态迁移、终态后新建 parent task 语义、累计预算与 expiry/retention 配置，建立状态合同测试。
- [x] 1.6 增加任务、计划、步骤、尝试、产物、事件、命令及必要动作关联的线性迁移，在私有 schema 验证约束和升降级。
- [x] 1.7 实现 owner-scoped Task Repository、命令 key/hash 幂等与 expected-version 冲突，含已成功请求重放优先级。
- [x] 1.8 实现 task scheduler epoch、步骤 lease/token、SKIP LOCKED 领取、心跳续租和条件完成提交。
- [x] 1.9 实现产物不可变保存、输入/依赖/证据版本指纹、分支归属校验与事务事件序号。
- [x] 1.10 实现持久预算预留、实际消耗和 unknown usage，重试/重启/输入恢复不能重置配额。
- [x] 1.11 实现 worker CLI 与进程生命周期，外部调用不持有长数据库事务，停机停止新领取并安全处理失租。
- [x] 1.12 接入现有 Harness/Run/trace correlation 与 Tool Gateway，避免第二套运行/身份实现。
- [x] 1.13 修复或适配协调工厂共享生命周期，验证 global/operation/subject 限额、续租与异常释放，显式 Redis 配置有等价集成验证。
- [x] 1.14 实现取消、过期与删除 fencing，并将新增表/产物/草稿纳入 owner-data inventory/delete 与 retention。
- [x] 1.15 使用真实独立 PostgreSQL 会话验证双 worker、过期租约、迟到结果、删除中运行、预算与事件一致性，不用内存替身代替。

## 2. 业务数据与 ragent 模式的 Python 检索贯通（阶段 C）

- [x] 2.1 只读核对总方案列出的 ragent 类和许可，记录借鉴点与不同失败语义，不修改 Java 工程或读取其秘密配置。
- [x] 2.2 增加 dock Category Schema、目录/规格展示支持和隔离种子，保留原十类回归。
- [x] 2.3 准备至少 4 laptop/4 monitor/4 dock SKU、预算/库存负例与接口/供电事实，真实编号统一映射到 Catalog。
- [x] 2.4 实现三态兼容规则及来源/版本，覆盖已知支持、不支持、缺字段，并禁止从 USB-C 名称猜结论。
- [x] 2.5 增加受信兼容/排查/政策语料与结构化 policy_rules，明确有效期、地区/渠道和系统事实/用户声明来源。
- [x] 2.6 增加 Document/Chunk 到 EvidenceVersion 的版本关联及受控 legacy 回填，记录 provider/model/dimension，禁止 delete-all 重建。
- [x] 2.7 实现 staged indexing 与发布事务、当前活动版本过滤、撤销立即不可见；验证失败时旧版本完整可见。
- [x] 2.8 将新任务证据入口接到真实 RetrievalPipeline，统一不可扩大的 QuerySpec、原问题、最多 3 子问题与一次补查预算。
- [x] 2.9 实现共享绝对 deadline、真实 transport timeout、有界 Channel executor 和 Vector/Lexical 归因，区分 empty/unavailable/timeout/disabled。
- [x] 2.10 固定 RRF 兼容参数与稳定身份，重排只能使用可信原候选；必需范围/版本/政策 gate 异常 fail closed。
- [x] 2.11 实现安全 CitationProjection、版本失效展示和任务确认前引用重验，拒绝文档指令注入、伪造 ID 与跨商品污染。
- [x] 2.12 使用真实 PostgreSQL/pgvector 文档查询验证检索、活动版本切换/撤销、元数据缺失与重排故障，不以固定排名作为验收。
- [x] 2.13 在保留旧公共合同的前提下，将旧推荐检索受控迁入安全共享入口并记录对照与回滚结果；未迁移资料不得静默返回不可信片段。

## 3. 受约束多 Agent、检查修订与步骤恢复（阶段 D/E 的执行层）

- [x] 3.1 实现新任务离线规则 Planner，并为三个任务生成不同依赖计划，旧 canonical planner 保持兼容。
- [x] 3.2 实现服务端计划验证：白名单、环检测、依赖存在、产物类型/字段引用、必需检查节点、规模和权限边界。
- [x] 3.3 实现协调者的结构化模型提案 Adapter，可在允许能力内选择步骤/依赖，而非仅给固定计划增加 query_focus。
- [x] 3.4 将 Planner/Reviewer/可选查询改写实际接入共享 Model Gateway，候选切换选择真正对应的 Provider，熔断状态跨调用保存。
- [x] 3.5 实现模型调用前预算预留、失败计费/未知 usage、transport deadline、迟到结果丢弃和模式/回退可见状态。
- [x] 3.6 实现按依赖就绪前沿调度，最多三个独立只读步骤并行，分支隔离、类型化交接和稳定归并。
- [x] 3.7 将 Catalog/兼容/证据/本人订单等现有能力接成窄工具，验证角色 allowlist 与用户归属。
- [x] 3.8 实现确定性 VerificationReport，问题关联具体条件、SKU、证据和受影响产物，缺事实保持 unknown。
- [x] 3.9 实现模型 Reviewer 的受限补充检查，不能覆盖规则失败或自行执行任何写操作。
- [x] 3.10 实现最多两次局部计划修订，失效受影响依赖后代，保留仍有效的锁定选择和完成产物。
- [x] 3.11 实现无进展指纹、累计步骤/模型/交互上限和明确终止原因，区分传输重试与业务修订。
- [x] 3.12 实现 waiting_input/awaiting_approval 时释放工作资源、用户补充事实后恢复及终态拒绝复活。
- [x] 3.13 实现真正的中断恢复：重新领取未完成步骤，校验已有产物新鲜度后复用，不用轨迹比较冒充续跑。
- [x] 3.14 通过模型替身故障测试覆盖非法计划、循环、越权、Reviewer 错判、模型候选耗尽、取消和数据注入；报告明确标 stub。
- [x] 3.15 记录新任务入口→规划→工具→检索→检查→修订→结果的实际调用证据，确认不是仅创建未接入组件。

## 4. 三场景业务、确认动作与前端工作台（阶段 D/E/F 的产品层）

- [x] 4.1 实现组合 GoalSpec 提取、预算/必需槽位澄清、锁定/排除和用户后续修改，按来源区分本次条件与已保存偏好。
- [x] 4.2 实现每槽最多五候选、最多 125 组合的确定性求解，最多三方案，输出币种/总价/兼容/评分/引用与 search_truncated。
- [x] 4.3 实现明确不兼容后的定向替换与未知兼容澄清，不能自行放宽硬条件，no_solution 限定实际搜索范围。
- [x] 4.4 实现连接排查状态、受信检查步骤、用户观察/已排除原因和最多五轮继续，不重复问已回答问题。
- [x] 4.5 实现排查无进展、资料缺失和不在安全范围时的 unresolved 输出与人工建议，禁止远程设备操作。
- [x] 4.6 实现本人 Order/Payment 读取与政策资格分析，修复或隔离旧默认十四天和非法日期逻辑，缺送达事实仅 conditional/unknown。
- [x] 4.7 实现本地售后草稿合同和存储，不新增外部工单、退款或伪造物流；草稿保留 user_reported 标识。
- [x] 4.8 扩展 PendingAction/Action Registry 支持组合加购和本地草稿，绑定 task/goal/plan/artifact/action version 与 TTL。
- [x] 4.9 实现组合确认的短事务重验、稳定 SKU 锁序、Cart 合并数量检查、整组原子写入与 ResolutionRecord；禁止循环提交单品模拟原子性。
- [x] 4.10 实现价格/库存/引用版本变化后的拒绝与重新预览，动作修改/拒绝/过期/取消不产生非预期副作用。
- [x] 4.11 实现草稿确认保存与重复确认重放；真实 PostgreSQL 验证取消与确认竞态、并发确认、响应丢失和单项失败全回滚。
- [x] 4.12 实现 `/api/shopping-tasks` 创建/列表/详情/inputs/cancel/resume/actions/confirm，统一认证、幂等、分页、版本错误和关闭模式。
- [x] 4.13 实现持久事件游标 SSE、快照 last_sequence、过期游标语义及脱敏投影，断开不取消任务。
- [x] 4.14 更新 OpenAPI 并生成前端类型，新增 `/tasks` 与 `/tasks/:id` 路由以及旧 Chat 的显式任务入口。
- [x] 4.15 实现组合结果对比、证据与问题、排查反馈、售后分析/草稿、动作确认，区分 offline/agent 与事实来源。
- [x] 4.16 实现前端幂等 key 保留、409 状态刷新、SSE 重连去重、取消/继续与旧方案失效展示。
- [x] 4.17 更新统一启动脚本和任务 Demo Prepare/Start/Verify，检查 worker 就绪与配置；旧 Core Demo 不强制启用新功能。

## 5. 验收、文档、回滚与新窗口交接（阶段 F）

- [x] 5.1 建立至少 24 个任务的版本化验收目录（10 组合/6 排查/6 售后/2 跨场景），逐例明确预期结果、产物、依据和副作用。
- [x] 5.2 为每份 spec 的每个 Scenario 建立 test/case 映射，补齐并发、失租、门控异常、引用撤销和已终态操作负例。
- [x] 5.3 运行模型无关单元/API/角色/计划/检索聚焦测试，记录真实结果和 warning，不复用历史总数。
- [x] 5.4 在隔离数据库运行新增与受影响 migration、任务恢复、数据删除、兼容、证据发布/撤销和动作原子性集成。
- [x] 5.5 若启用 Redis，运行跨客户端准入/续租/速率/释放验证，证明实例共享语义而不是只通过单对象测试。
- [x] 5.6 运行前端 unit、lint、typecheck、build、bundle budget 与必要 mocked E2E。
- [x] 5.7 运行三个场景真实浏览器→API→worker→数据库链路，验证重连、输入继续、方案修订、确认与实际数据变化。
- [x] 5.8 回归旧推荐、Chat/Confirm/SSE、身份/owner-data、Cart/Checkout/Order/Mock Payment/Outbox 和既有评测门禁，记录兼容性证据。
- [x] 5.9 扩展 production preflight/live readiness，检查新 migration、已启用 task mode/provider/worker 和共享协调，禁用可选能力不阻断旧路径。
- [x] 5.10 演练关闭新任务准入、排空/取消 worker、保留已确认动作与证据撤销约束的回滚，不自动 downgrade 用户数据。
- [x] 5.11 在取得明确授权后执行三种任务各至少一条真实模型轨迹，覆盖一次合法局部修订；未授权或不可用时保持本项未完成并记录原因。
- [x] 5.12 分层报告 offline、stub、真实 PostgreSQL 检索、live browser、真实模型结果；记录源代码/Prompt/模型/配置/语料版本与脱敏失败。
- [x] 5.13 编写 `docs/shopmind_agent_upgrade_acceptance.md`，关联每一验收项、命令与实际证据，明确业务/工程/模型完成状态。
- [x] 5.14 更新项目状态、架构、Runtime、开发与 Demo 文档、五分钟演示和三条简历表述；所有声明只覆盖已接入验证能力。
- [x] 5.15 最终检查 OpenSpec 严格校验、变更格式、单一 migration head、任务清单与规格覆盖；列明剩余项，未经授权不提交推送、发版或部署。

## 6. 剩余 8 项收尾执行顺序（规划说明，不替代上方勾选状态）

| 批次 | 对应任务 | 前置条件 | 完成证据 |
| --- | --- | --- | --- |
| C1 旧检索切流 | 2.13 | 当前 evidence/version gate | public contract 对照、shadow 差异、撤销与 rollback 测试 |
| C2 动作并发 | 4.11 | 0018 私有 schema、当前 Action 表 | 并发/取消/响应丢失/部分失败 PostgreSQL 矩阵 |
| C3 前端闭环 | 4.15、4.16 | C2 action schema 稳定 | Vitest + mocked Playwright：SSE、409/410、幂等、stale UI |
| C4 真实浏览器 | 5.7 | C1–C3 | 三场景 UI→API→worker→DB 行级断言 |
| C5 生产与回滚 | 5.9、5.10 | C1–C4 | preflight/readiness/release-operation 真实演练 |
| C6 真实模型 | 5.11 | provider 配置有效、C1–C5 | 三条真实轨迹 + 一次合法局部 revision |

执行细节、失败处理与门禁见 `design.md` 的 `Remaining Closeout Plan（67/75 → 75/75）`。任何批次未满足其完成门禁时，对应 task 必须保持未勾选。
