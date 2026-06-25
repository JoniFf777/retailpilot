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
