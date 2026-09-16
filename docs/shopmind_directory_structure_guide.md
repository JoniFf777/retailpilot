# ShopMind 项目目录结构详解

> 用途：理解代码放在哪里、各层怎样协作，以及面试时如何介绍项目结构。  
> 当前仓库名是 `retailpilot`，当前产品名是 **ShopMind**。仓库仍保留早期 TechHub workshop 和 V1 单 Agent 代码，因此阅读时要区分“当前主链路”和“历史参考代码”。

## 1. 先建立整体认识

这个仓库可以分成六块：

```text
retailpilot/
├── frontend/               # React/TypeScript Web 前端
├── app/                    # FastAPI 后端、领域服务、数据库和 Agent Runtime
├── agents/                 # LangGraph 编排、专业 Agent 和历史 Agent
├── tools/                  # Agent 可以调用的商品、文档、偏好、购物车工具
├── alembic/                # PostgreSQL 数据库迁移
├── data/                   # Catalog 种子数据、RAG 文档和历史数据集
├── evaluation/             # 确定性评测、轨迹回放、检索与质量评测
├── tests/                  # 单元、API、数据库集成和架构测试
├── scripts/                # 启动、初始化、索引、清理、运维和 smoke 脚本
├── docs/                   # 架构、设计、验收、运维和简历说明
├── examples/               # API 客户端和运行配置示例
├── artifacts/              # 评测与验收生成物，不是业务源码
└── workshop_modules/       # 原始课程 notebook，不是当前产品主链路
```

最重要的代码关系可以简化为：

```text
React 页面
   ↓
frontend/src/api/client.ts
   ↓ HTTP / POST SSE
app/api/routes/
   ├── 对话请求 → app/dependencies/agent.py → Harness → LangGraph / 推荐引擎
   └── 交易请求 → app/services/ → app/repositories/ → SQLAlchemy Models
                                                   ↓
                                          PostgreSQL / pgvector
```

如果只想快速掌握项目，优先阅读：

1. `app/main.py`
2. `app/api/router.py`
3. `app/dependencies/agent.py`
4. `agents/shopmind_multi_agent/graph.py`
5. `agents/shopmind_multi_agent/recommendation_nodes.py`
6. `app/recommendation/`
7. `app/services/`
8. `frontend/src/features/`

## 2. 根目录文件

```text
retailpilot/
├── README.md
├── AGENTS.md
├── PLAN.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── docker-compose.yml
├── alembic.ini
├── config.py
├── langgraph.json
└── .github/workflows/ci.yml
```

### `README.md`

项目对外入口，包含产品说明、启动方法和主要验收命令。第一次了解项目时先看它，但具体实现状态应以 `docs/project_status.md` 和代码为准。

### `AGENTS.md`

代码代理和维护者的工作约定，记录当前实现基线、运行命令、数据库安全规则和哪些能力已经完成。它不是业务代码，但能快速判断当前版本边界。

### `PLAN.md`

项目从 V1 到 V6 的演进路线。它用于理解为什么仓库中会同时存在单 Agent、多 Agent、Runtime、治理和交易模块。已完成部分不等于当前正式发布版本。

### `pyproject.toml` 与 `uv.lock`

Python 项目元数据与依赖锁定。主要依赖包括 FastAPI、LangGraph、LangChain、SQLAlchemy、Alembic、PostgreSQL 驱动、pgvector 相关检索依赖和 pytest。

### `.env.example`

非敏感配置模板。实际 `.env` 是本机私有配置，不能提交或打印。Agent 模式、数据库地址、身份方式、Redis、RAG 和支付模拟等配置都由服务端设置控制。

### `docker-compose.yml`

本地 PostgreSQL/pgvector 服务定义。数据库是商品、运行状态、订单、支付和 Outbox 的事实存储。

### `alembic.ini`

Alembic 配置入口，实际迁移环境和版本文件在 `alembic/`。

### `config.py`

早期 Agent/workshop 的模型配置入口。当前后端更主要的运行设置集中在 `app/core/settings.py`。

### `langgraph.json`

原 workshop LangGraph deployment 的图注册配置，主要引用 `deployments/`。当前 ShopMind Web 主链路通过 FastAPI 提供服务，不应把这里的所有 graph 当成当前产品入口。

### `.github/workflows/ci.yml`

CI 质量门禁，包括后端测试、数据库集成、前端检查和评测工件等流程。

## 3. `app/`：当前后端主体

`app/` 是当前项目最重要的目录。它不是按单一技术分层，也不是完全按领域垂直切分，而是两种方式结合：

- API、Schema、Repository、Service 是常见后端分层；
- recommendation、runtime、catalog、orders、payments、outbox 是领域或平台模块。

```text
app/
├── main.py
├── api/
├── core/
├── dependencies/
├── schemas/
├── db/
├── catalog/
├── cart/
├── orders/
├── payments/
├── outbox/
├── recommendation/
├── runtime/
├── repositories/
├── services/
├── security/
├── governance/
├── operations/
└── integrations/
```

### 3.1 `app/main.py`：FastAPI 启动入口

主要职责：

