# ShopMind Core Demo 操作手册

> 更新时间：2026-09-17
>
>
> 状态：Phase 1-6B-2 accepted/closed；Project Closure implementation in progress；Inbox/Consumer deferred。

本文提供可复制的本地 Web Demo 路径。Core Demo 需要 PostgreSQL、FastAPI Backend、React Frontend 和 ShopMind Catalog；不需要 RocketMQ、LangSmith、外部 Trace、真实支付 Provider、远程 MCP 或联网搜索。

## 1. Demo 展示什么

```text
中文购物需求
  → 结构化约束与 SKU 推荐
  → 证据与引用
  → 选择明确 SKU
  → PendingAction 确认
  → Cart
  → Checkout Preview
  → Order + Inventory Reservation
  → Mock Payment
  → paid Order + Outbox facts
```

建议面试演示控制在 5 分钟内。AI Operations、RocketMQ Publisher 和生产参考检查属于补充内容，不要阻塞核心链路。

## 2. 环境准备

激活 Python 环境，使 `python` 可用，或设置 `SHOPMIND_PYTHON`：

```powershell
python --version
```

需要本地覆盖时，从 `.env.example` 创建被忽略的 `.env`。`DATABASE_URL` 必须指向 loopback 上名称包含 `_demo`、`_test` 或 `_smoke` 的隔离 PostgreSQL 数据库，例如 `retailpilot_v2_smoke`。

准备脚本会拒绝：

- 非 loopback 主机；
- 看起来像生产环境的数据库名；
- 缺少 pgvector 且没有合法 `POSTGRES_ADMIN_URL` 的空库；
- 与 `DATABASE_URL` 不同目标的管理员连接。

安装前端依赖：

```powershell
npm --prefix frontend ci
```

## 3. Prepare

```powershell
./scripts/start_shopmind_demo.ps1 -Prepare
```

Prepare 会：

1. 检查 PostgreSQL 和前端依赖；
2. 通过同库管理员连接确保 pgvector 前置条件；
3. 将 Alembic 升级到 `0020_task_worker_heartbeat`；
4. 运行旧结构化种子和 ShopMind Catalog/SKU 种子；
5. 只补充缺失记录，保持幂等。

Prepare 不会执行 `--clear`、删除表或自动重建完整文档向量索引。数据库目标不安全时，会在任何写入前 fail closed。

## 4. Start

```powershell
./scripts/start_shopmind_demo.ps1 -Start
```

默认地址：

- Backend：`http://127.0.0.1:8000`；
- Frontend：`http://127.0.0.1:5173`；
- Health：`http://127.0.0.1:8000/api/health`；
- Readiness：`http://127.0.0.1:8000/api/health/readiness`。

启动配置：

- profile 为 `offline-demo`；
- 使用确定性路由和 development identity；
- `LANGSMITH_TRACING=false`；
- `SHOPMIND_OUTBOX_ENABLED=false`；
- AI 管理面和远程扩展保持关闭；
- Chat/Confirm Admission 使用本地协调基线。

不会启动 RocketMQ Publisher。日志写入被忽略的 `.local/shopmind-demo/`。

当 Backend 或 Frontend 端口被占用时，`-Start` 会 fail closed，不会静默复用未知进程。停止旧进程，或显式传入其他 `-BackendPort`/`-FrontendPort`。

开发者确认现有进程可信时，可以使用：

```powershell
./scripts/start_shopmind_demo.ps1 -Start -ReuseExisting
```

该选项仍会检查 Backend readiness 和 Frontend shell。Clean-room 验证不得使用 `-ReuseExisting`。

## 5. Verify

```powershell
./scripts/start_shopmind_demo.ps1 -Verify
```

`smoke_shopmind_demo.py` 检查：

- Health/Readiness；
- OpenAPI 核心合同；
- Frontend Vite shell；
- 当前 migration；
- active Catalog/SKU；
- Recommendation → SKU → PendingAction → Cart → Checkout → Order → Mock Payment。

验证不仅检查 HTTP 状态，还检查 paid Order、succeeded PaymentAttempt、consumed Reservation、库存差值和 exactly-one versioned Order/Payment Outbox facts。非零退出码代表 Demo 失败。

## 6. 浏览器 Happy Path

打开 `http://127.0.0.1:5173`：

1. 输入 development user id；
2. 输入笔记本需求；
3. 查看结构化条件、推荐卡片、评分和证据状态；
4. 选择明确 SKU；
5. 确认 PendingAction；
6. 打开 Cart；
7. 生成 Checkout Preview；
8. 创建 Order；
9. 点击 Mock Payment；
10. 查看订单、PaymentAttempt 和状态变化。

