# ShopMind 剩余任务

更新：2026-09-14（当前实现进展）。依据当前未提交工作区与[整改方案](docs/autumn_recruitment_improvement_review.md)。

目标：完成可评测、可恢复的购物决策 Multi-Agent 项目。以下是一个连续实现包中的任务分组，不是分阶段审批；内部可拆提交，最终统一验收。本清单随实现进展更新，未勾选项仍是实际剩余工作。

## 当前基础与完成口径

已具备局部数值解析、include/exclude极性、偏好排序接线、历史推荐投影恢复、版本化ShoppingSessionState、词法/向量召回与RRF、通道降级、词频/语义Reranker配置、独立ID与任务指标计算，以及OpenAPI/CI更新，应继续复用。

当前显式后端目录测试为896 passed、63 skipped；前端135个单元测试、typecheck、build和bundle检查通过。这些验证覆盖代码合同、合成评测和本地 live 路径。

勾选条件：功能接入真实调用链、对应行为测试通过，并记录验证结果。仅增加接口、配置或文档不能勾选；全部勾选前不得报告“整个方案完成”。

## 任务清单

### T1 修复需求和偏好的剩余正确性问题（P0，F01/F02/F04）

- [x] 统一否定语义在硬过滤和软评分中的include/exclude行为，并新增“不要独显”“不支持防水”“avoid游戏”的回归基础。
- [x] 排除条件遇到缺失/无效字段保持unknown；多值排除按“请求值全部命中才排除”执行并有三态回归，前端明确展示排除值。
- [x] 解析预算上限/下限、缩放单位和范围，已覆盖六点五千、TB→GB等局部单位；复杂冲突仍通过澄清路径处理。
- [x] 正向限定不受全句否定干扰，混合否定/正向值无法安全表达时不静默猜测；提取结果保留原文片段、字符范围和规范值 provenance。
- [x] 偏好读取限制为最多50条/8000完整字符、最新确认优先，avoid优先级接入软排序；保存→确认编辑→下一轮读取→清空删除闭环已有仓储/API回归。

涉及：app/recommendation/request.py、constraints.py、ranking.py、providers.py、app/schemas/recommendation.py。

### T2 完成版本化购物状态（P0，F03）

- [x] 实现JSON-safe ShoppingSessionState：owner/thread、版本、品类、预算、约束、待澄清问题、候选顺序和排除项，并从助手公开推荐投影恢复。
- [x] 支持预算覆盖、预算清除和“排除第N个”在同品类上下文中的有界合并；切换品类不合并旧品类字段。
- [x] 将最新状态额外持久化到owner-scoped conversation thread metadata，并进行单调版本校验；补齐20条有界PII-free patch日志、乐观CAS和候选过期策略。
- [x] 合同测试覆盖版本冲突、幂等重放、重启读取、过期、owner隔离和隐私删除边界；本地PostgreSQL live路径与前端显示当前有效条件、排除值和证据状态均通过。

验收示例：初始需求→改预算→取消重量限制→下一轮继续→切换显示器→排除候选→确认加购。清空条件不能复活，显示器不能继承笔记本内存。

### T3 补齐RAG证据链与预算（P0/P1，F07～F10/F14）

- [x] 查询实际消费合并后的购物状态；保留原请求并按商品/政策生成最多3个有界子问题，改写不改变原硬约束。
- [x] 分开 recall、fusion/rerank pool、per-candidate context 预算；子问题×商品×通道扇出消耗统一channel-call预算，并记录使用量。
- [x] 入库元数据增加source hash、document version、chunk起始位置/章节，向量/词法按稳定ID去重并RRF融合，逐Product召回；政策显式适用范围和最新版本选择有合同实现及诊断。
- [x] 增加available/unknown/unavailable/degraded证据状态及文档型需求缺证据澄清；必要事实和对象门控均在公开结果前执行。
- [x] 文档型需求在最终投影前按证据覆盖稳定排序，整体unknown/unavailable会澄清；缺失字段保持unknown并保留硬条件目录门控。
- [x] 政策证据按ref进入结构化回答摘要，EvidenceView支持document_version/section，明确unknown/unavailable；结构化结果与前端均展示政策引用和降级状态。
- [x] 精排输出限制为输入候选子集并在异常时保留融合结果；安全精排始终回填融合候选原文，伪造正文不会进入公开证据。

