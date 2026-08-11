# RetailPilot / ShopMind 秋招项目改造说明书

> 用途：交给 Codex 或其他代码代理完整检查当前仓库，并基于真实代码结构制定可执行的改造方案。
> 仓库：`https://github.com/JoniFf777/retailpilot.git`

---

## Phase 0 事实修正（2026-08-03）

本说明书的后续设计以当前工作区为准：当前存在一版未跟踪的 `frontend/`，并非“完全没有 Web
前端”。该版本已经包含 React/Vite、聊天、POST-SSE、AbortController 停止生成、HITL 确认抽屉以及
部分 privacy/runs/status 页面；它应作为协议和测试参考保留，后续可以重新设计，但不得直接删除。

当前缺少的是**结构化、可验证、可在 90 秒内演示完整的推荐与模拟交易闭环**：公开的
`RecommendationResult`、商品卡/对比、SKU/属性/数量库存、结构化 PendingActionView、独立 Cart API、
Checkout、ShopMind 专用订单、Mock Payment、Outbox/Inbox 与推荐质量对照评估仍未实现。

当前 Vite 开发端口为 `5173`，`docker-compose.yml` 仅定义 PostgreSQL；不应预先宣称前端端口为
`3000` 或 Compose 已启动前后端、Redis、RocketMQ。旧 `orders`/`order_items` 关联 Customer 历史数据，
不能复用为 ShopMind 订单域。README 中的贡献和指标只在实际实现、验证后更新。

详见 `docs/baseline_report.md`、`docs/current_architecture_audit.md`、`docs/gap_analysis.md` 与
`docs/implementation_plan.md`。

---

## 1. 项目背景

RetailPilot / ShopMind 最初基于官方教学项目进行开发，目前已经在原始单 Agent 能力上扩展为 Multi-Agent 系统。

当前项目的主要技术方向包括：

- FastAPI 后端 API
- LangGraph Multi-Agent 编排
- Product Agent、RAG Agent、Preference Agent、Decision Agent 等专业 Agent
- Runtime Harness
- Tool Gateway 与工具权限控制
- PostgreSQL / pgvector 持久化
- 会话、运行记录、事件和长期记忆
- SSE 流式事件
- 幂等、预算、超时与重试控制
- Human-in-the-loop 写操作确认
- pending action 两阶段写入
- 身份、数据所有权和治理审计
- 自动化测试与评估框架

当前后端工程能力已经比较丰富；已有一版可体验的前端雏形，但尚缺少以结构化推荐、商品比较、购物车、
结算、订单和模拟支付构成的完整 Web Demo，购物业务链路也没有完整展示出来。

本轮改造的核心不是继续增加 Agent 数量，而是：

> 将现有 Multi-Agent 后端包装成一个可体验、可验证、可演示的数码产品智能决策与交易系统。

---

## 2. 项目定位

### 2.1 推荐定位

项目最终定位为：

> **ShopMind：面向数码产品选购的可控 Multi-Agent 决策与模拟交易系统。**

用户可以通过自然语言描述预算、用途、性能、便携性等需求，系统完成：

1. 理解和结构化用户需求。
2. 检索符合条件的数码产品。
3. 查询产品规格、政策和其他 RAG 证据。
4. 读取用户历史偏好。
5. 对候选商品进行确定性过滤、评分和排序。
6. 生成带证据、约束匹配和妥协项的推荐结果。
7. 将商品加入购物车。
8. 通过 Human-in-the-loop 确认敏感写操作。
9. 完成购物车管理、模拟结算、订单创建和模拟支付。
10. 在前端展示 Agent 执行过程和最终业务结果。

### 2.2 目标用户

主要面向：

- 在校大学生
- 秋招或刚入职的开发者
- 有明确预算和用途的数码产品购买者

优先覆盖：

- 笔记本电脑
- 显示器
- 键盘和鼠标
- 耳机与音频设备
- 常见电脑配件

### 2.3 项目价值

项目不应只是“一个会聊天的购物机器人”，而应体现以下能力：

