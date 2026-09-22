# ShopMind 本地开发与运行指南

> 更新时间：2026-09-17
>
>
> 本文只保存可移植命令，不包含开发者本机解释器路径、密钥或未脱敏连接串。机器状态放在被 Git 忽略的 `.local/`。

## 1. 环境要求

- Python 3.11+ 和项目依赖；
- Node.js 与 npm；
- Docker；
- PostgreSQL 16 + pgvector；
- Windows PowerShell，用于仓库中的启动脚本。

激活 Python 环境，使 `python` 指向项目解释器；也可以设置 `SHOPMIND_PYTHON`。脚本会在 Python、Node/npm 或 PostgreSQL 不可用时给出明确失败。

本仓库机器上的 Agent 应遵循 `AGENTS.md`，使用既有 Conda 环境；本文保持跨机器写法。

## 2. 环境变量和安全边界

需要本地覆盖时，将 `.env.example` 复制为被忽略的 `.env`。不要把真实密钥写进受跟踪文件。

- `DATABASE_URL`：应用运行数据库；
- `TEST_DATABASE_URL`：隔离 PostgreSQL 集成测试；
- `POSTGRES_ADMIN_URL`：只在空库缺少 `vector` 扩展时，用于同一数据库的前置安装；
- `LANGSMITH_TRACING=false`：普通开发、测试和 Core Demo 的默认选择。

示例：

```powershell
$env:LANGSMITH_TRACING = "false"
docker compose up -d postgres
# DATABASE_URL 必须指向隔离的 *_demo、*_test 或 *_smoke 数据库。
# 空库缺少 vector 时，再设置同库的 POSTGRES_ADMIN_URL。
python scripts/prepare_shopmind_demo.py --json
```

`POSTGRES_ADMIN_URL` 不会进入应用 Runtime。目标不一致、扩展缺失且没有合法管理员连接时，准备脚本会 fail closed。

完整 bootstrap 可能包含破坏性旧种子操作，只能在确认目标是隔离数据库后执行：

```powershell
python scripts/bootstrap_postgres.py --execute --confirm-clear --skip-documents
```

普通开发优先使用只读 smoke 或幂等 Demo Prepare，不要每次清库和重建索引。

## 3. 数据库版本

当前 Alembic head：

```text
0020_task_worker_heartbeat
```

- `0016_shopping_evidence_pipeline`：购物证据版本、入库任务/节点和活动发布指针；
- `0017_ai_extension_registry`：Prompt、Skill、MCP 定义与活动发布指针。
- `0018_shopping_task_workbench`：持久任务、worker lease、产物、事件和动作。
- `0019_document_evidence_version`：Document 与 versioned evidence 的受控关联。
- `0020_task_worker_heartbeat`：任务 Worker 的持久心跳与 live readiness 依据。

Readiness 会检查数据库是否达到当前 head。

## 4. 后端

```powershell
./scripts/start_shopmind.ps1 -Profile development -Action api -Reload
./scripts/start_shopmind.ps1 -Profile development -Action tests
python scripts/smoke_postgres.py
```

API 默认地址：`http://127.0.0.1:8000`。

常用接口：

- OpenAPI：`/docs`；
- Liveness：`/api/health`；
- Production preflight：`/api/health/preflight`；
- Live readiness：`/api/health/readiness`；
- Service metrics：`/api/health/service-metrics`；
- Outbox snapshot：`/api/health/outbox`；
- 默认关闭的 AI Operations：`/api/admin/ai/*`。