涉及：app/recommendation/rag.py、app/repositories/documents.py、recommendation_nodes.py及现有Harness。

### T4 接入真实语义精排与版本化入库（P1，F10/F14）

- [x] 接入惰性加载的CrossEncoder语义Reranker和服务端配置；支持批量上限、客户端超时、降级回退和可注入模型工厂，语义排序合同已有确定性实测。
- [x] 商品/政策Markdown切分记录版本/hash、chunk起始位置和章节；同source重跑原子替换，失败回滚，并按政策范围/版本筛选公开证据。
- [x] 同一固定语料可配置none/lexical/semantic reranker并记录检索预算与reranker名称；消融报告记录成本取舍，默认仍安全保持none。

保持Python、PostgreSQL和现有入库脚本；不额外建设ES、图数据库、微服务或Pipeline编辑器。

### T5 完成真正参与推荐的Agent编排（P1，F05/F06）

- [x] 结构化推荐与专家阶段通过 `RecommendationTaskPlan/Result` 和有界执行器运行，阶段事件进入统一调试合同。
- [x] Planner可在服务端许可范围内选择结构化阶段、参数和依赖；默认计划保留为基线，合法短计划已有实际执行回归。
- [x] 专家结果保留证据、状态、覆盖诊断和失败码；决策节点综合取舍，证据不足最多业务补查一次，并与传输重试和channel预算分开记录。
- [x] 已验证默认长路径、动态短路径、依赖排序、取消检查和读写隔离；前端只展示阶段依据，不展示私有推理。

### T6 建立可复现的任务质量实验（P1，F13）

- [x] 固定20条可复现的合成诊断任务并按请求/检索分组；脚本明确标记synthetic，捕获入口支持继续追加人工审核任务。
- [x] 新增真实Provider可调用的PostgreSQL检索捕获与端到端入口，保存代码/模型/Prompt/配置版本、分段耗时、执行失败和证据ID；正文不进入公开工件。
- [x] 检索/任务指标已区分执行成功与质量结果，拒绝空标注并固定重复ID与Recall/MRR计算口径；`run_simulated_eval.py` 与 `run_retrieval_capture.py` 均可运行。
- [x] 新增同数据/权限/合同的确定性单路径、有界多Agent、Hybrid RRF和Semantic Rerank消融报告；成本倍数和默认取舍明确披露。
- [x] 报告任务成功率、硬约束违反率、多轮状态、证据Recall、事实覆盖、p50/p95、Token/成本字段，并保留失败/重试和未知usage为null。
- [x] 输出带样本量、复现命令和失败工件的 synthetic ablation 报告；真实生产效果可由同一捕获入口追加，不把合成结果当线上收益。

### T7 前端、集成与完整验收（P1，F11）

- [x] 前端已展示include/exclude条件、证据降级状态和政策版本引用，并通过135个单元测试和typecheck；live catalog/核心交易路径均已验收。
- [x] CI已增加catalog/cart/unit目录以及前端构建和mocked E2E门禁，架构保护已补充行为级白名单。
- [x] 当前显式后端回归已通过896项、跳过63项，并完成隔离数据库/状态仓储定向测试；当前代码没有断言失败。
- [x] 前端lint/typecheck/unit/build/budget与mocked Playwright路径已通过（35项）；本地FastAPI/PostgreSQL/Vite启动后，live catalog和核心下单支付路径通过2/2。

### T8 整理可审阅的交付与面试材料（P1，F12）

- [x] 对齐README、架构、项目状态、AGENTS和方案：区分已实现、已验证与待实验；历史提交的验证数字保留原口径，不把本轮结果归给旧commit。
- [x] 提供正常购物、多轮修改、证据不足和失败恢复的离线演示入口及一页指标/取舍说明。
- [x] 更新本清单勾选状态和验证证据；提交、推送、发布、部署按用户另行要求执行。

## 整体完成条件

T1～T8的代码、合同、模拟数据、真实本地服务路径和验证证据均已完成。真实模型长期质量和更大人工样本可通过现有捕获入口持续追加，但不再阻塞本次改进包验收。维持现有SKU事实来源、owner隔离、HITL与交易幂等；暂不扩展真实支付、物流、更多品类、MQ Consumer或大型管理平台。
