# ShopMind

## Current V6 Release Candidate Addendum

The current branch has completed V4, V5 through Slice 36, and all V6 Slices.
For a capability-by-capability overview, see the
[complete project introduction](docs/project_introduction.md). The
additive `/api/owner-data/*` API provides bounded inventory/memory inspection,
exact-owner memory correction and hard deletion, plus explicitly confirmed
transactional deletion of ShopMind-owned personal data. Fingerprint-only audit
facts retain independent expiry; product/document catalogs and inherited
customer/order seed data are not deletion targets.

The server-selected `signed_header` adapter now provides short-lived,
one-time HMAC-authenticated ingress identity behind `IdentityBoundary`; the
V3-compatible development default is unchanged. Audit emission now exposes a
PII-free process health snapshot with configurable consecutive-failure
alert/recovery logging. The offline governance lifecycle is explicitly accepted
as the eighth closed V6 catalog suite. The six-check static production
configuration preflight, five-check live deployment readiness, bounded
per-replica service metrics/SLO contracts, and offline versioned
rollout/rollback/incident checks are implemented. A compact policy-preserving
reference client now demonstrates JSON chat, ordered SSE, generic HITL resume,
memory inspection and exact-owner payload-free run/trace inspection through
public APIs only. Immutable implementation commit `908b918` passes the complete
validation matrix from a fresh detached worktree without `.env`, with clean Git
status before and after. V4-V6 implementation is complete; publishing remains a
separate release workflow.
Alembic head is `0007_governance_audit`; the released public baseline remains
`v3.0.0`.

ShopMind 是一个以中文购物决策为场景的 Multi-Agent Engineering 参考后端。
项目基于 FastAPI、LangGraph、PostgreSQL/pgvector 和 LangSmith，重点不是构建
完整电商平台，而是展示可执行、可约束、可持久化、可流式消费和可评估的
Agent Runtime。

仓库保留原 TechHub workshop 作为历史教学材料；当前产品路径是 ShopMind。

## 当前状态

| 版本 | 状态 | 主要成果 |
| --- | --- | --- |
| V1 | 完成 | 单 Agent、工具、偏好和确认式加购 |
| V2 | 完成 | PostgreSQL/pgvector、Repository、迁移和 smoke |
| V3 | 已发布 | 多 Agent 读路径、受保护写 handoff、API/CI/LangSmith |
| V4 | 完成 | Harness、运行持久化、Memory/Context、SSE、Tool Gateway |
| V5 | 完成 | Slice 36：remote RAG、通用多 action HITL、受控编辑与持久化恢复 |
| V6 | 完成 | Slices 1-5、完整 clean committed-checkout validation 与 release-candidate 文档均完成 |

当前正式 release 仍是 **ShopMind V3.0.0**（tag `v3.0.0`）。V4-V6 已合并到
`main`，并已通过 clean committed-checkout 验证；尚未创建新的正式版本 tag
或执行部署。

V5 正式退出条件与 V6 exit criteria 已全部满足。当前验证基线：

```text
668 passed, 6 skipped
PostgreSQL integration: 23 passed
PostgreSQL + Redis integration: 25 passed
V3 API handoff smoke: 3/3
Planner policy: 10/10 cases, 70/70 checks
Plan trajectory replay: 13/13 cases, 195/195 checks
Adapter equivalence: 5/5 cases, 24/24 checks
Action lifecycle: 10/10 cases, 60/60 checks
Resilience replay: 6/6 cases, 72/72 checks
Coordination equivalence: 5/5 cases, 18/18 checks
Governance lifecycle: 5/5 cases, 42/42 checks
Release operations: 7/7 cases, 42/42 checks
V6 catalog regression: 8/8 suites, 61/61 cases, 488/488 suite checks, 48/48 baseline checks
Migration head: 0007_governance_audit
```

## 核心能力

- Supervisor、Product、RAG、Preference 和 Decision Agents。
- 确定性路由以及受 canonical plan 约束的可选 LLM planner。
- 有界并行 fan-out/fan-in、typed Agent task/result envelopes 和 Adapter Registry。
- step、tool、token、cost、deadline、duration 和 delegation budgets。
- server-owned specialist retry、attempt usage 对账和结构化生命周期事件。
- PostgreSQL conversation/run/event/memory/idempotency persistence。
- SSE 生命周期流、合作式取消、本地并发和 bounded event buffers。
- Tool Gateway capability/ownership/resource/confirmation policy。
- add-to-cart/save-preference pending actions、精确字段编辑、持久化恢复和 `/api/chat/confirm` 通用确认边界。
- 模型无关的 planner policy、graph trajectory 与 adapter equivalence CI gates。
- 版本化、离线的 deployment/rollback/incident release-operation checks。
- 有界 public-API reference client，以及不泄露内容/事件 payload 的 exact-owner run/trace inspection。

