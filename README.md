# AI Engineering Lifecycle on LangSmith Platform

这是一个基于 LangChain、LangGraph 和 LangSmith 的 AI engineering lifecycle workshop 项目，原始场景是为虚构电商 TechHub 构建 customer support Agent。当前仓库已在此基础上扩展出 ShopMind V1：一个面向中文用户的购物决策 Agent 后端项目。

<div align="center">
    <img src="images/main_graphic.png">
</div>

## ShopMind V1：Shopping Decision Agent Backend

本仓库已扩展为 **ShopMind V1**，即一个基于 FastAPI + LangChain Agent 的中文购物决策后端。它复用原 TechHub workshop 的 dataset 和 RAG documents，并新增 Agent API、商品工具、用户偏好记忆和基于确认机制的加购流程。

### ShopMind V1 功能

- **FastAPI backend**
  - `GET /api/health`
  - `POST /api/chat`
  - `POST /api/chat/confirm`
- **Single ShopMind Agent**
  - 使用 LangChain `create_agent` 构建
  - 中文 system prompt
  - 基于 Tool-calling 的购物决策流程
- **Product tools**
  - 商品搜索
  - 商品详情查询
  - 商品对比
- **RAG document tools**
  - 商品规格检索
  - 政策文档检索
- **User preference memory**
  - 读取用户偏好
  - 保存 budget、brand、usage、style、avoid 等长期偏好
- **Confirmation-based cart flow**
  - Agent 创建 `pending_actions`
  - API confirmation endpoint 执行或取消加购
  - 敏感购物车写入工具不直接暴露给 Agent
- **Automated tests**
  - API tests
  - 使用 mock model 的 Agent tests
  - 覆盖 product、preference、cart 行为的 Tool tests

### 技术栈

- **Backend:** FastAPI
- **Agent:** LangChain `create_agent`
- **Agent orchestration foundation:** LangGraph-compatible agent graphs
- **LLM providers:** 通过 LangChain model initialization 接入 OpenAI / Anthropic
- **Data:** SQLite (`data/structured/techhub.db`)
- **RAG:** Markdown documents + InMemoryVectorStore
- **Testing:** pytest + httpx
- **Observability / evaluation foundation:** 保留 LangSmith workshop 组件

### 运行 FastAPI

```bash
conda run -n pythonLearn python -m uvicorn app.main:app --reload
```

API 文档：

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/redoc

### V2.0 本地 PostgreSQL（可选）

V2.0 基础设施升级会引入 PostgreSQL + pgvector。当前阶段只提供本地数据库容器和统一配置读取，还没有迁移 SQLite 数据，也没有改造现有 Tools、Agent 或 API。

启动数据库：

```bash
docker compose up -d postgres
```

检查容器状态：

```bash
docker compose ps postgres
docker compose logs postgres
```

默认连接配置见 `.env.example`：

```text
DATABASE_URL=postgresql+psycopg://retailpilot:retailpilot@127.0.0.1:5432/retailpilot?connect_timeout=5
TEST_DATABASE_URL=postgresql+psycopg://retailpilot:retailpilot@127.0.0.1:5432/retailpilot_test?connect_timeout=5
VECTOR_DIMENSION=768
```

注意：此阶段数据库启动后是空的。后续步骤才会加入 schema migration、数据导入、pgvector 文档索引和 Tool 数据层改造。

创建 V2.0 结构化业务表：

```bash
conda run -n pythonLearn alembic upgrade head
```

这会创建 `customers`、`products`、`orders`、`order_items`、`user_preferences`、`cart_items` 和 `pending_actions`。当前阶段仍然不会导入 SQLite 数据，也不会让现有 Tools 切换到 PostgreSQL。

导入原始结构化数据：

```bash
conda run -n pythonLearn python scripts/seed_postgres.py --clear
```

seed 脚本会从 `data/structured/customers.json`、`products.json`、`orders.json` 和 `order_items.json` 导入 PostgreSQL。`user_preferences`、`cart_items` 和 `pending_actions` 是运行时状态表，不会由 seed 脚本导入。

