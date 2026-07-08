# ShopMind V1 架构设计

## 项目背景

ShopMind V1 是在原 TechHub 电商 Agent Workshop 基础上改造出来的购物决策 Agent 后端项目。原项目主要用于教学 LangChain、LangGraph、LangSmith 的 Agent 生命周期，核心场景偏“电商客服”；ShopMind V1 则把它收敛成一个更适合展示和写进简历的后端项目：

- 用 FastAPI 提供 HTTP API；
- 用单个 LangChain Agent 承载购物决策逻辑；
- 用多个 LangChain Tools 访问商品、文档、用户偏好、购物车和待确认动作；
- 继续复用原项目 TechHub SQLite 数据和 Markdown 文档 RAG。

V1 的重点不是做完整电商系统，而是完成一个可运行、可测试、可解释的 Agent 后端闭环。

## V1 架构图

```mermaid
flowchart TD
    U["用户 / Postman / Swagger UI"] --> API["FastAPI Backend"]
    API --> Health["GET /api/health"]
    API --> Chat["POST /api/chat"]
    API --> Confirm["POST /api/chat/confirm"]

    Chat --> AgentDep["app.dependencies.agent.call_shopmind_agent"]
    AgentDep --> Agent["ShopMind Agent<br/>LangChain create_agent"]

    Agent --> ProductTools["Product Tools<br/>search_products<br/>get_product_detail<br/>compare_products"]
    Agent --> DocTools["Document Tools<br/>search_product_docs<br/>search_policy_docs"]
    Agent --> PrefTools["Preference Tools<br/>get_user_preferences<br/>add_user_preference"]
    Agent --> CartPrepare["Cart Tools exposed to Agent<br/>prepare_add_to_cart<br/>get_cart_items"]

    ProductTools --> SQLite["SQLite<br/>data/structured/techhub.db"]
    PrefTools --> SQLite
    CartPrepare --> SQLite
    DocTools --> VectorStore["InMemoryVectorStore<br/>TechHub Markdown Docs"]

    Confirm --> ConfirmDep["app.dependencies.agent.confirm_pending_action"]
    ConfirmDep --> SensitiveCart["Sensitive Cart Tools<br/>confirm_add_to_cart<br/>cancel_pending_action"]
    SensitiveCart --> SQLite
```

## 请求链路

### 普通购物咨询

```text
POST /api/chat
  → app/api/routes/chat.py
  → app/dependencies/agent.py
  → agents/shopmind_agent.invoke_shopmind_agent
  → ShopMind Agent
  → Tools
  → SQLite / InMemoryVectorStore
  → ChatResponse(status="completed")
```

### 加购确认

```text
POST /api/chat
  → ShopMind Agent 调用 prepare_add_to_cart
  → 写入 pending_actions
  → 返回 confirmation_required + pending_action_id

POST /api/chat/confirm
  → confirm_pending_action
  → confirmed=true 调用 confirm_add_to_cart
  → confirmed=false 调用 cancel_pending_action
  → 更新 pending_actions / cart_items
  → 返回 completed 或 cancelled
```

## 为什么 V1 采用单 Agent + 多 Tool

原 workshop 中已经有 Supervisor Multi-Agent 示例，但 ShopMind V1 暂时采用单 Agent + 多 Tool，原因是：

1. V1 的目标是做出可展示的购物决策闭环，而不是证明多 Agent 编排复杂度。
2. 当前业务边界还比较清晰：商品检索、文档检索、偏好记忆、购物车确认都可以通过 Tool 表达。
3. 单 Agent 更容易调试、测试和接入 FastAPI。
4. 对简历项目来说，“Agent 能根据用户意图动态选择工具，并完成安全加购确认”已经足够体现 Agentic 后端能力。

后续如果业务扩展到更复杂的角色分工，例如导购 Agent、售后 Agent、订单 Agent、风控 Agent，再拆 Multi-Agent 更合理。

## 为什么 V1 不使用 A2A

V1 没有采用标准 A2A 协议或分布式 Agent-to-Agent 通信。当前项目中的 Agent 和 Tools 都运行在同一个 Python 后端进程中，不涉及 Agent Card、Agent Discovery、跨服务任务生命周期或独立 Agent Server。

不使用 A2A 的原因：

- V1 没有多个独立部署的 Agent 服务；
- 业务流程主要是单用户请求内的工具调用；
- 引入 A2A 会增加部署、协议、鉴权、任务状态同步等复杂度；
- 对第一版简历项目来说，A2A 的收益低于成本。