## API

- `GET /api/health`
- `GET /api/health/governance-audit`（PII-safe process metrics）
- `GET /api/health/preflight`
- `GET /api/health/readiness`
- `GET /api/health/service-metrics`
- `POST /api/chat`
- `POST /api/chat/stream`（SSE）
- `POST /api/chat/confirm`
- `POST /api/owner-data/inspect`
- `POST /api/owner-data/runs/inspect`
- `POST /api/owner-data/memory/correct`
- `POST /api/owner-data/memory/delete`
- `POST /api/owner-data/delete`

V3 JSON contract 保持向后兼容。详细请求和响应见
[API design](docs/api_design.md) 与
[V3 handoff contract](docs/v3_api_handoff_contract.md)。

## 本地环境

Windows 开发统一使用现有 Conda 环境和解释器：

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe ...
```

不要直接运行 `python`、`pytest` 或 `uv run`，不要替换环境。

启动 API：

```powershell
.\scripts\start_shopmind.ps1 -Profile development -Action api -Reload
```

运行全量测试：

```powershell
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest
```

只读 PostgreSQL smoke：

```powershell
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
```

不要在日常启动中运行 seed、document index 或
`bootstrap_postgres.py --execute --confirm-clear`；这些操作会清理数据。

## Reference Client

客户端只调用公开 API，默认连接 loopback HTTP；远程地址必须使用 HTTPS。
它不接受任意认证头或签名密钥，生产流量仍必须经过负责身份注入的可信入口。

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py chat --message "推荐一款办公键盘" --user-id demo-user --thread-id demo-thread
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py stream --message "比较两款键盘" --user-id demo-user --thread-id demo-thread
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py run --user-id demo-user --run-id RUN_ID
```

## 离线评估

```powershell
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_planner_eval.py --output-json artifacts\v5-planner-policy\summary.json
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_plan_trajectory_eval.py --output-json artifacts\v5-plan-trajectories\summary.json
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_adapter_equivalence_eval.py --output-json artifacts\v5-adapter-equivalence\summary.json
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_action_lifecycle_eval.py --output-json artifacts\v5-action-lifecycle\summary.json
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_catalog_eval.py --output-json artifacts\v6-evaluation-catalog\summary.json
```

五个 gate 都不需要模型、数据库、凭据或 LangSmith 网络访问。V6 catalog 使用
受控 runner 集合组合已有结果，并且只读取、不会自动改写 accepted baseline。
LangSmith 仅用于显式云端 trace/experiment。

## 文档

- [Agent handoff](AGENTS.md)
- [完整项目介绍与功能清单](docs/project_introduction.md)
- [前端实施方案（当前尚无 Web 前端）](docs/frontend_implementation_plan.md)
- [项目状态](docs/project_status.md)
- [完整路线图](PLAN.md)
- [当前架构](docs/architecture.md)
- [V4-V6 Runtime design](docs/agent_runtime_design.md)
- [开发与数据库指南](docs/development.md)
- [PR checklist](docs/pr_checklist.md)
- [LangSmith observability policy](docs/langsmith_observability.md)
- [V6 release-candidate notes](docs/v6_release_candidate_notes.md)

`docs/v2_*`、`docs/v3_multi_agent_handoff_summary.md` 和
`docs/v3_release_notes.md` 是历史记录，不作为当前 roadmap。

## 下一阶段

V5 退出条件已在 Slice 36 收口，V6 Slices 1-4 已完成。V6 Slice 5 已建立静态
preflight、live readiness、cleanup success evidence、版本化 PII-free service
metrics/SLO、离线 deployment/rollback/incident checks、compact reference
client 与 exact-owner run/trace inspection，隔离源码导出演练也已通过。
immutable commit `908b918` 也已从 fresh detached worktree 通过完整 clean
validation。V6 实现没有剩余 slice；下一步仅是需要单独授权的 push、PR、
版本/tag 与部署流程。
