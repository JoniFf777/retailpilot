# Phase 0 基线报告

日期：2026-08-03。本文记录改造开始前的真实工作区，而不是发布版本的历史结论。未执行 `git add`、`git commit`、远程 workflow 或外部观测服务调用。

## 工作区

`main` 比 `origin/main` 超前 1 个提交；暂存区为空。已有修改（均为用户所有）：

- `agents/shopmind_multi_agent/product_adapter.py`
- `agents/shopmind_multi_agent/product_agent.py`
- `docs/frontend_implementation_plan.md`
- `docs/project_status.md`
- `tests/agents/test_product_agent_adapter.py`

未跟踪内容为完整的 `frontend/` 应用和
`retailpilot_autumn_recruitment_modification_brief.md`。`frontend/` 包含 React/Vite、
POST-SSE、AbortController、HITL 抽屉、隐私、运行和状态页面；它是本次重做的保留参考，
不能删除或覆盖。仓库根目录还存在不可访问的 `pytest-cache-files-*`、
`pytest-temp-*` 目录；本次未处理它们。

## 实际验证

所有 Python 命令设置 `LANGSMITH_TRACING=false`。

| 范围 | 实际命令 | 结果 |
| --- | --- | --- |
| 前端 lint | `npm run lint` | 通过 |
| 前端类型 | `npm run typecheck` | 通过 |
| 前端 E2E 类型 | `npm run typecheck:e2e` | 通过 |
| 前端构建 | `npm run build` | 通过；100 modules，gzip JS 105.39 kB |
| 前端单测/POST-SSE | `npm run test` | 8 files、18 passed；SSE parser/reducer 共 6 项 |
| Playwright | `npm run e2e` | 未执行测试：启动浏览器进程时报 `spawn EPERM` |
| 后端全量（原命令） | `pytest` | 收集被 14 个不可访问的根目录临时目录阻断 |
| 后端全量（限定 tests） | `pytest tests -p no:cacheprovider` | 660 passed、6 skipped、25 errors；错误均为系统 Temp 目录创建/扫描权限，非业务断言 |
| 后端全量（自定义 basetemp） | `pytest tests -p no:cacheprovider --basetemp artifacts/phase0-pytest-basetemp` | 同类临时目录权限错误仍发生；多数业务测试已运行，不能宣称全绿 |
| 安全边界 | chat stream/confirm、identity、owner-data、Tool Gateway、actions、cart 聚焦测试 | 96 passed |
| PostgreSQL 集成 | `RUN_POSTGRES_INTEGRATION=1 pytest tests/integration -p no:cacheprovider` | 23 passed、2 skipped |
| PostgreSQL smoke | `scripts/smoke_postgres.py` | 通过；迁移为 `0007_governance_audit` |
| 迁移 current/upgrade | `alembic current`；`alembic upgrade head` | 均通过，已在 head |

未执行 `alembic downgrade`：目标为正在使用的 smoke 数据库，降级会破坏真实 schema/数据。
迁移的 upgrade/downgrade 往返验证应在新建的隔离数据库执行。Redis 集成的两个测试按现有
条件跳过；Docker daemon 因 npipe 权限不可访问，故不能确认 Compose 容器状态，只有
127.0.0.1:5432 TCP 连通。

## 现状和风险

- `docker-compose.yml` 当前只有 PostgreSQL；Vite 开发端口是 5173，不是 3000。
- 当前公开 API 只有 chat、confirm、stream、health、owner-data；没有 cart/checkout/order/payment 路由。
- `products` 只有价格和 `in_stock` 布尔值，无法支持 SKU、规格筛选或数量库存。
- `orders`/`order_items` 是 Customer 历史数据，不能复用为 ShopMind 订单域。
- 本地 pytest 临时目录权限与 Playwright `EPERM` 是当前可重复的验证环境风险。

基线结论：现有 V3-V6 安全与运行时边界在聚焦和 PostgreSQL 集成测试中正常；下一步可开始
Phase 1 的纯加性商品中心与推荐纵向切片，但不得把本报告视为全量测试全绿。