如果后续将商品 Agent、订单 Agent、客服 Agent 独立部署为多个服务，再考虑 A2A 会更自然。

## 为什么 V1 使用 SQLite 和 InMemoryVectorStore

V1 继续使用原项目的 SQLite 和 InMemoryVectorStore：

- SQLite 已包含 TechHub 商品、订单、客户等结构化数据，足够支撑 V1 演示；
- InMemoryVectorStore 已能完成商品文档和政策文档检索；
- 避免第一阶段陷入数据库迁移、pgvector 安装、数据导入和 Docker 编排；
- 降低学习成本，让重点放在 Agent、Tool、FastAPI 和安全确认链路上。

这不是说 SQLite 适合生产大规模电商，而是它很适合作为 V1 的可运行 MVP 数据层。

## V2 演进方向

V2 可以沿以下方向增强：

- PostgreSQL + pgvector：替代 SQLite 和 InMemoryVectorStore，统一结构化数据和向量检索存储；
- LangGraph interrupt/resume：把当前 pending_actions API 确认机制升级为图状态级 HITL；
- Docker Compose：一键启动 FastAPI、PostgreSQL、pgvector 和测试环境；
- 更完整的评测体系：加入 LangSmith dataset、offline evaluation、工具调用准确率和加购安全性评测；
- 更严格的会话状态：使用 thread_id 管理多轮上下文和 pending action 生命周期。

## V2.0 第一阶段：本地 PostgreSQL + pgvector

当前 V2.0 基础设施升级的第一阶段只加入本地 PostgreSQL + pgvector 容器和统一配置读取，不改变 V1 的 Tools、Agent 或 API 行为。

启动本地数据库：

```bash
docker compose up -d postgres
```

检查容器状态：

```bash
docker compose ps postgres
docker compose logs postgres
```

默认数据库配置：

```text
POSTGRES_DB=retailpilot
POSTGRES_USER=retailpilot
POSTGRES_PASSWORD=retailpilot
DATABASE_URL=postgresql+psycopg://retailpilot:retailpilot@127.0.0.1:5432/retailpilot?connect_timeout=5
TEST_DATABASE_URL=postgresql+psycopg://retailpilot:retailpilot@127.0.0.1:5432/retailpilot_test?connect_timeout=5
VECTOR_DIMENSION=768
```

这一阶段数据库启动后还没有 schema 和业务数据。SQLite (`data/structured/techhub.db`) 与 InMemoryVectorStore 仍然是 V1 的实际运行数据层。后续阶段才会加入 schema migration、数据导入、pgvector documents 表和 Tool 改造。

## V2.0 第二阶段：SQLAlchemy + Alembic Schema

第二阶段加入 SQLAlchemy ORM models 和 Alembic migration，用于在 PostgreSQL 中创建结构化业务表：

- `customers`
- `products`
- `orders`
- `order_items`
- `user_preferences`
- `cart_items`
- `pending_actions`

本地运行 migration：

```bash
docker compose up -d postgres
conda run -n pythonLearn alembic upgrade head
```

当前阶段只建立 PostgreSQL schema，不迁移 SQLite 数据，不创建 pgvector documents 表，也不切换现有 Tools、Agent 或 API。V1 运行路径仍然继续使用 SQLite 和 InMemoryVectorStore；Repository 与 Tool 数据层迁移会在后续阶段完成。

## V2.0 第三阶段：PostgreSQL Seed

第三阶段加入结构化业务数据 seed 脚本，从 `data/structured` 下的原始 JSON 文件导入 PostgreSQL：

- `customers.json` → `customers`
- `products.json` → `products`
- `orders.json` → `orders`
- `order_items.json` → `order_items`

本地执行顺序：

```bash
docker compose up -d postgres
conda run -n pythonLearn alembic upgrade head
conda run -n pythonLearn python scripts/seed_postgres.py --clear
```

`--clear` 会先按外键反向顺序清空 `order_items`、`orders`、`products`、`customers`，再按 `customers`、`products`、`orders`、`order_items` 导入。`--dry-run` 只打印各 JSON 文件的数据条数，不连接 PostgreSQL。

这一阶段仍然不导入 `user_preferences`、`cart_items`、`pending_actions`，这些表属于运行时状态。现有 ShopMind Tools、Agent 和 API 也仍未切换到 PostgreSQL。

## V2.0 第四阶段：PostgreSQL Repository

第四阶段新增 Repository 层，为后续 Tool 数据访问迁移做准备：