- LLM 负责自然语言理解和解释。
- 普通代码负责可确定、可验证的业务规则。
- Multi-Agent 负责不同证据源和业务职责之间的协作。
- Tool Gateway 负责权限和安全边界。
- Human-in-the-loop 负责敏感操作确认。
- Runtime 负责可观测、可恢复和可治理的 Agent 执行。
- 前端负责把复杂后端能力转化成用户能理解的产品体验。

---

## 3. 当前主要问题

Codex 需要以实际代码为准检查以下问题，不要只依赖 README 或本文描述。

### 3.1 缺少完整业务 Web Demo

当前项目已有可直接体验的前端工作台雏形，但缺少面向结构化商品和交易闭环的完整体验，导致：

- Multi-Agent 执行过程不可见。
- SSE 生命周期事件无法直观展示。
- 推荐结果主要表现为文本，缺少商品卡片和参数对比。
- pending action 和用户确认流程无法直观演示。
- 加入购物车后用户难以继续查看和操作。
- 项目在线展示能力较弱。

### 3.2 购物车能力可能只完成了部分后端链路

需要检查现有代码中是否已经存在：

- `cart_items` 数据模型
- 购物车 Repository
- `prepare_add_to_cart`
- `confirm_add_to_cart`
- `get_cart_items`
- pending action
- `/api/chat/confirm`
- 写操作 Tool Gateway 策略

在此基础上确认缺失内容，预计包括：

- 独立的购物车查询 API
- 修改数量
- 删除单个商品
- 清空购物车
- 价格和库存重新校验
- 购物车页面
- 购物车角标和前端状态同步

### 3.3 缺少完整交易闭环

当前预计缺少或不完整的能力：

- Checkout Preview
- 创建订单
- 订单项价格快照
- 订单查询
- 订单详情
- 订单取消
- 支付模型
- 支付网关抽象
- Mock Payment
- 支付幂等
- 订单和支付状态机

### 3.4 Multi-Agent 价值缺少可量化证明

需要补充：

- Single Agent 与 Multi-Agent 对照实验
- 推荐效果评估集
- 推荐约束满足率
- 证据覆盖率
- 参数引用正确率
- 工具调用成功率
- 平均响应时间
- P95 响应时间
- Token 消耗和估算成本
- 任务成功率

### 3.5 架构复杂度较高，但业务表现较弱

当前项目可能存在以下情况：

- Runtime、治理、审计和评估能力较重。
- 用户能感知的业务功能较少。
- 核心装配代码或 Runtime 文件职责过多。
- 新旧 Agent 路径、教学代码和正式代码共存。
- 同步与异步执行存在桥接层。
- 项目阅读和维护成本较高。

需要 Codex 根据真实代码识别：

- 超大文件
- 高耦合模块
- 重复装配代码
- 隐式依赖
- 循环依赖风险
- 领域逻辑和基础设施逻辑混杂
- 可安全拆分的重构边界

---

## 4. 本轮改造的总体原则

### 4.1 不继续盲目增加 Agent

暂不新增以下类似 Agent：

- Price Agent
- Review Agent
- Search Agent
- Critic Agent
- Payment Agent
- Cart Agent

只有当独立 Agent 能带来明确的权限边界、远程服务边界或可量化收益时，才考虑增加。

### 4.2 可确定的逻辑使用普通代码

以下能力应优先使用确定性代码，而不是交给 LLM：

- 价格过滤
- 库存检查
- 商品属性过滤
- 硬约束判断
- 推荐评分
- 排序
- 购物车金额计算
- 订单金额计算
- 用户所有权检查
- 幂等校验
- 状态机
- 支付金额校验
- 写操作权限校验

LLM 主要负责：

- 从自然语言提取需求
- 判断缺少哪些信息
- 对候选结果生成解释
- 总结推荐理由
- 解释妥协项
- 将技术参数转化为用户可理解的表达

### 4.3 保留 Tool Gateway 和 Human-in-the-loop

这是项目最有价值的能力之一，应继续保留并在前端突出展示。

自然语言写操作推荐流程：

```text
用户提出“把第二款加入购物车”
        ↓
Agent 识别写意图
        ↓
创建 pending action
        ↓
前端展示即将执行的操作
        ↓
用户修改数量、确认或取消
        ↓
服务端重新校验身份、所有权、状态和参数
        ↓
真正写入购物车
```

