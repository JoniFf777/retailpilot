# TechHub Agent Simulation System

本目录提供自动化模拟系统，用于针对已部署的 `supervisor_hitl_sql_agent` 生成接近真实客服场景的 trace，方便 demo、测试和 LangSmith Insights 分析。

## 概览

该系统会与已部署的 TechHub Agent 进行多轮对话，核心能力包括：
- **Dynamic scenario generation** — queries the real TechHub SQLite DB to pick customers and their order history, then uses an LLM to generate grounded opening queries
- **12 scenario archetypes** covering all LangSmith Insights topic clusters (order status, complaints, returns, product research, policies, corporate inquiries, and more)
- **Automatic HITL interrupt handling** (email verification)
- **LLM-generated follow-up questions** matching persona characteristics
- **LangSmith trace tagging** with `archetype_id`, `generation_mode`, `segment`, and `sentiment` for rich Insights filtering
- **GitHub Actions automation** — 6 scheduled runs/day on weekdays, naturally spread across business hours

## 快速开始

### 前置条件

- 已部署并可访问的 TechHub Agent；
- `.env` 中已配置环境变量：
  - `LANGSMITH_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `LANGGRAPH_DEPLOYMENT_URL`

### 基本用法

```bash
# Run 1 dynamic conversation (default)
uv run python simulations/run_simulation.py

# Run multiple dynamic conversations
uv run python simulations/run_simulation.py --count 5

# Use static scenarios from scenarios.json (original behavior)
uv run python simulations/run_simulation.py --count 3 --mode static

# Mix static + dynamic
uv run python simulations/run_simulation.py --count 4 --mode mixed

# Test a specific static scenario by ID
uv run python simulations/run_simulation.py --scenario angry_delayed_order