1. 初始化 LangSmith 开关策略；
2. 加载服务端配置；
3. 执行生产配置预检；
4. 创建 FastAPI；
5. 注册 Correlation ID 中间件；
6. 将 `api_router` 挂到 `/api`。

应用启动对象是：

```text
app.main:app
```

本地启动最终也是加载这个对象。

### 3.2 `app/api/`：HTTP 接入层

```text
app/api/
├── router.py               # 汇总所有业务路由
├── middleware.py           # Correlation ID 中间件
├── chat_response.py        # Runtime 结果投影成公开 ChatResponse
└── routes/
    ├── chat.py             # POST /api/chat
    ├── chat_stream.py      # POST /api/chat/stream
    ├── chat_confirm.py     # 兼容确认入口
    ├── catalog.py          # 商品目录查询
    ├── pending_actions.py  # 创建、查看、确认、取消 PendingAction
    ├── cart.py             # 购物车读取、修改和删除
    ├── checkout.py         # 结算预览
    ├── orders.py           # 创建、查询和取消订单
    ├── payments.py         # 创建和查询支付尝试
    ├── owner_data.py       # 本人数据、Memory 和 Run 检查/删除
    ├── health.py           # 健康、就绪、审计、Outbox 和指标
    └── _helpers.py         # 稳定错误响应转换
```

路由层应该保持薄：

- 解析 Pydantic 请求；
- 绑定可信用户身份；
- 调用 Agent facade 或领域 Service；
- 决定 `commit/rollback`；
- 将已知错误映射成稳定 HTTP 响应。

业务规则不应全部堆在路由函数里。例如创建订单的库存校验在 `app/services/orders.py`，而不是 `app/api/routes/orders.py`。

### 3.3 `app/core/`：全局基础配置

```text
app/core/
├── settings.py             # 所有 SHOPMIND_* 服务端配置
├── logging.py              # PII-safe 结构化日志
├── time.py                 # 时间辅助函数
├── chat_errors.py          # Chat 公开错误投影
└── langsmith_policy.py     # LangSmith 启用/禁用的安全策略
```

`settings.py` 是理解运行模式的关键文件。它控制：

- 单 Agent 或多 Agent；
- 确定性或 LLM Router/Planner；
- Runtime 预算与重试；
- 身份提供方式；
- 本地或 Redis 协调；
- RAG provider 与 reranker；
- Checkout、支付、Outbox 和运维配置。

这些配置由服务端持有，API 调用方不能随意指定远程 Agent 地址、权限或身份模式。

### 3.4 `app/dependencies/`：API 与内部实现的桥梁

```text
app/dependencies/
├── agent.py                # Chat/Confirm 到 Runtime 与 Agent 的统一入口
└── security.py             # FastAPI 身份依赖和 owner 绑定
```

`agent.py` 是对话主链路的重要桥接文件：

```text
Chat Route
  → call_shopmind_agent()
  → execute_shopmind_agent_run()
  → 构造 RunRequest / RuntimePolicy / RunBudget
  → ShopMindRuntimeHarness.run()
  → 根据配置调用单 Agent 或多 Agent
  → 写意图进入 write_handoff
  → RunResult 转回兼容 ChatResponse
```

它的价值是让 API 不直接依赖 LangGraph 的内部 State，同时让 JSON Chat、SSE 和确认流程复用相同 Runtime 合同。

`security.py` 将开发环境 body user、可信 Header 或签名 Header 统一成有效身份，并在访问数据前验证 owner 一致性。

### 3.5 `app/schemas/`：公开数据合同

```text
app/schemas/
├── chat.py
├── recommendation.py
├── catalog.py
├── pending_actions.py
├── cart.py
├── checkout.py
├── orders.py
├── payments.py
└── owner_data.py
```

这里放 Pydantic 请求/响应模型：

- 定义 HTTP 接口的字段和校验；
- 生成 OpenAPI；
- 为前端生成 TypeScript 类型；
- 避免 API 直接返回 SQLAlchemy ORM 对象；
- 保持内部调试数据和公开响应的边界。

容易混淆的几个概念：

| 类型 | 所在目录 | 用途 |
| --- | --- | --- |
| Pydantic API Schema | `app/schemas/` | 网络请求和响应合同 |
| SQLAlchemy Model | `app/db/`、`app/catalog/` 等 | 数据库表映射 |
| LangGraph State | `agents/shopmind_multi_agent/state.py` | 一次图执行的工作状态 |
| Runtime Contract | `app/runtime/contracts.py` | Run、Event、Tool、Agent Task 等平台合同 |

### 3.6 数据库模型目录

数据库模型因为项目演进分布在几个目录中：

```text
app/db/
├── base.py                 # SQLAlchemy DeclarativeBase
├── session.py              # Engine、SessionLocal、FastAPI DB dependency
├── version.py              # 当前 Alembic head
└── models.py               # 兼容业务表 + Runtime/Memory/Audit/Document 表

app/catalog/models.py       # Category、Attribute、Product、SKU、Inventory
app/cart/models.py          # 新 SKU CartItem
app/orders/models.py        # Order、OrderItem、InventoryReservation
app/payments/models.py      # PaymentAttempt
app/outbox/models.py        # OutboxEvent
```