### 运行测试

```bash
conda run -n pythonLearn python -m pytest tests/agents/test_shopmind_agent.py tests/tools/test_cart.py tests/tools/test_preferences.py tests/tools/test_products.py tests/api
```

当前验证结果：

```text
38 passed
```

### ShopMind V1 设计文档

- [架构设计](docs/architecture.md)
- [Tools 设计](docs/tools_design.md)
- [API 设计](docs/api_design.md)
- [安全设计](docs/safety_design.md)

### LangSmith Evaluation

ShopMind V1 已接入 LangSmith evaluation，用于检查 tool calls、response status、敏感操作安全性和回答关键词。

设置 LangSmith 环境变量：

```bash
# Required for LangSmith dataset/evaluation
set LANGSMITH_API_KEY=your_langsmith_api_key

# Optional but recommended for trace collection
set LANGSMITH_TRACING=true
set LANGSMITH_PROJECT=shopmind-v1
```

创建或刷新 evaluation dataset：

```bash
conda run -n pythonLearn python evaluation/create_shopmind_dataset.py
```

运行 evaluation：

```bash
conda run -n pythonLearn python evaluation/run_langsmith_eval.py
```

默认 evaluation 使用确定性的规则型 evaluators：

- `expected_tools_evaluator`
- `forbidden_tools_evaluator`
- `status_evaluator`
- `expected_keywords_evaluator`
- `count_total_tool_calls_evaluator`

现有 `correctness_evaluator` 也可以复用，但它是 LLM-as-Judge evaluator，会产生额外模型调用成本。需要时请显式开启：

```bash
set INCLUDE_CORRECTNESS_EVALUATOR=true
conda run -n pythonLearn python evaluation/run_langsmith_eval.py
```

### V2 Roadmap

- PostgreSQL + pgvector：用于结构化数据和 vector search 持久化
- LangGraph interrupt/resume：实现更正式的 human-in-the-loop confirmation
- Docker Compose：提供可复现的本地部署
- 更强的 auth/session model：替代调用方直接传入 `user_id`
- 更完整的 LangSmith evaluation datasets 和 regression checks
- pending action 过期机制、audit logs 和更严格的 transaction handling

## 原 Workshop 会构建什么

原 workshop 会构建一个 customer support Agent 系统，包含：

- **Multi-agent architecture**：由 Supervisor 协调 Database Agent 和 Documents Agent；
- **Human-in-the-loop (HITL)**：使用 LangGraph primitives 完成客户验证；
- **Evaluation-driven development**：通过 offline evaluation 发现并修复瓶颈；
- **Production deployment**：部署到 LangSmith，并结合 online evaluation 和 data flywheel 持续改进。

## 快速设置