### 4.4 UI 明确操作不必经过 LLM

例如用户在购物车页面直接点击：

- 数量加一
- 数量减一
- 删除
- 清空购物车

这些操作应使用普通 REST API，不必经过 Agent 和 LLM。

需要保留的区分：

- 自然语言触发的敏感写操作：Agent + pending action + HITL。
- 用户在确定性 UI 中直接操作：普通 API + 身份和所有权检查。

### 4.5 优先形成一条完整可演示链路

本轮最重要的主流程：

```text
描述购买需求
→ Multi-Agent 分析
→ 结构化需求
→ 商品搜索与 RAG
→ 候选评分和推荐
→ 商品参数对比
→ 加入购物车
→ 用户确认
→ 查看购物车
→ 模拟结算
→ 创建订单
→ Mock 支付
→ 展示订单结果
```

---

## 5. 前端实现范围

建议使用：

- React
- TypeScript
- Vite
- TanStack Query
- React Hook Form
- Zod
- `fetch + ReadableStream` 处理 POST SSE
- AbortController 取消请求
- Playwright 端到端测试

可根据仓库实际情况选择已有技术栈，不强制重建已有前端。

### 5.1 页面一：AI 购物决策工作台

建议布局：

```text
┌──────────────┬──────────────────────────┬──────────────────┐
│ 历史会话     │ 对话与推荐结果           │ Agent 执行时间线 │
│              │                          │                  │
│ 新建会话     │ 用户消息                 │ 理解需求 ✓       │
│ 会话一       │ AI 流式回复              │ 商品检索 ✓       │
│ 会话二       │ 商品候选卡片             │ RAG 查询 ✓       │
│              │ 推荐理由与证据           │ 偏好读取 ✓       │
│              │ 参数对比                 │ 生成决策 ...     │
└──────────────┴──────────────────────────┴──────────────────┘
```

需要实现：

- 新建和切换会话
- 用户输入
- 流式回复
- 停止生成
- Agent 节点执行状态
- 工具调用事件
- 错误和重试状态
- 推荐商品卡片
- 推荐理由
- 匹配约束
- 妥协项
- 证据来源
- 加入对比
- 加入购物车

### 5.2 结构化需求面板

用户输入示例：

> 预算 6000 元以内，主要用于 Java 开发，偶尔剪视频，希望轻一点，内存至少 16GB。

前端需要展示并允许修改：

```text
预算：≤ 6000 元
主要用途：Java 开发
次要用途：轻度视频剪辑
重量偏好：轻便
内存：≥ 16GB
屏幕尺寸：未指定
品牌偏好：未指定
```

修改后可重新执行推荐。

### 5.3 商品卡片

每个商品至少展示：

- 商品名称
- 品牌
- 当前价格
- 库存状态
- 核心规格
- 推荐分数
- 推荐理由
- 已满足硬约束
- 未满足或存在风险的约束
- 主要妥协项
- 证据来源
- 加入对比
- 加入购物车

### 5.4 商品对比页或对比抽屉

支持最多 3～4 个商品。

对比内容示例：

| 参数 | 商品 A | 商品 B | 商品 C |
|---|---:|---:|---:|
| 价格 | ¥5,999 | ¥6,299 | ¥5,499 |
| 内存 | 16GB | 32GB | 16GB |
| 重量 | 1.45kg | 1.72kg | 1.38kg |
| 约束满足 | 全部满足 | 重量超标 | 全部满足 |
| 推荐分数 | 91 | 82 | 88 |

需要突出：

- 最优项
- 约束冲突
- 不确定数据
- 推荐商品
- 推荐理由

### 5.5 pending action 确认抽屉

当 Agent 准备执行写操作时，前端展示：

- 操作类型
- 商品信息
- 数量
- 即将写入的数据
- 风险级别
- 过期时间
- 修改参数
- 确认
- 取消

必须正确处理：

- 已确认
- 已取消
- 已过期
- 已执行
- 重复确认
- 参数非法
- 所有权不匹配
- 服务端错误

### 5.6 购物车页面

需要实现：