`app/db/models.py` 同时包含两类模型：

1. 早期兼容业务模型，如 Product、CartItem、PendingAction、CandidateContext；
2. 当前 Runtime 模型，如 ConversationThread、AgentRun、RunEvent、Memory、Idempotency、Audit 和 Document。

新交易链路使用拆分后的 `shopmind_*` 模型。阅读订单代码时，应看 `app/orders/models.py`，不能把历史 `Order` 模型当成当前 `ShopMindOrder`。

### 3.7 `app/repositories/`：数据访问层

```text
app/repositories/
├── catalog.py                  # Catalog/SKU/Inventory 查询
├── shopmind_cart.py            # 新购物车数据访问
├── shopmind_orders.py          # 订单查询和投影
├── shopmind_payments.py        # 支付尝试查询
├── inventory_reservations.py   # Reservation 访问
├── products.py                 # 旧商品兼容查询
├── cart.py                     # 旧购物车兼容查询
├── preferences.py              # 用户偏好
├── documents.py                # pgvector/词法文档检索
├── candidate_contexts.py       # 历史候选序号上下文
├── runtime_conversations.py    # Thread、Message、Summary
├── runtime_runs.py             # Run、Event、幂等记录
├── runtime_memory.py           # Memory 记录
├── runtime_shopping_state.py   # 多轮购物状态 CAS 持久化
├── runtime_maintenance.py      # Runtime 清理
├── governance_audit.py         # 指纹审计记录
└── owner_data.py               # 本人数据查询与删除
```

Repository 负责“怎样从数据库取或写”，不负责完整业务流程。例如：

- Repository 可以查询订单并加锁；
- Service 决定什么状态允许取消、何时释放 Reservation；
- Route 决定成功后提交还是失败后回滚。

这种拆分让数据库查询、业务规则和 HTTP 行为可以分别测试。

### 3.8 `app/services/`：交易业务编排层

```text
app/services/
├── pending_actions.py      # 动作准备、确认、取消和重放
├── cart.py                 # SKU 购物车业务规则
├── checkout.py             # 只读结算预览和签名 token
├── orders.py               # 下单、库存预占、订单取消
├── payments.py             # 支付 claim、渠道结果和 finalization
├── payment_safety.py       # 支付状态对取消/过期的安全判断
├── reservation_release.py  # 统一释放库存预占
└── order_expiration.py     # 超时订单批量处理
```

Service 层是交易一致性的核心：

- 跨多个 Repository/Model 完成一个业务用例；
- 定义状态机和错误码；
- 使用行锁、条件更新和幂等键；
- 维护事务内不变量；
- 与 Outbox 一起写入业务事件。

这里没有直接接收浏览器请求，也不应该依赖 React 页面状态。

### 3.9 `app/recommendation/`：结构化推荐领域

```text
app/recommendation/
├── gate.py                 # 判断是否进入结构化推荐
├── request.py              # 中文需求解析与规范化
├── constraints.py          # 属性值和约束比较
├── compatibility.py        # 兼容旧 Laptop 合同
├── ranking.py              # 硬过滤、加权评分和分项解释
├── service.py              # 组装 RecommendationResult
├── providers.py            # Catalog/Preference provider 抽象
├── rag.py                  # 混合检索、RRF、reranker、政策范围
├── evidence.py             # 对外证据字段清洗
├── executor.py             # 五阶段 RecommendationTask 执行器
├── session_state.py        # ShoppingSessionState 模型和多轮合并语义
└── categories/
    ├── models.py           # Category/Attribute 定义模型
    ├── registry.py         # 加载、校验和匹配品类
    ├── laptop.json
    ├── phone.json
    ├── monitor.json
    └── ...                 # 共 10 类消费电子定义
```

主要调用关系：

```text
recommendation gate
  → request parser
  → CategoryRegistry 校验
  → Catalog Provider
  → Preference Provider
  → ranking.filter_candidates / rank_candidates
  → RAG Evidence Provider
  → RecommendationResult
```

`app/recommendation/` 负责纯领域逻辑，而 LangGraph 节点在 `agents/shopmind_multi_agent/recommendation_nodes.py` 中把这些函数连接起来。

这样拆分后，过滤、排序和证据处理可以脱离 LangGraph 单独测试，也可以使用 Fake Provider 运行，不需要每个测试都连接模型和数据库。

### 3.10 `app/runtime/`：通用 Agent 运行平台

```text
app/runtime/
├── contracts.py            # Run、Event、Budget、Usage、Tool、Agent Task 合同
├── harness.py              # 一次 Run 的统一生命周期
├── context.py              # 有界 Context/Memory 选择
├── policy.py               # 服务端 RuntimePolicy 和预算
├── tool_gateway.py         # 工具能力、参数、owner、预算和审计
├── actions.py              # 通用 Action Registry 与状态定义
├── adapters.py             # 进程内 typed Agent adapter
├── http_adapter.py         # 可选远程 HTTP Agent adapter
├── plan_executor.py        # 有界串行/并行计划、重试和合并
├── trajectory_replay.py    # 运行轨迹记录与回放
├── streaming.py            # SSE 编码和流准入控制
├── coordination.py         # 本地协调合同与实现
├── redis_coordination.py   # Redis 原子协调实现
├── coordination_factory.py # 根据配置选择协调后端
└── service_monitoring.py   # 有界服务指标和 SLO 计算
```