# Override deployment URL
uv run python simulations/run_simulation.py --url https://custom-deployment.langgraph.app
```

## Scenario Modes

### `--mode dynamic` (default)

运行时动态生成场景：

1. 从 SQLite DB 中随机选择真实 customer 及其 recent order history；
2. 根据 customer segment 加权选择 archetype；
3. 调用 LLM 生成引用真实订单的开场问题。

这种模式可以生成多样化且有数据依据的对话。

### `--mode static`

使用 `scenarios.json` 中的 10 个固定 persona。该模式保留原始行为。

### `--mode mixed`

将 static 和 dynamic 场景混合运行，并打乱顺序。

## Dynamic Archetypes

共 12 个 archetypes，覆盖 LangSmith Insights 的主要主题：

| Archetype | Verification Required | Primary Agent | Sentiment Skew |
|---|---|---|---|
| `order_status_check` | Yes | DB/SQL | Mostly neutral |
| `delayed_order_complaint` | Yes | DB/SQL | 90% negative |
| `return_exchange_request` | Yes | DB+Docs | 80% negative |
| `spending_history_review` | Yes | SQL | Mostly neutral |
| `product_research` | No | Docs | Positive/neutral |
| `policy_question` | No | Docs | Positive/neutral |
| `product_spec_deep_dive` | No | Docs | Even split |
| `corporate_bulk_inquiry` | Yes | SQL | Corporate only, mostly neutral |
| `warranty_claim` | Yes | DB+Docs | 75% negative |
| `cancelled_order_confusion` | Yes | DB | 85% negative |
| `home_office_setup` | No | Docs | Home Office weighted |
| `loyalty_inquiry` | Yes | SQL | Even split |

## Static Scenarios（`scenarios.json`）

以下 10 个 static scenarios 可通过 `--mode static` 使用：

**需要 email verification：**`power_user_analytics`, `corporate_buyer_bulk`, `order_tracker_simple`, `support_seeker_account_issue`, `multi_order_analysis`, `angry_delayed_order`, `frustrated_wrong_item`

**不需要 verification：**`product_researcher_no_auth`, `policy_question_warranty`, `product_spec_deep_dive`

## GitHub Actions Automation

The workflow in `.github/workflows/simulate_traffic.yml` runs 1 dynamic conversation 6 times per weekday at 2-hour intervals (9am–5:30pm ET), producing naturally spread traffic patterns for LangSmith dashboards.

### 必需的 GitHub Secrets

在 **Settings > Secrets and variables > Actions** 中添加：

| Secret | 说明 |
|---|---|
| `ANTHROPIC_API_KEY` | 用于 LLM 调用的 Anthropic API key |
| `LANGSMITH_API_KEY` | 用于 tracing 的 LangSmith API key |
| `LANGGRAPH_DEPLOYMENT_URL` | LangGraph deployment URL |

### 手动触发

From the **Actions** tab → **Simulate TechHub Traffic** → **Run workflow**, you can set `count` and `mode` to run on demand.

## 在 LangSmith 中查找模拟 Trace

### 按 Simulation Source 过滤

```
metadata.source = "automated_simulation"
```

### 按 Generation Mode 过滤

```
metadata.generation_mode = "dynamic"   # LLM+DB generated
metadata.generation_mode = "static"    # From scenarios.json
```

### 按 Archetype 过滤

```
metadata.archetype_id = "delayed_order_complaint"
metadata.archetype_id = "product_research"
```

### 按 Persona / Sentiment 过滤

```
metadata.persona_type = "Corporate"
metadata.sentiment = "negative"
metadata.requires_verification = true
```

## 工作原理

### 架构流程

1. **Scenario Generation** — Dynamic mode queries DB for real customer + orders, picks weighted archetype, calls LLM to generate opening query. Static mode loads from `scenarios.json`.
2. **Thread Creation** — Creates LangSmith thread with simulation metadata (`archetype_id`, `generation_mode`, `sentiment`, etc.)
3. **Initial Query** — Sends opening query via SDK client
4. **HITL Handling** (if `requires_verification`):
   - Detects `__interrupt__` from agent
   - Auto-generates email response matching persona style
   - Resumes with `Command(resume=email)`
5. **Follow-up Generation** — LLM generates 2-6 realistic follow-up questions based on persona, sentiment, and conversation history
6. **Natural Ending** — Conversation ends when persona is satisfied or max turns reached

## 配置

Edit `simulations/simulation_config.py` to customize:

```python
DEFAULT_CONVERSATIONS_PER_RUN = 1      # Per GHA run (6 runs/day = 6 conversations)
DEFAULT_SIMULATION_MODE = "dynamic"    # static | dynamic | mixed
MAX_TURNS_PER_CONVERSATION = 8         # Max turns before forced end
SCENARIO_SELECTION = "random"          # random | round_robin | all (static mode only)
```

## 项目结构

```
simulations/
├── __init__.py                    # Package marker
├── run_simulation.py              # Main orchestrator (CLI entry point)
├── dynamic_scenario_generator.py  # DB-grounded LLM scenario generation
├── scenarios.json                 # 10 static customer personas
├── simulation_config.py           # Configuration constants
├── interrupt_handler.py           # HITL interrupt detection/response
└── README.md                      # This file

.github/workflows/
└── simulate_traffic.yml           # Scheduled GitHub Actions automation
```

## 故障排查

### Deployment URL Not Found

**Symptoms**: `DEPLOYMENT_URL not set` error

**Solution**: Set `LANGGRAPH_DEPLOYMENT_URL` in `.env` (note: two G's — `LANGGRAPH`, not `LANGRAPH`)

### Interrupt Not Detected

**Symptoms**: HITL scenario doesn't pause for email collection

**Solution**:
- Verify archetype/scenario has `requires_verification: true`
- Check agent classification logic
- Set `LOG_LEVEL = "DEBUG"` in `simulation_config.py`

### Too Many or Too Few Turns

**Solution**: Adjust `MAX_TURNS_PER_CONVERSATION` in `simulation_config.py` or review persona prompts

### Traces Not Appearing in LangSmith

**Solution**: Verify `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and `LANGGRAPH_DEPLOYMENT_URL` are set correctly

### Connection Errors

**Solution**: Check deployment status in LangSmith Studio and verify URL is correct

## 成功指标

- **>95% completion rate** — Very few errors
- **3-5 average turns** — Realistic conversation length
- **100% interrupt handling** — All HITL scenarios successfully resume
- **Archetype variety** — Filter by `metadata.archetype_id` to see distribution across runs
