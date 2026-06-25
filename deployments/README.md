# Deployments

本目录包含可部署到 LangSmith / LangGraph 平台的 graph 配置。每个文件都会导出一个 `graph` 实例，并由根目录 `langgraph.json` 引用。

## 可用部署

| Deployment | Agent | 说明 | Module |
|------------|-------|-------------|--------|
| `db_agent_graph.py` | Database Agent | 使用固定数据库 Tool 的 baseline Agent | 1 |
| `sql_agent_graph.py` | SQL Agent | 支持更灵活 SQL 查询的改进版 Agent | 2 |
| `docs_agent_graph.py` | Documents Agent | 基于 RAG 搜索商品文档和政策文档 | 1 |
| `supervisor_agent_graph.py` | Supervisor | 协调 DB + Docs Agent | 1 |
| `supervisor_hitl_agent_graph.py` | Supervisor HITL | 带客户验证流程的完整系统 | 1 |
| `supervisor_hitl_sql_agent_graph.py` | Supervisor HITL + SQL | 使用 SQL Agent 的改进版完整系统 | 2 |

## 文件结构模式

每个 deployment 文件都遵循类似结构：

```python
# deployments/db_agent_graph.py
from agents import create_db_agent

# Module-level graph instance for LangSmith deployment
graph = create_db_agent(use_checkpointer=False)
```

关键点：

- `use_checkpointer=False`：部署环境由 LangSmith / LangGraph 管理持久化状态，因此不启用本地 checkpointer。
- `graph` 必须是模块级变量，方便 `langgraph.json` 引用。

## LangSmith 部署入口

这些 graph 在 `langgraph.json` 中注册：

```json
{
  "graphs": {
    "db_agent": "./deployments/db_agent_graph.py:graph",
    "supervisor_hitl_sql": "./deployments/supervisor_hitl_sql_agent_graph.py:graph"
  }
}
```

ShopMind V1 当前主要通过 FastAPI 本地后端暴露 API，尚未新增独立 LangGraph deployment。