- 查询购物车
- 修改数量
- 删除商品
- 清空购物车
- 商品价格
- 小计
- 总价
- 库存状态
- 价格变化提示
- 去结算
- 空购物车状态
- 加载和错误状态

### 5.7 结算页面

需要实现：

- 购物车商品确认
- 收货信息
- 配送方式
- 模拟支付方式
- 商品金额
- 配送金额
- 优惠金额（可暂时为 0）
- 应付金额
- 提交订单
- 重复提交保护

### 5.8 订单页面

需要实现：

- 订单列表
- 订单详情
- 订单号
- 创建时间
- 订单商品
- 金额快照
- 支付状态
- 订单状态
- 模拟支付结果
- 取消订单
- 空状态和错误状态

---

## 6. 后端功能范围

Codex 需要先检查现有实现，再决定新增、复用或重构，禁止重复造轮子。

### 6.1 购物车 API

建议目标接口：

```http
GET    /api/cart
PATCH  /api/cart/items/{cart_item_id}
DELETE /api/cart/items/{cart_item_id}
DELETE /api/cart
```

可根据当前 ID 设计和代码风格调整路径。

要求：

- 所有接口绑定当前身份。
- 只能访问和修改自己的购物车。
- 数量必须为合法正整数。
- 检查商品是否存在。
- 检查库存。
- 删除和清空保持幂等。
- 返回统一错误模型。
- 添加单元测试和集成测试。

### 6.2 Checkout Preview

建议接口：

```http
POST /api/checkout/preview
```

职责：

- 重新读取服务端购物车。
- 不信任前端传回的价格。
- 检查商品是否存在。
- 检查库存。
- 使用数据库最新价格。
- 检查商品上下架状态。
- 计算商品小计和总价。
- 返回价格变化。
- 返回库存不足商品。
- 返回不可结算原因。
- 不在 Preview 阶段创建正式订单。

### 6.3 订单 API

建议接口：

```http
POST /api/orders
GET  /api/orders
GET  /api/orders/{order_id}
POST /api/orders/{order_id}/cancel
```

`POST /api/orders` 要求：

- 支持幂等键。
- 重新进行服务端校验。
- 在事务中创建订单和订单项。
- 保存商品名称、价格等订单快照。
- 正确处理库存。
- 正确处理购物车清理。
- 避免重复订单。
- 返回稳定的订单结果。

订单状态可参考：

```text
pending_payment
paid
cancelled
payment_failed
refunded
```

实际状态需结合已有模型设计。

### 6.4 Mock Payment

第一阶段不接真实支付宝、微信或 Stripe。

新增支付网关抽象，例如：

```python
class PaymentGateway(Protocol):
    def create_payment(self, order_id: str, amount: Decimal) -> PaymentResult:
        ...

    def query_payment(self, payment_id: str) -> PaymentResult:
        ...

    def refund(self, payment_id: str, amount: Decimal) -> RefundResult:
        ...
```

实现：

```text
MockPaymentGateway
```

至少支持：

- 支付成功
- 支付失败
- 支付处理中

建议新增支付记录：

```text
payments
- payment_id
- order_id
- user_id / owner_id
- amount
- currency
- provider
- status
- idempotency_key
- provider_reference
- failure_reason
- created_at
- updated_at
- paid_at
```

支付状态可参考：

```text
pending → processing → succeeded
                     ↘ failed

succeeded → refunded
```

要求：

- 金额由服务端读取订单，不接受前端决定最终支付金额。
- 支持幂等。
- 支付记录与订单所有者一致。
- 状态转换合法。
- 保留后续替换真实支付 Provider 的能力。
- Demo 可通过配置控制成功、失败或处理中。

### 6.5 商品推荐结构化输出

当前若只有纯文本回答，需要逐步扩展为结构化结果。

建议结构：