真实浏览器门禁：

```powershell
npm --prefix frontend run test:e2e:live
```

Live 配置不包含 `page.route`、`route.fulfill` 或浏览器 API mock。普通命令：

```powershell
npm --prefix frontend run e2e
```

普通 E2E 使用 mocked API，不要求 Backend/PostgreSQL 运行。

## 7. 演示时如何解释证据能力

当前核心 Demo 可以展示推荐引用和证据状态，但不要求现场重新导入语料。

购物证据能力的正确表述：

- 受信商品说明、兼容资料、选购指南和商城政策可以进入版本化 Pipeline；
- Pipeline 使用 PostgreSQL 租约/CAS，不依赖 RocketMQ；
- 文档不能覆盖 Catalog 的价格、库存和 SKU 真值；
- 完整 `SearchChannel + PostProcessor` 已有实现和门禁，但默认 RAG 兼容路径当前只复用公共 RRF；
- 图谱、联网搜索和远程 MCP 没有进入 Core Demo。

如果要单独检查语料：

```powershell
python scripts/audit_shopping_evidence.py
python scripts/ingest_shopping_evidence.py --dry-run
```

## 8. Advanced Reliability Demo（可选）

即使 RocketMQ 关闭，交易事务仍会在 PostgreSQL 创建 Outbox 行。

可选高级演示步骤：

1. 运行 `scripts/bootstrap_rocketmq_sdk.ps1` 安装固定版本 SDK；
2. 启动一次性 RocketMQ NameServer/Broker/Proxy；
3. 配置 Publisher 环境变量；
4. 运行 `scripts/run_outbox_publisher.py`；
5. 使用 `scripts/inspect_outbox.py` 检查，必要时显式 redrive。

只读检查：

```powershell
python scripts/inspect_outbox.py --json
```

输出只包含计数、有界失败/dead-letter 事实和安全时间戳，不打印 payload、身份、Provider Key 或 request hash。

`GET /api/health/outbox` 也提供可选状态。Publisher disabled、积压或 dead-letter 不会让核心 Backend/PostgreSQL readiness 失败；Readiness 不执行 RocketMQ 网络探测。

## 9. AI Operations（可选）

`/admin/ai` 默认关闭。只有同时启用 AI platform、AI operations 并配置管理员授权后，才可查看模型健康、购物证据和任务摘要。

当前页面以只读健康摘要为主，后端 API 还支持证据列表/覆盖率、带 expected-version 的扩展发布/证据撤销和 payload-free Trace 投影。

现场面试不建议启用该页面，除非专门讲平台工程；它不是消费者功能，也不是通用知识库后台。

## 10. 常见失败

| 现象 | 检查 |
| --- | --- |
| PostgreSQL 不可达 | 确认 5432 端口、容器和 `DATABASE_URL` |
| migration 不匹配 | 执行 Prepare，确认 head 为 `0020_task_worker_heartbeat` |
| 端口占用 | 停止旧进程或显式更换端口，不直接复用未知服务 |
| 前端没有 Demo 身份 UI | 重新 Start，让脚本重建带 `VITE_SHOPMIND_DEMO_IDENTITY=true` 的 preview |
| 推荐无结果 | 检查 Catalog/SKU seed、品类条件和库存 |
| 支付不可用 | 确认订单是 `pending_payment` 且 Reservation active |
| Outbox 未发布 | Core Demo 默认就是 disabled；数据库 Outbox 行仍应存在 |

## 11. Clean-room 验证

Release gate 会在仓库外创建临时快照，排除：

- `.git`、`.env`；
- 虚拟环境、`node_modules`、`dist`；
- 缓存、测试结果和本地 artifacts；
- 原仓库的绝对路径与机器配置。

然后只通过环境变量注入隔离 `DATABASE_URL`，执行本文的 Environment、Prepare、Start、Verify 和 live E2E。

这证明源代码快照不依赖仓库内秘密或缓存，但不等于已经完成真正的 fresh clone、正式发布或生产部署。

## Task workbench five-minute addendum

1. Run the normal Core Demo Prepare and verify the database head, then apply
   migration `0018_shopping_task_workbench` in an isolated database.
2. Seed `shopping_task_dock_catalog.json` and `seed_shopping_task_fixtures.py --execute`.
3. Start `scripts/run_shopping_task_worker.py`, open `/tasks`, and create an
   offline bundle, diagnosis, or after-sales task.
4. Refresh `/tasks/:taskId` to observe persisted steps and artifacts; only an
   explicit action confirmation may touch the cart or save a local draft.

This demonstrates the offline engineering path, not a real-model trajectory or
production deployment.
