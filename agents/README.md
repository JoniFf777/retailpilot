# Agents

本目录包含 TechHub / ShopMind 项目中可复用的 Agent factory functions。原 workshop Agent 主要用于演示 LangChain、LangGraph 和 LangSmith 的 Agent 开发生命周期；ShopMind V1 在此基础上新增了一个面向购物决策的单 Agent。

## 可用 Agent

| Agent | 说明 | 使用位置 |
|-------|-------------|---------|
| **Database Agent** (`db_agent.py`) | 使用固定数据库 Tool 查询订单状态、商品信息等结构化数据 | Module 1 |
| **SQL Agent** (`sql_agent.py`) | 使用 SQL 生成能力处理更灵活的聚合和复杂查询，是 DB Agent 的改进版 | Module 2 |
| **Documents Agent** (`docs_agent.py`) | 使用 RAG / vector search 检索商品文档和政策文档 | Module 1 |
| **Supervisor Agent** (`supervisor_agent.py`) | 协调 DB Agent 和 Docs Agent 处理复杂问题 | Module 1 |
| **Supervisor HITL Agent** (`supervisor_hitl_agent.py`) | 带客户验证和 human-in-the-loop 流程的完整 workshop Agent | Module 1 |
| **ShopMind Agent** (`shopmind_agent.py`) | 面向中文用户的购物决策单 Agent，接入商品、文档、偏好和加购确认工具 | ShopMind V1 |

## 快速开始

所有 Agent 都遵循 factory function 模式：

```python
from agents import create_db_agent, create_docs_agent, create_supervisor_agent

# Create agents with sensible defaults
db_agent = create_db_agent()
docs_agent = create_docs_agent()
supervisor = create_supervisor_agent(db_agent, docs_agent)

# Use like any LangGraph graph
result = supervisor.invoke({"messages": [{"role": "user", "content": "..."}]})
```

ShopMind V1 可以直接调用：

```python
from agents.shopmind_agent import invoke_shopmind_agent

result = invoke_shopmind_agent(
    message="推荐一个适合办公的键盘",
    user_id="demo-user",
)
```

## 配置方式

所有 Agent 默认读取根目录 `config.py` 中的配置，并可通过 `.env` 覆盖：

```python
# .env file
WORKSHOP_MODEL="anthropic:claude-haiku-4-5"

# Automatically used by all agents
db_agent = create_db_agent()  # Uses model from config
```

## 高级用法

### 自定义 State Schema

可以传入自定义 state schema，在 graph 之间共享状态：

```python
from langgraph.graph import MessagesState

class CustomState(MessagesState):
    customer_id: str

agent = create_db_agent(state_schema=CustomState)
```

### 扩展 Tools

可以在创建 Agent 时追加额外 Tool：

```python
from tools import get_customer_orders

agent = create_db_agent(additional_tools=[get_customer_orders])
```

### 覆盖默认模型或 Prompt

可以按需覆盖默认模型或 prompt：

```python
agent = create_db_agent(
    model="anthropic:claude-sonnet-4",
    system_prompt="Custom instructions..."
)
```

### 部署模式

生产部署时通常关闭本地 checkpointer，由 LangGraph Cloud / LangSmith 管理持久化状态：

```python
agent = create_db_agent(use_checkpointer=False)
```

部署入口可参考 `deployments/` 目录。

## 实现模式

每个 Agent 文件通常包含：

1. **模块级常量**：system prompt 和基础 tools；
2. **Factory function**：如 `create_*_agent()`；
3. **编译后的 graph**：可直接 `.invoke()` 或 `.stream()`。

这种模式默认简单，同时保留模型、prompt、tools 和 state schema 的扩展能力。具体实现可查看各 Agent 文件。