```json
{
  "schema_version": "shopmind.recommendation.v1",
  "outcome": "recommended",
  "ranking_policy_version": "laptop-v1",
  "request_summary": "用户需求摘要",
  "structured_constraints": {
    "budget_max": 6000,
    "memory_min_gb": 16,
    "weight_max_kg": "1.6",
    "primary_use_cases": ["java_development"]
  },
  "recommendations": [
    {
      "product_id": "catalog-product-uuid",
      "sku_id": "catalog-sku-uuid",
      "product_name": "ThinkBook 14+",
      "sku_name": "16GB / 512GB / 银色",
      "money": {"amount": "5999.00", "currency": "CNY"},
      "specifications": [
        {"code": "memory_gb", "name": "内存", "value": 16, "value_type": "integer", "unit": "GB", "comparable": true, "display_order": 20}
      ],
      "score": 91,
      "matched_hard_constraints": [
        "价格低于 6000 元",
        "内存为 16GB"
      ],
      "unmatched_soft_constraints": [],
      "soft_tradeoffs": [
        "显卡性能只适合轻度剪辑"
      ],
      "evidence": [
        {
          "source_type": "product",
          "source_id": "TECH-LAP-001",
          "field": "weight",
          "value": "1.42kg"
        }
      ],
      "availability": {"sale_status": "active", "available_quantity": 8, "in_stock": true, "reason_code": "available"},
      "reason": "推荐理由"
    }
  ]
}
```

实际 Schema、no_match、clarification_required、Money 与公开投影错误语义以
`docs/recommendation_contract_design.md` 为唯一契约来源。

### 6.6 确定性过滤和评分

建议流程：

```text
LLM 提取结构化需求
        ↓
Catalog Repository 查询 active SKU + Preference 读取
        ↓
普通代码执行硬约束过滤和 SKU 层加权评分（默认按 SPU 去重）
        ↓
返回 Top K SKU
        ↓
按 Top K legacy_product_id 查询产品 RAG + 查询通用 policy RAG
        ↓
证据校验后由 Decision Agent 解释同一 Top K
```

评分逻辑需要：

- 可配置
- 可测试
- 可解释
- 不依赖隐藏 prompt
- 能输出各评分项贡献
- 对缺失字段有明确策略

可考虑：

```text
总分 =
预算匹配分
+ 性能匹配分
+ 便携性分
+ 用户偏好分
+ 库存可用分
- 约束冲突惩罚
- 缺失数据惩罚
```

不要在第一版过度复杂化，可先实现简单且可测试的加权评分。

---

## 7. 架构重构方向

Codex 需要先绘制现有依赖关系，再决定是否拆分。不要为了“看起来更干净”进行大规模重写。

### 7.1 重点检查模块

重点检查：

- `app/dependencies/agent.py`
- `app/runtime/harness.py`
- Multi-Agent graph
- Supervisor
- Decision Agent
- Write Handoff
- Tool Gateway
- Cart Repository
- Order Models / Repositories
- Chat API
- Confirm API
- SSE 实现
- 身份与 owner boundary
- 数据库事务边界
- 幂等实现
- 测试夹具和集成测试

### 7.2 可能的目标结构

仅作为候选方向，需结合真实代码调整：

```text
app/
  composition/
    container.py

  application/
    chat_service.py
    cart_service.py
    checkout_service.py
    order_service.py
    payment_service.py
    action_service.py

  domain/
    product/
    recommendation/
    cart/
    order/
    payment/
    action/

  runtime/
    runner.py
    event_service.py
    budget_service.py
    persistence.py

  infrastructure/
    repositories/
    payments/
    llm/
    rag/
```

目标不是强行应用 DDD，而是：

- 降低核心文件职责数量。
- 分离对象装配与业务用例。
- 分离领域状态机与 HTTP。
- 分离推荐逻辑与 Prompt。
- 使购物车、订单、支付能够独立测试。

### 7.3 重构要求

- 优先小步重构。
- 每次重构保持测试通过。
- 不改变公开 API 时要保持兼容。
- 必要变更需要迁移说明。
- 避免一次性重写 Runtime。
- 避免破坏现有 HITL 和安全边界。
- 避免为了目录美观增加无意义抽象。

---

## 8. Demo 演示脚本

建议准备一个固定的 90 秒演示。

### 场景

用户输入：

> 我预算 6000 元以内，想买一台适合 Java 开发的笔记本，偶尔剪视频，希望内存至少 16GB，尽量轻一点。

### 演示步骤

