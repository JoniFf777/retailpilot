"""Bootstrap and verify the local ShopMind V2 PostgreSQL database."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

from app.core.settings import get_settings
from scripts.smoke_postgres import _mask_database_url


StepAction = Callable[[], None]


@dataclass(frozen=True)
class BootstrapOptions:
    execute: bool = False
    confirm_clear: bool = False
    skip_seed: bool = False
    skip_documents: bool = False
    skip_smoke: bool = False
    include_tool_smoke: bool = False
    run_integration: bool = False


@dataclass(frozen=True)
class BootstrapStep:
    name: str
    description: str
    destructive: bool
    action: StepAction


class BootstrapSafetyError(RuntimeError):
    """Raised when a destructive bootstrap plan lacks explicit confirmation."""


class BootstrapRunner:
    def alembic_upgrade(self) -> None:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")

    def seed_postgres(self) -> None:
        from scripts.seed_postgres import run_seed

        run_seed(clear=True)

    def index_documents(self) -> None:
        from scripts.index_documents_pgvector import run_index

        run_index(clear=True)

    def smoke_check(self, *, include_tools: bool = False) -> None:
        from scripts.smoke_postgres import run_smoke

        run_smoke(include_tools=include_tools)

    def integration_tests(self) -> None:
        env = dict(os.environ)
        env["RUN_POSTGRES_INTEGRATION"] = "1"
        subprocess.run(
            [sys.executable, "-m", "pytest", "tests/integration"],
            check=True,
            env=env,
        )


def build_steps(
    options: BootstrapOptions,
    runner: BootstrapRunner,
) -> list[BootstrapStep]:
    steps = [
        BootstrapStep(
            name="alembic",
            description="运行 Alembic upgrade head，创建或升级 PostgreSQL schema",
            destructive=False,
            action=runner.alembic_upgrade,
        ),
    ]

    if not options.skip_seed:
        steps.append(
            BootstrapStep(
                name="seed",
                description="清空并重新导入 customers/products/orders/order_items",
                destructive=True,
                action=runner.seed_postgres,
            )
        )

    if not options.skip_documents:
        steps.append(
            BootstrapStep(
                name="documents",
                description="清空并重新索引 markdown documents 到 pgvector",
                destructive=True,
                action=runner.index_documents,
            )
        )

    if not options.skip_smoke:
        steps.append(
            BootstrapStep(
                name="smoke",
                description="运行只读 PostgreSQL smoke check",
                destructive=False,
                action=lambda: runner.smoke_check(
                    include_tools=options.include_tool_smoke
                ),
            )
        )

    if options.run_integration:
        steps.append(
            BootstrapStep(
                name="integration",
                description="运行 RUN_POSTGRES_INTEGRATION=1 pytest tests/integration",
                destructive=True,
                action=runner.integration_tests,
            )
        )

    return steps


def print_plan(database_url: str, steps: list[BootstrapStep]) -> None:
    print(f"目标数据库：{_mask_database_url(database_url)}")
    print("执行计划：")
    for index, step in enumerate(steps, 1):
        destructive_label = "（会清空/写入 V2 数据）" if step.destructive else "（只读/迁移）"
        print(f"{index}. {step.name}: {step.description} {destructive_label}")


def _has_destructive_steps(steps: list[BootstrapStep]) -> bool:
    return any(step.destructive for step in steps)


def run_bootstrap(
    options: BootstrapOptions,
    runner: BootstrapRunner | None = None,
) -> list[BootstrapStep]:
    settings = get_settings()
    runner = runner or BootstrapRunner()
    steps = build_steps(options, runner)
    print_plan(settings.database_url, steps)

    if not options.execute:
        print("未执行：请添加 --execute 后真正运行。")
        return steps

    if _has_destructive_steps(steps) and not options.confirm_clear:
        raise BootstrapSafetyError(
            "执行计划包含会清空或写入 V2 数据的步骤。"
            "请确认 DATABASE_URL 指向独立开发库后，添加 --confirm-clear 再执行。"
        )

    for step in steps:
        print(f"开始：{step.name}")
        step.action()
        print(f"完成：{step.name}")

    print("PostgreSQL bootstrap 完成")
    return steps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap and verify the ShopMind V2 PostgreSQL database."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="真正执行计划。未提供时只打印计划，不连接或写入数据库。",
    )
    parser.add_argument(
        "--confirm-clear",
        action="store_true",
        help="确认允许执行会清空或写入 V2 数据的步骤，例如 seed、documents index 和 integration tests。",
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="跳过结构化 seed 数据重导入。",
    )
    parser.add_argument(
        "--skip-documents",
        action="store_true",
        help="跳过 pgvector documents 重新索引。",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="跳过 smoke check。",
    )
    parser.add_argument(
        "--include-tool-smoke",
        action="store_true",
        help="smoke check 中额外调用 LangChain Tools，会加载 embedding model。",
    )
    parser.add_argument(
        "--run-integration",
        action="store_true",
        help="bootstrap 后运行真实 PostgreSQL integration tests。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    options = BootstrapOptions(
        execute=args.execute,
        confirm_clear=args.confirm_clear,
        skip_seed=args.skip_seed,
        skip_documents=args.skip_documents,
        skip_smoke=args.skip_smoke,
        include_tool_smoke=args.include_tool_smoke,
        run_integration=args.run_integration,
    )
    try:
        run_bootstrap(options)
    except BootstrapSafetyError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
