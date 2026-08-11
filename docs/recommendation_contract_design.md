# Phase 1 推荐契约设计

## 现状与目标

现有 `ChatResponse`（`app/schemas/chat.py`）只暴露文本、status、tool calls 和 pending id。
`product_agent.py` 的 `product_summary` 由工具文本抽取；`decision_agent.py` 生成文本。因此新结果必须
作为加性公开模型，前端不能从 `answer`、tool name 或 debug 解析商品事实。

## Pydantic 模型

新增 `app/schemas/recommendation.py`，包含：

```text
RecommendationResult
  schema_version = "shopmind.recommendation.v1"
  outcome: recommended | no_match | clarification_required
  ranking_policy_version
  request_summary
  structured_constraints
  no_match_reason?
  missing_fields[]?
  clarification_question?
  recommendations[]

Money
  amount: string（内部以 Decimal 校验并规范化为两位小数）
  currency: ISO 4217

ProductSpecificationView
  code, name, value_type: string | integer | decimal | boolean | string_list
  value: str | int | bool | list[str]（decimal 以 string 表示）
  unit, comparable, display_order

AvailabilityView
  sale_status, available_quantity, in_stock, reason_code

Recommendation
  product_id, sku_id, product_name, sku_name, money, image_url?
  specifications[], score, score_breakdown[]
  matched_hard_constraints[], unmatched_constraints[], soft_tradeoffs[]
  evidence[], reason, availability
```

约束使用显式 optional 字段：budget_max、budget_currency、memory_min_gb、storage_min_gb、weight_max_kg、
cpu_tier_min、gpu_tier_min、screen_inches、primary_use_cases、secondary_use_cases。Evidence 只发布
白名单 source/type/field/value/ref，不暴露 RAG 原始 payload 或内部 debug。`specifications` 是 Catalog 的稳定
卡片/比较事实；Evidence 只提供溯源，不能替代或覆盖 specifications。硬约束不满足的 SKU 绝不进入 Top K；
保留 `unmatched_soft_constraints` 时它只能描述软约束。无匹配返回 `outcome=no_match`、空 recommendations、
结构化 `no_match_reason` 和已应用硬约束；缺关键信息返回 `outcome=clarification_required`、缺失字段和
澄清问题。前端不能通过数组为空推断业务状态，generated TypeScript 必须保留上述 union/标量类型而非
退化为 `any`。当至少有三个有效匹配时最多返回三个；少于三个时返回实际数量，不能用硬约束不满足的 SKU
补足。

`Money.amount` 的公开输入/输出均为 string：拒绝负数、NaN、Infinity 和超过两位小数的输入，不做静默舍入；
有效值输出为两位小数字符串。`currency` 必须为三个大写字母；中文购物语境将元、人民币、RMB、CNY、全角 `￥`
与未带日元语义的半角 `¥` 归一化为 CNY，明确 JPY/日元则保持 JPY，Phase 1 不进行汇率换算。
`ProductSpecificationView.value` 使用严格 string/int/bool/string-list 联合，integer 不接受 bool、boolean 不接受 int，
decimal 必须为 Decimal-valid 的 string。

`ChatResponse` 增加可选 `recommendation: RecommendationResult | null` 与可选的稳定
`projection_error`。该结果不由 Runtime 自动公开：
Phase 1B 新增 API 层 `build_chat_response(result, user_id, thread_id, include_debug)`，使用
`RecommendationResult.model_validate(result.output_data["recommendation"])` 安全投影；JSON chat route 和
`chat_stream.py::_legacy_stream_result` 都只能调用该函数。Runtime 在成功持久化前执行本领域结果校验，仍只保存通用 dict，不能 import 本领域
Schema。旧客户端忽略未知字段即可兼容。

完整传播链为：Graph/Service 在成功 raw result 前先执行 `RecommendationResult.model_validate()`，将
`recommendation` 放入 raw result →
`ShopMindRuntimeHarness._build_success_result` 复制到 `RunResult.output_data` → `_persist_finish` 写入
`AgentRun.result_json`、assistant `ConversationMessage.content_json` 和 idempotency response fingerprint →
`_run_result_from_persisted_run` 在重放中恢复 output_data → 统一 API builder 验证/投影到 ChatResponse →
JSON route 与 SSE terminal `run.result` 使用同一 builder。现有 `run_result_to_legacy_response()`
(`app/runtime/harness.py`) 不包含 output_data，必须在 Phase 1B 替换 API 调用点，不能假设自然一致。

## 算法、RAG 顺序与 Agent 边界

新增 `app/recommendation/service.py`：先校验/归一化约束，随后按可售、库存、预算、内存、存储、重量等
硬约束过滤；再执行可配置的分项评分，输出贡献、缺失惩罚和软约束妥协。LLM/Agent 只产出受 Pydantic
验证的需求草案和解释；服务端 catalog price/inventory 覆盖任何模型数字。Phase 1 的确定性 parser
先覆盖预算币种、内存、Java 开发与剪视频等中文常见表达；“尽量轻”等未给出数值的措辞不伪造硬约束，
保留给后续明确的软偏好契约。LLM extractor 后续作为 opt-in adapter，且必须与 schema 和默认行为等价。

目标图顺序为：Catalog candidate retrieval 与 Preference retrieval → `deterministic_recommendation` →
Top K SKU → `top_k_product_rag`（只按 Top K legacy ids 查询）与可并行的 `policy_rag` →
`evidence_validation` → Decision。商品专属 RAG 不得早于 Top K；RAG 不得决定价格、库存、sale status、
结构化规格或引入 Top K 外商品。

新增普通 graph nodes/adapters，不新增 Recommendation Agent。State 输入为 `structured_constraints`、
`catalog_candidates`、`preference_summary`；ranking 输出为 `recommendation_result`、
`ranked_sku_candidates`、`recommendation_diagnostics`；evidence nodes 输出 `top_k_product_evidence`、
`policy_evidence`、`validated_evidence`。Decision 只读 recommendation_result 和 validated evidence 生成解释，
禁止添入 Top K 外 SKU。Graph adapter 将相同 result 放入 raw result；写意图 handoff 在 Catalog/recommendation
节点前保持原有分支。single Agent 路径可以没有 optional recommendation，或经同一 service 生成，不能伪造。

Response Builder 只安全读取并投影已验证 output_data，不能把已持久化的 completed Run 改写为 failed。旧路径
缺少 recommendation 合法；若已持久化结果带损坏 recommendation，JSON 和 SSE 都保留原 Run status，返回
`recommendation=null` 与稳定 `projection_error.code=recommendation_projection_corrupt`，并产生 PII-safe 审计
事实。Graph/Service 校验失败则应在 Harness 持久化前成为 failed Run。response fingerprint 只包含规范化的
公开 status/answer/tool calls/pending action 和 canonical RecommendationResult；不包含全部 output_data 或
recommendation_diagnostics。

## 验收与风险

Phase 1A 单测覆盖无满足、缺失属性、预算边界、库存/下架、分项得分和稳定排序及纯 evidence sanitizer/merge；
真实 RAG/Catalog 冲突集成测试属于 Phase 1B。Phase 1B API/SSE 测试断言同一结果模型、
result_json/idempotency 重放和 response fingerprint 都包含 canonical recommendation。每条 stream 恰有一个合法
terminal：`run.result`、`run.cancelled` 或 `run.failed`；后两类不要求正常 RecommendationResult。风险是
当前 Product/RAG 数据缺规格；通过新 Laptop seed 解决，不能把自由文本 RAG 当库存或价格事实。