- `app/repositories/products.py`：商品搜索、商品详情、按 ID/名称获取商品；
- `app/repositories/preferences.py`：用户偏好增删查，非法 preference type 归为 `other`；
- `app/repositories/cart.py`：pending action 加购确认流、购物车读取与清理。

Repository 函数接收 SQLAlchemy `Session`，返回结构化 dict/list，不使用 LangChain `@tool`，也不返回面向用户的中文回答文本。测试使用 SQLAlchemy SQLite 内存数据库和 `Base.metadata.create_all(test_engine)` 验证逻辑，不依赖 Docker 或真实 PostgreSQL。

当前阶段仍然不切换 ShopMind V1 Tools。`tools/products.py`、`tools/preferences.py`、`tools/cart.py`、Agent 和 API 继续走 SQLite / InMemoryVectorStore，直到后续 Repository 迁移任务。

## V2.0 第五阶段：结构化 Tools 迁移

第五阶段先迁移结构化数据 Tools：

- `search_products`
- `get_product_detail`
- `compare_products`
- `get_user_preferences`
- `add_user_preference`
- `clear_user_preferences`
- `prepare_add_to_cart`
- `confirm_add_to_cart`
- `cancel_pending_action`
- `get_cart_items`
- `clear_cart_items`

这些 Tool 的 LangChain 名称、输入 schema 和中文返回格式保持不变，内部结构化数据访问改为通过 `app.repositories.*` 和 SQLAlchemy `Session` 访问 PostgreSQL Repository。为了避免导入阶段依赖真实数据库连接，Tool 模块会懒加载 `SessionLocal`。

这一阶段不迁移 `tools/documents.py`，Agent 和 API 也仍保持原运行路径；RAG pgvector documents 仍未引入。

## V2.1 第一阶段：pgvector Documents Schema

V2.1 开始迁移 RAG 数据层。第一阶段只建立 pgvector documents schema，不改变现有 RAG Tool 行为。

新增 PostgreSQL extension 和表：

- `CREATE EXTENSION IF NOT EXISTS vector`
- `documents`

`documents` 表用于后续保存 markdown chunk 与 embedding：

- `doc_type`：`product` 或 `policy`
- `source_path`、`source_name`
- `product_id`、`product_name`
- `policy_name`
- `chunk_index`
- `content`
- `metadata_json`
- `embedding vector(768)`
- `embedding_provider`
- `embedding_model`
- `created_at`

索引包括：

- `doc_type`
- `product_id`
- `source_path`
- `metadata_json` GIN index
- `embedding` HNSW vector cosine index

本地运行：

```bash
docker compose up -d postgres
conda run -n pythonLearn alembic upgrade head
```

当前阶段不读取 `data/documents`，不生成 embeddings，不导入 pgvector 数据，也不修改 `tools/documents.py`。RAG 仍继续使用现有 InMemoryVectorStore，直到后续 documents index 脚本和 repository 迁移完成。

## V2.1 第二阶段：Documents pgvector Index Script

第二阶段新增 `scripts/index_documents_pgvector.py`，负责把 markdown RAG 语料导入 PostgreSQL `documents` 表。

脚本能力：

- 读取 `data/documents/products/*.md`
- 读取 `data/documents/policies/*.md`
- 复用 V1 chunk 参数：`chunk_size=1000`、`chunk_overlap=200`
- 保留 product / policy metadata
- 支持 `--dry-run`
- 支持 `--clear`
- 支持 `--doc-type all|product|policy`

本地 dry-run：

```bash
conda run -n pythonLearn python scripts/index_documents_pgvector.py --dry-run
```

真实写入：

```bash
docker compose up -d postgres
conda run -n pythonLearn alembic upgrade head
conda run -n pythonLearn python scripts/index_documents_pgvector.py --clear
```

`--dry-run` 只读取和切分 markdown，不连接 PostgreSQL，也不创建 embedding model。非 dry-run 模式会根据 `EMBEDDING_PROVIDER` 创建 embedding model，并写入 `documents` 表。

当前阶段仍然不修改 `tools/documents.py`，Agent/API 的 RAG 行为继续使用 InMemoryVectorStore。

## V2.1 第三阶段：Documents Repository

第三阶段新增 `app/repositories/documents.py`，为后续 RAG Tool 迁移做准备。

Repository 函数：

- `search_product_documents(session, query_embedding, k=3)`
- `search_policy_documents(session, query_embedding, k=2)`

生产路径使用 PostgreSQL pgvector cosine distance：