可以把 Runtime 理解成 Agent 的“应用服务器”：

- Agent 图负责业务决策；
- Runtime 负责什么时候开始、如何编号、能调用多少工具、是否超时、怎样记录、如何重放以及怎样返回错误。

`harness.py` 的典型生命周期：

```text
接收 RunRequest
  → 创建 RunContext
  → 检查幂等重放
  → 加载有界 Context
  → 持久化 run.started
  → 调用具体 Agent executor
  → 检查预算和取消
  → 保存结果与事件
  → 返回 RunResult
```

### 3.11 安全、治理和运维目录

```text
app/security/
├── identity.py             # development/trusted/signed identity
└── audit.py                # PII-safe 审计合同

app/governance/
├── emitter.py              # 审计事实写入
├── monitoring.py           # 审计失败/恢复监控
└── owner_data.py           # 本人数据治理业务

app/operations/
├── preflight.py            # 静态生产配置检查
├── readiness.py            # PostgreSQL/迁移/协调等实时就绪检查
├── cleanup_evidence.py     # 清理证据
└── release_checks.py       # 部署、回滚、事故检查合同

app/integrations/
└── rocketmq.py             # RocketMQ Publisher 适配
```

这几层解决的是“谁可以访问”“记录什么审计事实”“服务是否适合接流量”“怎样连接外部消息基础设施”。

## 4. `agents/`：Agent 编排和专业节点

```text
agents/
├── shopmind_agent.py               # V1 单 Agent，保留作兼容/对照
├── shopmind_multi_agent/            # 当前多 Agent 主链路
├── db_agent.py                      # workshop DB Agent
├── docs_agent.py                    # workshop Docs Agent
├── sql_agent.py                     # workshop SQL Agent
├── supervisor_agent.py              # workshop Supervisor
└── supervisor_hitl_agent.py         # workshop HITL 示例
```

当前产品重点是 `agents/shopmind_multi_agent/`：

```text
agents/shopmind_multi_agent/
├── graph.py                 # 创建和编译 LangGraph，定义边与分支
├── state.py                 # ShopMindMultiAgentState
├── supervisor.py            # Supervisor 节点
├── supervisor_router.py     # 确定性/LLM 意图路由
├── planning.py              # canonical plan 与可选 LLM planner
├── product_agent.py         # 商品只读节点
├── rag_agent.py             # 文档只读节点
├── preference_agent.py      # 偏好只读节点
├── decision_agent.py        # 汇总和安全决策，不持有工具
├── product_adapter.py       # Product typed task adapter
├── rag_adapter.py           # RAG 本地/HTTP adapter
├── preference_adapter.py    # Preference typed task adapter
├── recommendation_nodes.py  # 结构化推荐五阶段 LangGraph 节点
├── permissions.py           # Agent 工具白名单与 Gateway 包装
├── write_handoff.py         # 读图到 PendingAction 写路径的交接
├── parallel_state.py        # 并行分支 State 隔离与归并
├── observability.py         # 图内步骤事件
└── prompts.py               # Agent prompt 常量
```

### `graph.py` 是怎样工作的

图从 Supervisor 开始，然后经过 Recommendation Gate：

```text
START
  → supervisor
  → recommendation_gate
       ├── 普通读请求 → Product/RAG/Preference → Decision
       ├── 结构化推荐 → Catalog → Preference → Ranking → Evidence → Decision
       ├── 新任务合同 → RecommendationTaskExecutor
       ├── 澄清/不支持 → RecommendationResolution
       └── 写意图 → 由 API bridge 交给 write_handoff
  → END
```

通用 Product/RAG/Preference 任务可以根据计划有界并行；结构化推荐默认是有依赖的五阶段链路，不应该讲成“五个 Agent 同时调用大模型”。

### 为什么 Adapter 与 Agent 文件分开

以 Product 为例：

- `product_agent.py` 定义具体节点行为；
- `product_adapter.py` 将 LangGraph State 转成 `AgentTask`；
- `app/runtime/adapters.py` 定义统一传输无关合同；
- `plan_executor.py` 只依赖合同，不关心执行发生在本地函数还是 HTTP 服务。

这样可以在不改变 Planner 的情况下替换传输方式，并对本地/远程结果做等价性测试。

## 5. `tools/`：Agent 的业务能力接口

```text
tools/
├── products.py          # 商品搜索、详情和对比
├── documents.py         # 商品/政策文档向量检索
├── preferences.py       # 偏好读取与兼容写工具
├── cart.py              # 加购准备、确认、取消等兼容工具
└── database.py          # workshop 数据库工具
```

Tool 与 Repository 的区别：

| 层 | 面向谁 | 返回内容 |
| --- | --- | --- |
| Tool | Agent/LLM | 经过格式化、适合模型理解的结果或 artifact |
| Repository | Python 业务代码 | 结构化数据库记录或领域投影 |