1. 用户提交需求。
2. 前端显示结构化需求。
3. 展示 Supervisor 和各专业 Agent 执行状态。
4. Product Agent 搜索商品。
5. RAG Agent 查询规格和政策。
6. Preference Agent 读取用户偏好。
7. Decision Agent 输出 3 个候选。
8. 展示约束匹配、证据和妥协项。
9. 用户打开商品对比。
10. 用户说“把第二个加入购物车”。
11. 前端弹出 pending action 确认抽屉。
12. 用户修改数量并确认。
13. 购物车角标更新。
14. 进入购物车。
15. 执行 Checkout Preview。
16. 创建订单。
17. Mock Payment 返回成功。
18. 展示订单详情。

### 失败场景演示

可额外准备一个失败场景：

- 商品库存不足
- pending action 过期
- 重复确认
- Mock Payment 失败
- 重复提交订单
- 用户试图访问其他人的购物车或订单

用于展示系统不是只处理 Happy Path。

---

## 9. 评估体系

### 9.1 推荐效果评估集

准备至少 50～100 条用户需求，覆盖：

- 简单搜索
- 多硬约束
- 预算冲突
- 库存冲突
- 信息缺失
- 需要澄清
- 多商品对比
- 历史偏好影响
- 无满足商品
- RAG 证据冲突
- 写操作请求

每条样本包含：

- 用户输入
- 期望结构化约束
- 允许候选商品
- 禁止候选商品
- 期望是否澄清
- 期望证据字段
- 期望工具轨迹
- 期望是否触发写确认

### 9.2 指标

至少统计：

- 需求抽取准确率
- 硬约束满足率
- Recall@K
- 推荐证据覆盖率
- 商品参数引用正确率
- 无满足商品时的拒绝或澄清正确率
- 写操作未经确认执行次数
- 工具调用成功率
- 平均响应时间
- P50 / P95 响应时间
- 平均 Token
- 平均估算成本
- 任务成功率

### 9.3 对照实验

对比：

```text
Single Agent
Multi-Agent
Multi-Agent + Deterministic Ranking
```

最终 README 应能回答：

- Multi-Agent 提升了什么？
- 增加了多少延迟？
- 增加了多少 Token 或成本？
- 哪些简单请求不值得走 Multi-Agent？
- 是否需要根据请求复杂度动态路由？

---

## 10. 测试要求

### 10.1 单元测试

覆盖：

- 需求结构化
- 约束过滤
- 推荐评分
- 购物车数量修改
- 总价计算
- Checkout Preview
- 订单状态机
- 支付状态机
- Payment Gateway
- 幂等
- owner 校验
- pending action 状态转换

### 10.2 集成测试

覆盖：

- Chat → 推荐
- Chat → pending action
- Confirm → cart
- Cart → checkout preview
- Checkout → order
- Order → mock payment
- 重复请求
- 事务回滚
- 库存不足
- 非法状态转换
- 不同用户之间的数据隔离

### 10.3 E2E 测试

使用 Playwright 或等价工具覆盖：

```text
输入需求
→ 收到流式推荐
→ 选择商品
→ 确认加购
→ 查看购物车
→ 结算
→ 创建订单
→ 模拟支付
→ 查看订单
```

同时覆盖：

- 取消 SSE
- 断线或错误恢复
- pending action 过期
- 支付失败
- 空购物车
- 重复提交

---

## 11. 部署和演示要求

### 11.1 一键本地启动

目标：

```bash
docker compose up
```

启动：

- 前端
- 后端
- PostgreSQL
- Redis（若项目需要）
- 数据初始化

访问：

```text
http://localhost:3000
```

### 11.2 Demo Mode

建议支持：

```env
DEMO_MODE=true
```

用途：

- 没有真实模型 API Key 时也能演示。
- 使用固定响应、录制事件或 Mock LLM。
- CI 中运行稳定 E2E。
- 面试现场避免外部模型服务不稳定。

Demo Mode 不应绕过核心业务校验；购物车、订单、支付状态机仍应走真实后端代码。

### 11.3 在线 Demo

仓库首页建议提供：

- Live Demo
- Demo Video
- Architecture
- My Contributions
- Evaluation Results
- Local Setup

### 11.4 演示视频

准备一段 60～90 秒录屏，展示主流程和一次失败场景。

---

## 12. README 改造