```sql
ORDER BY embedding <=> CAST(:embedding AS vector)
```

返回结构化 dict/list，包含 source、metadata、content、embedding provider/model 和可选 score。SQLite 单测环境不支持 pgvector operator，因此 Repository 提供 deterministic fallback，只按 `doc_type` 和 `id` 返回限定数量结果，用于验证过滤和返回结构。

当前阶段仍然不切换 `tools/documents.py`。RAG Tool 继续使用 InMemoryVectorStore；下一阶段再把 Tool 层接到 Documents Repository。

## V2.1 第四阶段：RAG Tools 迁移

第四阶段将 `tools/documents.py` 从 V1 InMemoryVectorStore 切换到 Documents Repository。

保持不变：

- `search_product_docs`
- `search_policy_docs`
- LangChain `@tool(response_format="content_and_artifact")`
- Tool 输入参数 `query`
- 返回给 Agent 的格式化文本和 LangChain `Document` artifacts

内部变化：

- Tool 层懒加载 `EMBEDDING_PROVIDER` 对应的 embedding model；
- 每次查询生成 query embedding；
- 通过 `app.repositories.documents.search_product_documents()` 或 `search_policy_documents()` 查询 PostgreSQL `documents` 表；
- Repository 在 PostgreSQL 下使用 pgvector cosine distance 排序；
- 单测中用 SQLite in-memory fallback 和 monkeypatch，避免依赖 Docker、真实 PostgreSQL 或真实 embedding model。

这一阶段只迁移 RAG Tool 的数据访问路径，不修改 Agent/API 的调用契约，也不引入 LangGraph interrupt/resume。

## V2.2 第一阶段：PostgreSQL Smoke Check

V2.2 第一阶段新增只读 smoke check，用于验证 V2 PostgreSQL 链路是否完整可用。

新增脚本：

- `scripts/smoke_postgres.py`

默认检查内容：

- 读取 `DATABASE_URL`，连接目标 PostgreSQL；
- 输出当前 database 和 user；
- 校验 Alembic version 为 `0002_documents_pgvector`；
- 校验 V2 结构化表、运行时状态表和 `documents` 表均存在；
- 校验 customers、products、orders、order_items 已有 seed 数据；
- 校验 documents 表已有 product / policy chunks；
- 通过 Repository 层执行商品搜索和 pgvector documents 搜索。

脚本默认只读，不执行 clear、seed、index 或任何写入操作。`--include-tools` 会额外调用 LangChain Tool 层，用于确认 `tools/products.py` 和 `tools/documents.py` 的运行路径，但会加载 embedding model，适合人工 smoke，不适合默认单测。

测试分层：

- `tests/scripts/test_smoke_postgres.py` 使用 SQLite in-memory，验证 smoke 逻辑，不依赖 Docker 或真实 PostgreSQL；
- `tests/integration/test_postgres_smoke.py` 默认跳过；
- 设置 `RUN_POSTGRES_INTEGRATION=1` 后才会连接真实 `DATABASE_URL`。

如果本机 5432 已有 PostgreSQL，应优先在现有实例中新建独立数据库，例如 `retailpilot_v2_smoke`，避免默认 Docker Compose 的 `5432:5432` 端口映射与现有数据库冲突。

## V2.2 第二阶段：PostgreSQL Health Endpoint

第二阶段在 FastAPI 中新增 PostgreSQL health endpoint，同时保持原有健康检查不变。

API：

- `GET /api/health`：原有轻量检查，只返回 `{"status": "ok"}`；
- `GET /api/health/postgres`：连接 `DATABASE_URL` 指向的 PostgreSQL，读取当前 database、user 和 `alembic_version`；
- PostgreSQL 不可用时返回 HTTP 503，并在响应 detail 中包含错误信息。

该 endpoint 只读，不执行 migration、seed、index 或 Tool 调用，适合部署后快速确认 V2 数据库连接和 schema version。

## V2.2 第三阶段：PostgreSQL Write Path Integration

第三阶段补充默认跳过的 PostgreSQL 写路径 integration tests，用于验证 Repository 在真实 PostgreSQL 上的运行时状态表行为。

新增测试：

- `tests/integration/test_postgres_write_paths.py`

覆盖内容：

- `user_preferences` 写入、读取和清理；
- `pending_actions` 创建；
- `confirm_add_to_cart` 写入 `cart_items`；
- 跨用户确认保护；
- 重复确认保护；
- 测试前后按唯一 `integration-smoke-*` user_id 清理 `user_preferences`、`cart_items` 和 `pending_actions`。