Tool 通常通过 Repository 访问数据库，并在多 Agent 路径中由 `permissions.py` 和 `ToolGateway` 施加权限与预算。

读 Agent 的工具集合是白名单：Product Agent 不能借用购物车写工具，Decision Agent 没有工具。

## 6. `frontend/`：React Web 应用

```text
frontend/
├── package.json
├── vite.config.ts
├── openapi.json
├── src/
│   ├── main.tsx
│   ├── app/
│   ├── api/
│   ├── features/
│   ├── styles/
│   └── test/
├── e2e/
└── scripts/
```

### 6.1 `frontend/src/app/`：应用壳和路由

```text
app/
├── App.tsx               # 侧栏、导航和 Outlet 页面框架
├── router.tsx            # URL 到页面组件的映射
├── providers.tsx         # TanStack Query 与 Session Provider
├── session.tsx           # 开发/生产身份上下文
├── sessionContext.ts
├── useSession.ts
└── id.ts                 # 前端 ID 辅助逻辑
```

当前主要页面：

| 路径 | 页面 |
| --- | --- |
| `/` | 对话与推荐工作台 |
| `/catalog` | 商品品类列表 |
| `/catalog/:category/:product` | 商品和 SKU 详情 |
| `/checkout` | 结算预览与下单 |
| `/orders` | 订单列表 |
| `/orders/:orderId` | 订单、支付和状态详情 |
| `/privacy` | 本人数据与 Memory 管理 |
| `/runs` | 本人 Run/Trace 检查 |
| `/status` | 服务健康与就绪状态 |

### 6.2 `frontend/src/api/`：前后端合同和请求

```text
api/
├── openapi.generated.ts  # 根据后端 OpenAPI 自动生成
├── contracts.ts          # 为页面提供稳定类型别名
├── client.ts             # REST 与 POST SSE 客户端
├── sse.ts                # SSE frame 解析
├── sseTypes.ts           # 流式事件类型
└── errors.ts             # 统一 API 错误解析
```

`client.ts` 统一处理 `/api` 前缀、JSON、Idempotency-Key 和错误。开发时 `vite.config.ts` 将 `/api` 代理到 FastAPI 的 `127.0.0.1:8000`。

OpenAPI 类型生成链路：

```text
FastAPI Pydantic Schema
  → scripts/export_openapi.py
  → frontend/openapi.json
  → frontend/scripts/generate-api-types.mjs
  → frontend/src/api/openapi.generated.ts
  → contracts.ts / 页面组件
```

### 6.3 `frontend/src/features/`：按用户功能组织页面

```text
features/
├── chat/             # 对话、SSE 状态、消息和安全重试
├── recommendation/   # 推荐卡、约束、评分、证据和对比
├── actions/          # PendingAction Drawer
├── catalog/          # 商品浏览和 SKU 详情
├── cart/             # 购物车面板、数量修改和确认框
├── checkout/         # Checkout Preview 和创建订单
├── orders/           # 订单列表、详情、支付和 Attempt 历史
├── privacy/          # Memory/本人数据操作
├── runs/             # Run/Trace 检查
└── status/           # Health/Readiness 页面
```

这个目录采用“功能内聚”方式：一个功能的组件、类型辅助、错误映射、Query Key 和测试尽量放在一起。

例如一次对话在前端的主要路径是：

```text
ChatPage.tsx
  → shopMindApi.streamChat()
  → sse.ts 解析事件
  → streamReducer.ts 管理连接/运行/完成/失败状态
  → AssistantMessage.tsx
  → RecommendationPanel.tsx
  → RecommendationCard / ScoreBreakdown / Evidence
```

### 6.4 前端测试与工程文件

```text
frontend/e2e/                         # Playwright 浏览器测试
frontend/playwright.config.ts         # mocked/offline 测试配置
frontend/playwright.live.config.ts    # 真实 FastAPI/PostgreSQL 测试配置
frontend/src/**/*.test.ts(x)          # Vitest/Testing Library
frontend/scripts/check-bundle-budget.mjs
frontend/scripts/generate-api-types.mjs
```

`package.json` 提供 lint、typecheck、test、e2e、build、bundle budget 和 API 类型生成命令。

## 7. `alembic/`：数据库结构演进

```text
alembic/
├── env.py
└── versions/
    ├── 0001_create_structured_business_tables.py
    ├── 0002_create_documents_pgvector_table.py
    ├── 0003_create_candidate_contexts.py
    ├── 0004_create_runtime_persistence.py
    ├── 0005_runtime_memory_records.py
    ├── 0006_action_registry_fields.py
    ├── 0007_governance_audit.py
    ├── 0008_shopmind_catalog_identity.py
    ├── 0009_shopmind_skus_inventory.py
    ├── 0010_pending_action_contract.py
    ├── 0011_shopmind_cart.py
    ├── 0012_shopmind_orders.py
    ├── 0013_shopmind_payments.py
    ├── 0014_shopmind_outbox_events.py
    └── 0015_shopmind_order_expiration.py
```

迁移文件直接体现项目演进：

```text
基础业务表
  → pgvector 文档
  → Agent 候选上下文
  → Runtime/Memory/Action/Governance
  → Catalog/SKU/Inventory
  → PendingAction/Cart
  → Order/Reservation
  → Payment
  → Outbox
  → Order Expiration
```