README 建议新增以下部分：

### 12.1 项目一句话介绍

> ShopMind 是一个面向数码产品选购的可控 Multi-Agent 决策与模拟交易系统。

### 12.2 原始项目与个人贡献

明确区分：

```text
Original Baseline
- 官方教学项目提供的基础能力

My Contributions
- Multi-Agent 编排
- Runtime 扩展
- Tool Gateway
- HITL
- SSE 生命周期事件
- 持久化和幂等
- 前端决策工作台
- 购物车完整链路
- Checkout 和订单
- Mock Payment
- 推荐评估体系
```

具体内容必须根据 Git 历史和真实代码确认，不能夸大。

### 12.3 Before / After

展示原始架构和当前架构。

### 12.4 Demo 截图与 GIF

至少包含：

- 决策工作台
- Agent 执行时间线
- 商品对比
- pending action
- 购物车
- 订单结果

### 12.5 指标

展示真实评估结果，不使用虚构数字。

### 12.6 架构取舍

说明：

- 为什么使用 Multi-Agent
- 为什么可确定逻辑不用 LLM
- 为什么使用 HITL
- 为什么支付使用 Mock Provider
- 为什么 UI 明确操作不经过 Agent
- 当前限制和下一步计划

---

## 13. 实施阶段来源

本文件定义产品定位、范围、验收和禁止事项，**不再定义实施 P0–P7 顺序**。唯一的实施阶段来源是
`docs/implementation_plan.md`：Phase 0 为基线，Phase 0.5 为设计收口，随后先执行 Phase 1A（Catalog、
身份桥接和确定性推荐内核），再执行 Phase 1B（Graph、统一 HTTP/SSE 映射和结构化前端）。购物车、交易、
RocketMQ Spike、Mock Payment、评估和部署均按该文件的后续阶段推进。

本说明书过去的“先前端、后推荐”的 P0–P7 次序已过时，不能作为编码依据。当前已存在前端雏形；结构化
Catalog、统一结果契约与确定性推荐必须先于新的商品卡和交易页面。

---

## 14. 本轮明确不做

除非代码检查发现强依赖，否则第一阶段不做：

- 真实支付宝或微信支付
- 完整商城首页
- 秒杀、优惠券和营销系统
- 商家后台
- 物流系统
- 退款售后完整流程
- 大规模商品爬虫
- 无限品类扩张
- 为每个功能新增 Agent
- 大规模重写 Runtime
- 微服务拆分
- Kubernetes 复杂部署

---

## 15. Codex 代码检查任务

请 Codex 完整检查仓库代码，并按以下顺序工作。

### 15.1 先建立真实项目地图

输出：

1. 顶层目录说明。
2. FastAPI 启动入口。
3. 路由清单。
4. 依赖装配方式。
5. Single Agent 调用链。
6. Multi-Agent 调用链。
7. SSE 调用链。
8. pending action 调用链。
9. Tool Gateway 调用链。
10. Repository 和数据库模型关系。
11. 测试结构。
12. 部署结构。

### 15.2 逐项核对本文假设

对本文提到的每个现有能力，标记：

- 已完整实现
- 部分实现
- 未实现
- 文档存在但代码不存在
- 代码存在但未接入公开路径
- 已废弃或属于旧版本

重点核对：

- 购物车
- 订单
- 支付
- pending action
- confirm
- SSE
- 幂等
- owner boundary
- recommendation schema
- deterministic ranking
- evaluation
- frontend

### 15.3 识别问题

输出：

- 逻辑 Bug
- 安全问题
- 数据所有权问题
- 幂等问题
- 事务问题
- 并发问题
- SSE 问题
- 状态机问题
- 资源泄漏
- 异常吞掉
- 类型问题
- 测试盲区
- 文档和代码不一致
- 重复代码
- 过大模块
- 不必要复杂度
- 死代码或旧路径

每个问题需要包含：

- 严重级别
- 文件路径
- 相关函数或类
- 问题说明
- 触发场景
- 建议修复方式
- 推荐测试

### 15.4 输出目标架构

基于真实代码给出：

- 保留模块
- 修改模块
- 新增模块
- 删除或归档模块
- 数据库迁移
- API 变更
- 事件协议变更
- 前端接口约定
- 兼容策略