这些测试默认跳过，只有设置 `RUN_POSTGRES_INTEGRATION=1` 时才连接真实 `DATABASE_URL`。普通单测仍然使用 SQLite in-memory，不依赖 Docker 或 PostgreSQL。

## V2.2 第四阶段：PostgreSQL Tool Integration

第四阶段补充结构化 LangChain Tool 层的真实 PostgreSQL integration tests，验证 Agent 实际调用的 Tool wrapper 能通过 `SessionLocal` 访问 V2 数据库。

新增测试：

- `tests/integration/test_postgres_tools.py`

覆盖内容：

- `search_products` Tool 读取 PostgreSQL 商品数据；
- `add_user_preference`、`get_user_preferences`、`clear_user_preferences` 通过 Tool 层写入、读取和清理 PostgreSQL；
- `prepare_add_to_cart` 通过 Tool 层创建 pending action；
- `confirm_add_to_cart` 通过 Tool 层写入 cart item；
- Tool 层跨用户确认保护和重复确认保护；
- 测试使用唯一 `integration-tool-*` user_id，并在测试前后清理运行时状态表。

该阶段仍不引入 LangGraph interrupt/resume，也不改变 Agent/API 调用契约。RAG Tool 的真实 embedding 查询仍通过 `scripts/smoke_postgres.py --include-tools` 进行人工 smoke，避免默认 integration 测试每次加载 embedding model。

## V2.2 第五阶段：PostgreSQL API Integration

第五阶段补充 FastAPI 层的真实 PostgreSQL integration tests，验证 HTTP API 边界能通过 dependency 和 Tool 层访问 V2 数据库。

新增测试：

- `tests/integration/test_postgres_api.py`
- `tests/integration/test_integration_guard.py`

覆盖内容：

- `GET /api/health/postgres` 端到端读取真实 PostgreSQL 的 database、user 和 Alembic version；
- `POST /api/chat/confirm` confirmed=true 时通过 `confirm_add_to_cart` Tool 确认 pending action 并写入 `cart_items`；
- `POST /api/chat/confirm` confirmed=false 时通过 `cancel_pending_action` Tool 取消 pending action；
- 测试使用唯一 `integration-api-*` user_id，并在测试前后清理对应运行时状态。

Integration 测试默认在模块加载早期跳过，避免未设置 `RUN_POSTGRES_INTEGRATION=1` 时导入 FastAPI、Agent 或 Tool 重依赖。`test_integration_guard.py` 保证默认运行 `pytest tests/integration` 时仍有一个轻量测试被收集，避免 “no tests collected” 造成非零退出码。

## V2.2 第六阶段：PostgreSQL Bootstrap Script

第六阶段新增本地 PostgreSQL bootstrap 脚本，用于把 V2 数据库初始化、导入和验证流程收敛成一个入口。

新增脚本：

- `scripts/bootstrap_postgres.py`

默认行为：

- 只打印计划；
- 不连接数据库；
- 不执行 migration；
- 不清空或写入任何表。

只有添加 `--execute` 后才会实际执行。若执行计划包含 seed、documents index 或 integration tests 等写入/清空步骤，还必须添加 `--confirm-clear`，以确认 `DATABASE_URL` 指向的是独立开发库。

1. Alembic `upgrade head`；
2. 清空并重新导入 customers/products/orders/order_items；
3. 清空并重新索引 markdown documents 到 pgvector；
4. 运行只读 smoke check；
5. 可选运行真实 PostgreSQL integration tests。

常用命令：

```bash
conda run -n pythonLearn python scripts/bootstrap_postgres.py
conda run -n pythonLearn python scripts/bootstrap_postgres.py --execute --confirm-clear
conda run -n pythonLearn python scripts/bootstrap_postgres.py --execute --confirm-clear --skip-documents
conda run -n pythonLearn python scripts/bootstrap_postgres.py --execute --skip-seed --skip-documents --skip-smoke
```

选项：

- `--confirm-clear`：确认允许执行会清空或写入 V2 数据的步骤；
- `--skip-seed`：跳过结构化 seed 数据重导入；
- `--skip-documents`：跳过 pgvector documents 重新索引；
- `--skip-smoke`：跳过 smoke check；
- `--include-tool-smoke`：smoke 中额外调用 LangChain Tools；
- `--run-integration`：执行真实 PostgreSQL integration tests。

该脚本是本地开发和验证工具，不改变 FastAPI、Agent 或 Tool 的对外契约。