当前 migration head 在 `app/db/version.py` 中固定为 `0015_shopmind_order_expiration`，Readiness 会检查实际数据库是否到达该版本。

## 8. `data/`：商品种子和 RAG 语料

```text
data/
├── catalog/                # 当前 10 类 Catalog JSON 种子
├── documents/
│   ├── products/           # SKU/商品说明 Markdown
│   └── policies/           # 退货、保修、配送等政策
├── structured/             # 早期 TechHub 结构化数据
└── data_generation/        # 历史数据生成和 embedding 辅助脚本
```

要区分两个概念：

- `app/recommendation/categories/*.json` 定义属性规则和排序语义；
- `data/catalog/*_catalog.json` 保存实际商品、SKU、价格和库存种子。

前者回答“笔记本有哪些属性、怎样比较”，后者回答“数据库里有哪些笔记本 SKU”。

`data/documents/` 的内容由索引脚本切分并写入 PostgreSQL `documents`/pgvector 表，为 RAG 提供商品和政策证据。

## 9. `app/outbox/` 与消息发布

```text
app/outbox/
├── contracts.py        # 版本化事件 envelope
├── models.py           # OutboxEvent ORM
├── repository.py       # enqueue、claim、完成、失败、redrive
├── publisher.py        # 发布循环与故障处理
└── worker.py           # Worker 对外入口

app/integrations/rocketmq.py   # 实际 MQ adapter
scripts/run_outbox_publisher.py
scripts/inspect_outbox.py
scripts/redrive_outbox.py
```

Outbox 不是一个单文件功能，而是横跨：

- Service 在业务事务中调用 `enqueue_event`；
- Model 保存待发送事实；
- Repository 用租约和 `FOR UPDATE SKIP LOCKED` 领取；
- Publisher 在事务外调用 RocketMQ；
- 运维脚本检查积压或重新投递死信。

当前实现的是 Producer/Publisher 侧；没有 Consumer/Inbox。

## 10. `evaluation/`：Agent 与系统评测

```text
evaluation/
├── run_*_eval.py                 # 命令行入口
├── shopmind_*_eval.py            # 对应评测逻辑和案例
├── catalog/v6_evaluation_catalog.json
├── baselines/                    # 已接受确定性基线
├── quality_metrics.py            # 推荐质量指标
├── retrieval_metrics.py          # Recall@K、MRR 等检索指标
├── retrieval_capture.py          # 真实检索记录合同
├── run_retrieval_capture.py
├── run_simulated_eval.py         # 合成需求/检索 smoke
└── run_ablation_eval.py          # 合成报告框架
```

主要评测方向：

- Router/Planner 策略；
- 并行计划轨迹；
- 本地/HTTP Adapter 等价性；
- Action 创建、编辑、确认和重放；
- 故障与重启恢复；
- Redis/本地协调等价性；
- 治理、发布和回滚检查；
- 推荐约束与检索指标。

`run_*` 通常负责参数解析、执行和写 JSON artifact；`shopmind_*` 保存具体案例和断言逻辑。

合成评测主要证明合同稳定，不能替代真实用户质量评测。`run_ablation_eval.py` 当前也不能作为真实四路模型/架构收益证明。

## 11. `tests/`：按源码结构镜像测试

```text
tests/
├── agents/             # 路由、权限、Planner、Adapter 和图
├── recommendation/     # 解析、Schema、过滤、排序和推荐图
├── runtime/            # Harness、Context、Gateway、协调和回放
├── api/                # FastAPI 合同和错误边界
├── catalog/            # Catalog 模型、种子和迁移
├── cart/               # PendingAction/Cart Service
├── repositories/       # 数据访问层
├── governance/         # 审计和本人数据
├── security/           # 身份与审计合同
├── operations/         # Preflight/Readiness/Release checks
├── evaluation/         # 评测器本身的回归
├── scripts/            # 运维脚本测试
├── unit/               # Checkout、Payment、Outbox 等纯单元测试
└── integration/        # 真实 PostgreSQL/Redis 集成与并发测试
```

最有简历价值的是 `tests/integration/` 中的真实状态验证：

- `test_phase4_postgres_orders.py`：最后库存竞争、同 key 并发、多 SKU 锁顺序和整单回滚；
- `test_phase5_postgres_payments.py`：同 key 支付、双支付竞争、渠道成功恢复、支付与取消竞态；
- `test_phase6_postgres_outbox.py`：多 worker claim、租约恢复、发布崩溃窗口、死信和 redrive；
- `test_agent_write_hitl_postgres.py`：Agent 写意图到数据库动作生命周期；
- `test_chat_retry_idempotency_postgres.py`：Chat 响应丢失后的幂等恢复；
- `test_redis_coordination_integration.py`：真实 Redis 原子协调。

单元测试验证函数和合同，API 测试验证网络边界，Integration 测试验证 PostgreSQL/Redis 真正的锁与事务行为。三者不能相互替代。

## 12. `scripts/`：开发、数据和运维命令