## 5. 前端

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
npm --prefix frontend run test
npm --prefix frontend run e2e
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run typecheck:e2e
npm --prefix frontend run build
npm --prefix frontend run check:budget
```

Vite 默认运行在 `127.0.0.1:5173`，并把 `/api` 代理到 FastAPI。`POST /api/chat/stream` 使用 `fetch + ReadableStream`，不是浏览器 `EventSource`。

## 6. Core Demo

```powershell
./scripts/start_shopmind_demo.ps1 -Prepare
./scripts/start_shopmind_demo.ps1 -Start
./scripts/start_shopmind_demo.ps1 -Verify
npm --prefix frontend run test:e2e:live
```

Core Demo 使用确定性路由、development identity、`LANGSMITH_TRACING=false` 和 `SHOPMIND_OUTBOX_ENABLED=false`。它不需要 LangSmith Key、RocketMQ SDK/Broker、真实支付 Provider、远程 MCP 或联网搜索。

完整说明见 `docs/demo_runbook.md`。

## 7. 购物证据

审计当前 104 份商品资料和 5 份政策：

```powershell
python scripts/audit_shopping_evidence.py
```

先进行无写入检查：

```powershell
python scripts/ingest_shopping_evidence.py --dry-run
```

`ingest_shopping_evidence.py` 只接收受信商品说明、兼容性资料、选购指南和商城政策，不把聊天附件或任意 URL 写入证据库。

入库使用 PostgreSQL 租约、节点 CAS、内容指纹和活动版本指针。RocketMQ 不参与证据任务调度。

当前默认 RAG 兼容路径只复用 `retrieval_pipeline.py` 的公共 RRF；完整 Channel/PostProcessor 仍用于独立测试和可选/Shadow 接入。

## 8. PostgreSQL 集成验收

集成测试使用随机私有 Schema 和独立 Alembic version table，不应修改共享 `public`：

```powershell
$env:RUN_POSTGRES_INTEGRATION = "1"
python -m pytest tests/integration/test_phase3a_postgres_cart.py -p no:cacheprovider
python -m pytest tests/integration/test_phase4_postgres_orders.py -p no:cacheprovider
python -m pytest tests/integration/test_phase5_postgres_payments.py -p no:cacheprovider
python -m pytest tests/integration/test_phase6_postgres_outbox.py -p no:cacheprovider
python -m pytest tests/integration/test_shopping_evidence_postgres.py -p no:cacheprovider
```

不要在共享或生产数据库上运行带清理/迁移副作用的验收。

## 9. AI 平台聚焦验证

```powershell
python evaluation/run_ai_runtime_resilience_eval.py --output-json artifacts/ai-runtime-resilience.json
python evaluation/run_shopping_evidence_eval.py --output-json artifacts/shopping-evidence.json
python evaluation/run_retrieval_equivalence_eval.py --output-json artifacts/retrieval-equivalence.json
python evaluation/run_ai_platform_release_eval.py --output-json artifacts/ai-platform-release.json
```

这些 runner 不调用真实模型，分别检查：

- Admission、首包前候选切换、流开始后终止、预算和取消；
- 商品范围、政策有效期、Catalog 事实权威和确定性 RRF；
- 旧/新 RRF 固定语料等价性；
- default-off、shadow、启用和回滚证据。

Model Gateway 和 Extension Registry 已有合同与门禁，但尚未全面接管默认 Agent、Prompt 和工具路径。

## 10. RocketMQ 与 Outbox（可选）

```powershell
./scripts/bootstrap_rocketmq_sdk.ps1
python scripts/run_outbox_publisher.py
python scripts/inspect_outbox.py --json
```

RocketMQ Publisher 是独立可选 worker。Core Demo 和 API 启动不依赖 Broker。当前只有 Producer/Publisher；Consumer、Inbox 和消费端去重尚未实现。

详细设计见 `docs/rocketmq_outbox_design.md`。

## 11. 常用发布检查

```powershell
python scripts/check_production_config.py
python scripts/check_deployment_readiness.py
python scripts/check_release_operations.py
python evaluation/run_catalog_eval.py --output-json artifacts/v6-evaluation-catalog/summary.json
```

最终门禁组合后端回归、Catalog migration、真实 PostgreSQL 套件、Vitest、mocked/live Playwright、lint/typecheck/build/budget、compileall、Core Demo Verify、`git diff --check` 和 clean-room snapshot。

clean-room snapshot 不应包含 `.git`、`.env`、虚拟环境、`node_modules`、构建结果、缓存或本地 artifacts。

## 12. 默认关闭能力

- LangSmith 云 Trace/Evaluation；
- RocketMQ Publisher；
- `/admin/ai` 管理面；
- 远程 MCP、图谱和联网搜索；
- 可选远程 RAG Specialist；
- 真实支付 Provider。

Chat/Confirm 的 AI Admission 不是关闭状态：它默认使用本地协调，可显式选择 Redis。

## 12. Shopping task workbench (offline)

Apply the current head migration in an isolated database, seed the task-only
fixtures explicitly, then run the worker:

```powershell
conda run -n pythonLearn python.exe scripts\seed_shopmind_catalog.py --data data\shopping_task_dock_catalog.json
conda run -n pythonLearn python.exe scripts\seed_shopping_task_fixtures.py --execute
conda run -n pythonLearn python.exe scripts\run_shopping_task_worker.py
```

Set `SHOPMIND_SHOPPING_TASKS_ENABLED=false` to close new task admission while
keeping legacy Chat/catalog/commerce paths available. These commands must
target an isolated database and do not clear data.
