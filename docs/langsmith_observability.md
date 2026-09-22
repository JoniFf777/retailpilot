# ShopMind LangSmith 可观测性

> 中文入口更新时间：2026-09-17
>
>
> LangSmith 是显式启用的调试/云实验旁路，不是普通 API、Core Demo、测试、集成验收、离线评测或 AI 平台运行的必需依赖。

使用原则：

- 普通开发和测试设置 `LANGSMITH_TRACING=false`；
- 不读取、打印、提交或复制真实 Key；
- 只有用户明确授权时才创建云 Trace 或消耗云评测额度；
- 缺失、不可用、未授权、限流或额度不足都不能中断购物主链路；
- 本地确定性评测、购物证据 Pipeline 和 RocketMQ Outbox 不依赖 LangSmith。

以下保留 profile、采样和故障语义的固定英文术语，方便与配置字段对应。

LangSmith is an optional side-channel for debugging call chains and explicitly
requested cloud experiments. It is not required for normal API execution,
tests, integration checks, lint, or offline evaluation.

## Profiles

Use the existing `SHOPMIND_DEPLOYMENT_PROFILE` variable:

| Profile | Tracing | Project | Sampling |
| --- | --- | --- | --- |
| `development` | off by default | `shopmind-development` | `1.0` |
| `demo` | on when a Key exists | `shopmind-demo` | `1.0` |
| `production` | on when a Key exists | `shopmind-production` | `0.1` |
| `public-demo` | alias of `production` | `shopmind-production` | `0.1` |
| `evaluation` | on when a Key exists | `shopmind-evaluation` | `1.0` |

The project name and sampling rate may be explicitly overridden by process
environment variables. `public-demo` is normalized to `production`, so it
uses the same readiness and preflight behavior.

Start the API through the PowerShell entrypoint:

```powershell
.\scripts\start_shopmind.ps1 -Profile development -Action api -Reload
.\scripts\start_shopmind.ps1 -Profile demo -Action api
.\scripts\start_shopmind.ps1 -Profile production -Action api
```

The script never contains or prints a Key. The application loads the local
`.env` with `override=False`, so process variables set by the script take
precedence. Missing Keys, invalid sampling, invalid configuration, or
LangSmith initialization failures force both SDK tracing switches to
`false` and do not stop the business path.

## Tests and offline evaluation

Keep tracing explicitly disabled for every ordinary validation command:

```powershell
$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest

$env:LANGSMITH_TRACING = "false"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_catalog_eval.py --output-json artifacts\v6-evaluation-catalog\summary.json
```

Tests use mocks and local policy checks only. They do not use real Keys,
contact LangSmith, or create cloud Trace.

## Explicit cloud evaluation

Only run this after the user explicitly requests a LangSmith experiment and
the deployment environment supplies the Key as a Secret:

```powershell
.\scripts\start_shopmind.ps1 -Profile evaluation -Action langsmith-eval
```

The evaluation script refuses to run unless the effective profile is
`evaluation` and tracing remains enabled after the Key and configuration
checks.

## Local `.env` warning

The repository does not read, modify, or display the local Key. Before using
ordinary commands directly, change the local `.env` setting yourself to:

```dotenv
LANGSMITH_TRACING=false
```

Until that manual change is made, bypassing the unified startup script and
running an old command directly may still enable tracing from the existing
`.env`.