```text
scripts/
├── start_shopmind.ps1              # 统一开发/测试/评测启动入口
├── start_shopmind_demo.ps1         # Core Demo 启动
├── prepare_shopmind_demo.py        # 幂等准备 Demo 数据库
├── bootstrap_postgres.py           # 数据库初始化计划/执行
├── seed_postgres.py                # 历史结构化种子
├── seed_shopmind_catalog.py        # 新 Catalog/SKU 种子
├── index_documents_pgvector.py     # RAG 文档索引
├── validate_shopmind_catalog.py    # Catalog 数据质量检查
├── smoke_postgres.py               # 数据库只读 smoke
├── smoke_v3_handoff.py             # Chat/PendingAction API smoke
├── smoke_shopmind_demo.py          # 完整 Demo 验证
├── export_openapi.py               # 导出前端 API 合同
├── cleanup_candidate_contexts.py   # 清理过期候选
├── cleanup_runtime_persistence.py  # Runtime retention 清理
├── expire_orders.py                # 过期订单释放预占
├── run_outbox_publisher.py         # Outbox worker
├── inspect_outbox.py               # 无 payload 运维快照
├── redrive_outbox.py               # 显式重投死信
├── check_production_config.py      # 静态生产配置预检
├── check_deployment_readiness.py   # 实时部署就绪检查
└── check_release_operations.py     # 发布/回滚/事故检查
```

脚本不是随意的开发辅助代码，它们构成项目的本地运行、数据准备和运维入口。破坏性种子操作要求明确确认，日常开发优先使用 smoke 和幂等 Demo 准备。

## 13. `docs/`：文档如何分类

文档数量较多，建议按用途理解：

| 用途 | 文件 |
| --- | --- |
| 当前状态 | `project_status.md` |
| 项目简介 | `project_introduction.md`、`shopmind_project_plain_explanation.md` |
| 总体架构 | `architecture.md`、`shopmind_architecture_and_resume_review.md` |
| Runtime 设计 | `agent_runtime_design.md` |
| 推荐合同 | `recommendation_contract_design.md` |
| Catalog/SKU | `catalog_and_sku_design.md` |
| 库存/订单/支付 | `inventory_order_payment_design.md` |
| Outbox | `rocketmq_outbox_design.md` |
| API | `api_design.md`、`api_contracts.md` |
| 本地开发 | `development.md`、`demo_runbook.md` |
| 面试准备 | `interview_guide.md`、本文及简历总结 |
| 阶段记录 | `phase*_implementation_report.md` |
| 历史版本 | `v2_*`、`v3_*`、`v6_release_candidate_notes.md` |

阶段报告用于追溯当时做了什么，不能替代当前状态文档。

## 14. 历史和辅助目录

### `workshop_modules/`

原 TechHub Agent Engineering workshop 的 notebook，适合学习 LangChain/LangGraph/LangSmith 生命周期，不是当前 ShopMind Web 的运行入口。

### `deployments/`

原 workshop Agent 的 LangGraph deployment wrapper，由 `langgraph.json` 引用。当前 ShopMind 主应用入口是 `app.main:app`。

### `simulations/`

针对已部署 workshop Agent 的多轮客服场景模拟，不是当前 ShopMind 本地推荐质量评测主入口。

### `evaluators/`

早期 LangSmith evaluator，例如 LLM-as-Judge 和工具调用计数。当前默认离线评测主要在 `evaluation/`。

### `artifacts/`

评测 JSON、CI 验收、发布检查和本地分析结果。它们是生成物或验证证据，不是运行时代码，也不能简单把不同批次的数字相加。

### `.local/`

本机路径、容器和运行状态记录，已被 Git 忽略。不能把其中的机器信息或密钥复制到跟踪文档。

### `.venv/`、缓存和临时目录

`.venv`、`.pytest_cache`、`__pycache__`、HuggingFace 缓存、pytest 临时目录、`node_modules`、`dist` 都不是项目源码，介绍目录结构时可以忽略。

## 15. 三条主链路怎样穿过目录

### 15.1 推荐请求

```text
frontend/src/features/chat/ChatPage.tsx
  → frontend/src/api/client.ts
  → app/api/routes/chat_stream.py 或 chat.py
  → app/dependencies/agent.py
  → app/runtime/harness.py
  → agents/shopmind_multi_agent/graph.py
  → agents/shopmind_multi_agent/recommendation_nodes.py
  → app/recommendation/request.py
  → app/recommendation/categories/
  → app/recommendation/ranking.py
  → app/recommendation/rag.py
  → app/repositories/catalog.py / documents.py / preferences.py
  → PostgreSQL
  → RecommendationResult
  → frontend/src/features/recommendation/
```

这里体现了：前端功能 → HTTP → Runtime → Agent 编排 → 推荐领域 → 数据访问 → 数据库。

### 15.2 确认加购

```text
RecommendationCard / Catalog Product Page
  → frontend/src/api/client.ts
  → app/api/routes/pending_actions.py
  → app/services/pending_actions.py
  → app/repositories/runtime_runs.py / catalog.py / shopmind_cart.py
  → PendingAction 写入
  → 用户在 ActionDrawer 确认
  → 再次调用 pending_actions route/service
  → 锁定并校验动作
  → upsert SKU CartItem
  → 返回 CartActionOutcome
  → frontend/src/features/cart/CartPanel.tsx 刷新
```