### 15.5 输出分阶段实施计划

每个阶段需要包含：

- 目标
- 修改文件
- 新增文件
- 数据库迁移
- API
- 测试
- 风险
- 验收标准
- 是否依赖前一阶段

### 15.6 优先给出最小可交付版本

最小可交付版本必须能够完成：

```text
对话推荐
→ 商品卡片
→ Agent 时间线
→ HITL 确认加购
→ 查看购物车
→ 模拟结算
→ 创建订单
→ Mock 支付
```

### 15.7 不要直接大规模修改

在输出审查报告和改造方案前：

- 不要先重写目录。
- 不要删除旧路径。
- 不要修改数据库。
- 不要新增大量抽象。
- 不要替换核心框架。

先提供基于源码的设计方案，再按阶段实施。

---

## 16. Codex 期望输出格式

建议 Codex 最终输出以下文档：

```text
docs/
  current_architecture_audit.md
  gap_analysis.md
  target_architecture.md
  implementation_plan.md
  api_contracts.md
  database_migration_plan.md
  frontend_integration_plan.md
  test_plan.md
```

其中 `implementation_plan.md` 是唯一阶段来源；其当前顺序和每阶段文件、迁移、API/SSE、测试、风险、
回滚与验收标准必须以该文档为准。本说明书不复制该阶段表，避免再次漂移。

---

## 17. 验收标准

### 17.1 功能验收

- 用户可输入复杂数码购买需求。
- 系统返回结构化约束。
- 系统按有效匹配数量返回最多 3 个候选；不使用不满足硬约束的商品补足数量。
- 推荐包含匹配条件、妥协项和证据。
- 前端展示 Agent 执行过程。
- 用户可通过自然语言发起加购。
- 加购必须经过用户确认。
- 确认后购物车正确更新。
- 用户可修改和删除购物车商品。
- Checkout Preview 能发现库存和价格变化。
- 用户可创建订单。
- Mock Payment 可返回成功和失败。
- 用户可查看自己的订单。
- 不同用户数据严格隔离。

### 17.2 工程验收

- 核心逻辑有单元测试。
- 主流程有集成测试。
- 主流程有 E2E 测试。
- 数据库迁移可重复执行。
- API 有稳定 Schema。
- 错误码和错误响应一致。
- 订单和支付支持幂等。
- 关键状态转换可审计。
- SSE 支持取消和错误展示。
- 项目可一键本地启动。
- Demo Mode 可在无模型 Key 时运行。

### 17.3 展示验收

- README 有清晰项目定位。
- README 区分原始项目和个人贡献。
- 有架构图。
- 有在线 Demo 或一键启动。
- 有 60～90 秒演示视频。
- 有真实评估指标。
- 有已知限制。
- 面试时能在 3 分钟内完成主流程演示。

---

## 18. 面试表达重点

建议项目描述：

> 在官方单 Agent 教学项目基础上，我将其演进为面向数码产品选购的可控 Multi-Agent 决策与模拟交易系统。当前已实现 LangGraph Product、RAG、Preference、Decision 读协作，以及 Runtime Harness、Tool Gateway 和 Human-in-the-loop 两阶段确认。结构化 Catalog/SKU、确定性评分、完整购物车/订单/Mock Payment 和推荐对照评估是后续路线；只有实际实现和验证后，才应在简历或 README 中表述为已完成能力。

面试中重点说明：

- 哪些能力来自原始项目。
- 哪些能力由自己实现。
- 为什么采用 Multi-Agent。
- 为什么没有把所有逻辑交给 LLM。
- 为什么写操作需要确认。
- 为什么先使用 Mock Payment。
- 如何保证幂等、事务和用户数据隔离。
- Multi-Agent 相比 Single Agent 的真实收益和代价。
- 哪些地方存在技术债，下一步如何演进。

---

## 19. 最终目标

本轮改造完成后，项目应从：

> 架构能力丰富但缺少可视化业务闭环的 Multi-Agent 后端

升级为：

> 一个能够在线体验、完整演示、量化评估，并且能清楚说明个人贡献和工程取舍的秋招项目。