原 workshop 使用 [uv](https://docs.astral.sh/uv/) 管理 Python 依赖。如果本地尚未安装：

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

然后设置 workshop 环境：

```bash
# Clone repository
git clone https://github.com/langchain-ai/langsmith-agent-lifecycle-workshop.git
cd langsmith-agent-lifecycle-workshop

# Install dependencies (creates virtual environment automatically)
uv sync

# Configure API keys
cp .env.example .env
# Edit .env and add your API keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   LANGSMITH_API_KEY=lsv2_pt_...

# Build vectorstore (one-time setup, ~60 seconds)
uv run python data/data_generation/build_vectorstore.py

# Launch Jupyter
uv run jupyter lab
```

### Backend API（可选）

当前仓库已包含 ShopMind / RetailPilot API 层的 FastAPI backend。`/api/chat` 会调用独立的 ShopMind Agent。

```bash
# Start the FastAPI backend
conda run -n pythonLearn python -m uvicorn app.main:app --reload

# Health check
curl http://127.0.0.1:8000/api/health

# Chat endpoint
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Add TECH-KEY-010 to my cart\",\"user_id\":\"demo-user\",\"thread_id\":\"demo-thread\"}"

# Confirm a pending add-to-cart action returned by /api/chat
curl -X POST http://127.0.0.1:8000/api/chat/confirm \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"demo-user\",\"pending_action_id\":\"<pending_action_id>\",\"confirmed\":true,\"thread_id\":\"demo-thread\"}"
```

启动后可以访问交互式 API 文档：

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/redoc

运行 API 测试：

```bash
conda run -n pythonLearn python -m pytest tests/api
```

### V2.0 PostgreSQL / pgvector（可选）

本地 PostgreSQL + pgvector 由 Docker Compose 提供：

```bash
docker compose up -d postgres
docker compose ps postgres
```

当前阶段只是启动数据库并提供 `app/core/settings.py` 统一读取 `DATABASE_URL`、`TEST_DATABASE_URL` 和 `VECTOR_DIMENSION`。SQLite 数据、Markdown RAG documents 和现有 Tools 仍然按 V1 路径运行，尚未迁移到 PostgreSQL 或 pgvector。

如果需要在本地 PostgreSQL 中创建 V2.0 结构化 schema，先启动容器，然后运行 Alembic：

```bash
docker compose up -d postgres
conda run -n pythonLearn alembic upgrade head
conda run -n pythonLearn python scripts/seed_postgres.py --clear
```

当前 migration 只创建结构化业务表，不创建 pgvector documents 表；seed 脚本只导入 customers、products、orders 和 order_items。RAG 迁移会放到 V2.1。现有 ShopMind V1 Tools、Agent 和 API 仍继续使用 SQLite / InMemoryVectorStore。

V2.0 也新增了 PostgreSQL Repository 层：

- `app/repositories/products.py`
- `app/repositories/preferences.py`
- `app/repositories/cart.py`

这些 Repository 使用 SQLAlchemy `Session` 访问 PostgreSQL 业务表，返回结构化 dict/list，供后续 Tools 迁移使用。当前 ShopMind V1 的 `tools/products.py`、`tools/preferences.py`、`tools/cart.py` 尚未切换到 Repository，运行时仍使用 SQLite。

Tools 已开始分批切到 Repository：

- `tools/products.py` 保持 `search_products`、`get_product_detail`、`compare_products` 的 Tool 名称和中文返回格式；
- `tools/preferences.py` 保持用户偏好 Tool 名称和中文返回格式；
- `tools/cart.py` 保持 pending action 加购确认流、跨用户保护、重复确认保护和中文返回格式；
- 内部结构化数据访问改走 `app.repositories.*`；
- Tool 测试使用 SQLAlchemy SQLite in-memory session mock Repository 层，不依赖 Docker 或真实 PostgreSQL。

`tools/documents.py` 已在 V2.1 第四阶段切换到 Documents Repository；Agent 和 API 的调用契约保持不变。

V2.1 开始引入 pgvector RAG schema：

- Alembic migration 会执行 `CREATE EXTENSION IF NOT EXISTS vector`；
- 新增 `documents` 表，用于后续保存 markdown chunks、metadata 和 embedding；
- 当前 embedding 列维度为 `vector(768)`，匹配默认 HuggingFace `sentence-transformers/all-mpnet-base-v2`；
- 当前阶段只创建 schema，不导入 markdown documents，也不切换 `tools/documents.py`。

运行到最新 schema：

```bash
docker compose up -d postgres
conda run -n pythonLearn alembic upgrade head
```

索引 markdown documents 到 pgvector：

```bash
# 只读取和切分文档，不连接数据库、不生成 embeddings
conda run -n pythonLearn python scripts/index_documents_pgvector.py --dry-run

# 写入 PostgreSQL documents 表
conda run -n pythonLearn python scripts/index_documents_pgvector.py --clear
```

也可以只处理一种文档类型：

```bash
conda run -n pythonLearn python scripts/index_documents_pgvector.py --dry-run --doc-type policy
```

当前脚本会读取 `data/documents/products/*.md` 和 `data/documents/policies/*.md`，切分 chunk，并在非 dry-run 模式下生成 embeddings 后写入 `documents` 表。

V2.1 也新增了 Documents Repository：

- `app/repositories/documents.py`
- `search_product_documents(session, query_embedding, k=3)`
- `search_policy_documents(session, query_embedding, k=2)`

Repository 在 PostgreSQL 下使用 pgvector cosine distance 排序；在 SQLite 单测下使用 deterministic fallback，避免测试依赖 Docker 或 pgvector。

V2.1 第四阶段已将 `tools/documents.py` 切换到 Documents Repository：

- `search_product_docs` 和 `search_policy_docs` 的 Tool 名称、输入参数和 `content_and_artifact` 返回格式保持不变；
- Tool 内部会根据 `EMBEDDING_PROVIDER` 懒加载 embedding model；
- 查询时先生成 query embedding，再通过 `app.repositories.documents` 访问 PostgreSQL `documents` 表；
- 返回给 Agent 的内容格式和 LangChain `Document` artifacts 保持兼容；
- 测试仍使用 SQLAlchemy SQLite in-memory 和 monkeypatch，不依赖 Docker 或真实 PostgreSQL。

V2.2 新增只读 PostgreSQL smoke check：

```bash
conda run -n pythonLearn python scripts/smoke_postgres.py
```

该脚本只读取 `DATABASE_URL` 指向的数据库，不清空、不写入数据。检查内容包括：

- 当前数据库和用户；
- Alembic version 是否为 `0002_documents_pgvector`；
- V2 结构化表和 `documents` 表是否存在；
- customers、products、orders、order_items 是否已有 seed 数据；
- documents 是否已有 product / policy chunks；
- Repository 商品搜索和 pgvector documents 搜索是否能返回结果。

如果本机 5432 已经有 PostgreSQL，不要直接启动默认 `docker-compose.yml`，因为它也会绑定 `5432:5432`。建议在现有 PostgreSQL 中新建独立数据库，例如：

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/retailpilot_v2_smoke?connect_timeout=5
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/retailpilot_v2_smoke_test?connect_timeout=5
```

然后只对该独立库执行 migration、seed、documents index 和 smoke check：

```bash
conda run -n pythonLearn alembic upgrade head
conda run -n pythonLearn python scripts/seed_postgres.py --clear
conda run -n pythonLearn python scripts/index_documents_pgvector.py --clear
conda run -n pythonLearn python scripts/smoke_postgres.py
```

如需额外验证 LangChain Tool 层，可运行：

```bash
conda run -n pythonLearn python scripts/smoke_postgres.py --include-tools
```

`--include-tools` 会加载 embedding model，耗时更长。普通测试仍不依赖真实 PostgreSQL；真实库 integration 测试默认跳过，仅在显式设置环境变量后运行：

```bash
RUN_POSTGRES_INTEGRATION=1 conda run -n pythonLearn python -m pytest tests/integration
```

如果希望按标准顺序初始化并验证本地 V2 PostgreSQL，可以使用 bootstrap 脚本。默认只打印计划，不执行任何操作：

```bash
conda run -n pythonLearn python scripts/bootstrap_postgres.py
```

执行 Alembic、seed、documents index 和 smoke。因为该命令会清空并重导 V2 seed/documents 数据，必须显式添加 `--confirm-clear`：

```bash
conda run -n pythonLearn python scripts/bootstrap_postgres.py --execute --confirm-clear
```

如果 documents 已经索引过，只想快速重建结构化 seed 并验证：

```bash
conda run -n pythonLearn python scripts/bootstrap_postgres.py --execute --confirm-clear --skip-documents
```

可选参数：

- `--confirm-clear`：确认允许执行会清空或写入 V2 数据的步骤；
- `--skip-seed`：跳过结构化 seed 数据重导入；
- `--skip-documents`：跳过 pgvector documents 重新索引；
- `--skip-smoke`：跳过 smoke check；
- `--include-tool-smoke`：在 smoke 中额外调用 LangChain Tools，会加载 embedding model；
- `--run-integration`：执行 `RUN_POSTGRES_INTEGRATION=1 pytest tests/integration`。

Integration 测试包含两类：

- `tests/integration/test_postgres_smoke.py`：只读检查 schema、seed 数据、documents 和 Repository 查询；
- `tests/integration/test_postgres_write_paths.py`：验证 PostgreSQL 上的 preference 写入/清理、cart pending action 确认、跨用户保护和重复确认保护。
- `tests/integration/test_postgres_tools.py`：验证结构化 LangChain Tools 能直接通过 `SessionLocal` 使用 PostgreSQL，包括 product search、preference tools 和 cart confirmation tools。
- `tests/integration/test_postgres_api.py`：验证 FastAPI `/api/health/postgres` 和 `/api/chat/confirm` 能端到端使用 PostgreSQL。

写路径测试会生成唯一 `integration-smoke-*` user_id，并在测试前后清理该用户的 `user_preferences`、`cart_items` 和 `pending_actions`。
未设置 `RUN_POSTGRES_INTEGRATION=1` 时，integration 模块会在加载重依赖前快速跳过；`tests/integration/test_integration_guard.py` 确保默认运行 `pytest tests/integration` 也能稳定返回成功。

V2.2 也新增了 PostgreSQL health endpoint：

- `GET /api/health`：保持原有轻量健康检查，只返回 `{"status": "ok"}`；
- `GET /api/health/postgres`：只读检查 `DATABASE_URL` 指向的 PostgreSQL，返回当前 database、user 和 Alembic version；
- 如果 PostgreSQL 不可用，`/api/health/postgres` 返回 HTTP 503，不影响原有 `/api/health`。

提交或交接 V2 基础设施升级前，请参考：

- `docs/v2_infra_upgrade_handoff.md`

### Embedding Configuration（可选）

默认情况下，vectorstore 使用 **HuggingFace embeddings**，本地模型无需 API key。如果当前环境无法下载 HuggingFace 模型，也可以改用 **OpenAI embeddings**：

```bash
# Add to your .env file:
EMBEDDING_PROVIDER=openai

# Rebuild the vectorstore with OpenAI embeddings
uv run python data/data_generation/build_vectorstore.py
```

## Workshop 大纲

原 workshop 包含三个 module，从手动 tool calling 逐步推进到生产部署：

1. **Module 1: Agent Development**：从基础 Agent 到带 HITL 的 multi-agent system；
2. **Module 2: Evaluation & Improvement**：使用 eval-driven development 系统化改进 Agent；
3. **Module 3: Deployment & Continuous Improvement**：部署到生产环境并构建 data flywheel。

📚 To get started, see [workshop_modules/README.md](workshop_modules/README.md)


## 仓库结构

```
langsmith-agent-lifecycle-workshop/
├── workshop_modules/        # Interactive Jupyter notebooks
│   ├── module_1/            # Agent Development (4 sections)
│   ├── module_2/            # Evaluation & Improvement (3 sections)
│   └── module_3/            # Deployment & Continuous Improvement (2 sections)
│
├── agents/                  # Reusable agent factory functions
│   ├── db_agent.py          # Database queries (rigid tools)
│   ├── sql_agent.py         # Flexible SQL generation (improved)
│   ├── docs_agent.py        # RAG for product docs & policies
│   ├── supervisor_agent.py  # Multi-agent coordinator
│   └── supervisor_hitl_agent.py  # Full verification + routing system
│
├── tools/                   # Database & document search tools
│   ├── database.py          # 6 DB tools (orders, products, SQL)
│   └── documents.py         # 2 RAG tools (products, policies)
│
├── evaluators/              # Evaluation metrics
│   └── evaluators.py        # Correctness & tool call counters
│
├── deployments/             # Production-ready graph configurations
│   ├── db_agent_graph.py                   # Baseline database agent
│   ├── docs_agent_graph.py                 # RAG documents agent
│   ├── sql_agent_graph.py                  # Improved SQL agent
│   ├── supervisor_agent_graph.py           # Basic supervisor
│   ├── supervisor_hitl_agent_graph.py      # Supervisor with verification
│   └── supervisor_hitl_sql_agent_graph.py  # Complete system (best)
│
├── data/                    # Complete dataset & generation scripts
│   ├── structured/          # SQLite DB + JSON files
│   ├── documents/           # Markdown docs for RAG
│   ├── vector_stores/       # Pre-built vectorstore
│   └── data_generation/     # Scripts to regenerate data
│
├── config.py                # Workshop-wide configuration
├── langgraph.json           # LangGraph deployment config
└── pyproject.toml           # Dependencies
```

## 涵盖的关键概念

- **Agent Development：**Tool calling、multi-agent systems、Supervisor Pattern、HITL with interrupts；
- **Evaluation & Testing：**Offline evaluation、LLM-as-Judge、trace metrics、eval-driven development；
- **Deployment & Production：**LangSmith deployments、online evaluation、annotation queues、SDK integration；
- **Best Practices：**Factory functions、state management、dynamic prompts、structured outputs、streaming。

各 module 的详细说明见 [workshop_modules/README.md](workshop_modules/README.md)。

## 数据集概览

**TechHub dataset** 是一个高质量合成电商数据集：

- **50 customers**，覆盖 consumer、corporate、home office segments；
- **25 products**，包括 laptops、monitors、keyboards、audio、accessories；
- **250 orders**，覆盖约 2 年时间范围；
- **439 order items**，包含商品搭配购买模式；
- **SQLite database**，约 156 KB，包含完整 schema 和 indexes；
- **30 documents**，包含 25 个 product specs 和 5 个 policies，用于 RAG。

所有数据都可以直接使用。详情见 `data/data_generation/README.md`。

## 其他资源

### 文档

- **Data Generation Guide:** `data/data_generation/README.md` - 数据集生成说明
- **Database Schema:** `data/structured/SCHEMA.md` - 完整 schema 参考
- **RAG Documents:** `data/documents/DOCUMENTS_OVERVIEW.md` - 文档语料说明
- **Agent Architecture:** `agents/README.md` - Agent factory pattern 说明

### 外部链接
- [LangChain Python Docs](https://python.langchain.com)
- [LangGraph Python Docs](https://langchain-ai.github.io/langgraph)
- [LangSmith Platform](https://smith.langchain.com)
- [LangChain Academy](https://academy.langchain.com)

## 前置学习

### 必修（建议在 workshop 前完成）

来自 [LangChain Academy](https://academy.langchain.com) 的免费课程：
- [LangChain Essentials - Python](https://academy.langchain.com/courses/langchain-essentials-python) (30 min)
- [LangGraph Essentials - Python](https://academy.langchain.com/courses/langgraph-essentials-python) (1 hour)
- [LangSmith Essentials](https://academy.langchain.com/courses/quickstart-langsmith-essentials) (30 min)

### 推荐（用于更深入理解）

- [Foundation: Introduction to LangGraph](https://academy.langchain.com/courses/intro-to-langgraph) (6 hours)
- [Foundation: Introduction to Agent Observability & Evaluations](https://academy.langchain.com/courses/intro-to-langsmith) (3.5 hours)

### 技术要求

- **Python 3.10+**
- **API Keys:**
  - LangSmith (free tier: [smith.langchain.com](https://smith.langchain.com))
  - Anthropic or OpenAI (workshop uses Claude Haiku 4.5 by default)
- **Tools:** Git, Jupyter, uv (or pip)

## License

本项目使用 Apache License 2.0，详情见 [LICENSE](LICENSE)。

这是教学 workshop 材料，合成数据集可自由使用和分发。

---

**准备开始？**打开 `workshop_modules/module_1/section_1_foundation.ipynb` 开始学习。🚀