这条链路体现 Agent 的推荐和真正业务写入是两个阶段。

### 15.3 下单和支付

```text
CartPanel
  → CheckoutPage
  → app/api/routes/checkout.py
  → app/services/checkout.py
  → 签名 Checkout Token

CheckoutPage 创建订单
  → app/api/routes/orders.py
  → app/services/orders.py
  → app/repositories/shopmind_orders.py
  → CatalogInventory / Order / Reservation / Outbox

OrderDetailPage 发起支付
  → app/api/routes/payments.py
  → app/services/payments.py
  → app/payments/providers.py
  → PaymentAttempt provider_succeeded
  → 锁定 Order / Reservation / Inventory 完成 finalization
  → app/outbox/repository.py 写支付成功事件
```

这里体现 API、Service、Repository、Model 和 Outbox 的分层。

## 16. 面试时如何介绍目录结构

可以用下面这段话：

> 项目是前后端分离的模块化单体。前端放在 `frontend`，按 chat、recommendation、cart、checkout、orders 等业务功能组织，通过 OpenAPI 生成的类型调用 FastAPI。后端主体在 `app`，API Route 只处理协议和事务提交，交易规则放在 `services`，数据库访问放在 `repositories`，ORM 与 Pydantic Schema 分开。多 Agent 编排在 `agents/shopmind_multi_agent`，结构化推荐逻辑单独放在 `app/recommendation`，通用 Agent 生命周期、预算、权限和幂等能力放在 `app/runtime`。数据库迁移在 `alembic`，真实 PostgreSQL 并发验收在 `tests/integration`，运行和运维入口在 `scripts`。

如果面试官继续追问“为什么这么拆”，可以回答：

- Agent 图只负责编排，不把 SQL 和交易规则写进节点；
- 推荐规则脱离 LangGraph，方便确定性测试和替换 Provider；
- Route、Service、Repository 分开，便于分别验证 HTTP、业务状态机和数据库行为；
- Runtime 与具体 Agent 分开，让幂等、预算、权限、事件和回放可以复用；
- 前端以功能为单位组织，并以 OpenAPI 生成类型减少接口漂移。

## 17. 推荐阅读顺序

### 第一阶段：看懂产品入口

1. `docs/shopmind_project_plain_explanation.md`
2. `frontend/src/app/router.tsx`
3. `app/api/router.py`
4. `app/main.py`

目标：知道用户有哪些页面和 API。

### 第二阶段：看懂推荐

1. `app/dependencies/agent.py`
2. `agents/shopmind_multi_agent/graph.py`
3. `agents/shopmind_multi_agent/state.py`
4. `agents/shopmind_multi_agent/recommendation_nodes.py`
5. `app/recommendation/request.py`
6. `app/recommendation/ranking.py`
7. `app/recommendation/rag.py`

目标：能说明一句自然语言怎样变成推荐结果。

### 第三阶段：看懂安全写入和交易

1. `app/services/pending_actions.py`
2. `app/services/cart.py`
3. `app/services/checkout.py`
4. `app/services/orders.py`
5. `app/services/payments.py`
6. `app/outbox/repository.py`
7. `app/outbox/publisher.py`

目标：能说明确认、库存、支付和消息失败如何处理。

### 第四阶段：看懂工程保障

1. `app/runtime/contracts.py`
2. `app/runtime/harness.py`
3. `app/runtime/tool_gateway.py`
4. `app/runtime/plan_executor.py`
5. `tests/integration/`
6. `evaluation/`

目标：能说明系统如何限制 Agent、保存运行并验证故障恢复。

## 18. 最后用一张表记住目录职责

| 目录 | 一句话职责 |
| --- | --- |
| `frontend/` | 用户界面和浏览器状态 |
| `app/api/` | HTTP 接口与公开错误合同 |
| `app/dependencies/` | API 到 Agent/身份实现的桥梁 |
| `agents/shopmind_multi_agent/` | LangGraph 业务编排 |
| `app/recommendation/` | 可测试的推荐领域逻辑 |
| `app/runtime/` | Agent 运行、权限、预算、事件和协调 |
| `tools/` | Agent 可调用的业务能力 |
| `app/services/` | 交易状态机与事务编排 |
| `app/repositories/` | 数据库查询和持久化 |
| `app/schemas/` | HTTP/Pydantic 数据合同 |
| `app/*/models.py` | SQLAlchemy 数据表映射 |
| `alembic/` | 数据库 Schema 演进 |
| `data/` | 商品种子和 RAG 文档 |
| `evaluation/` | Agent/推荐确定性评测 |
| `tests/` | 分层测试与真实数据库并发验收 |
| `scripts/` | 启动、初始化、清理、smoke 和运维 |
| `docs/` | 当前设计、验收记录和使用说明 |

真正需要记住的结构是：

```text
页面 → API → Agent 编排或领域 Service → Repository → PostgreSQL
                   ↓
          Runtime 统一管理权限、预算、事件和幂等
```

这就是整个 ShopMind 代码目录的主干。
