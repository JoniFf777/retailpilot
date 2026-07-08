from types import SimpleNamespace

import pytest

from scripts import bootstrap_postgres
from scripts.bootstrap_postgres import (
    BootstrapOptions,
    BootstrapRunner,
    BootstrapSafetyError,
    build_steps,
    run_bootstrap,
)


class FakeRunner(BootstrapRunner):
    def __init__(self):
        self.calls = []

    def alembic_upgrade(self) -> None:
        self.calls.append("alembic")

    def seed_postgres(self) -> None:
        self.calls.append("seed")

    def index_documents(self) -> None:
        self.calls.append("documents")

    def smoke_check(self, *, include_tools: bool = False) -> None:
        self.calls.append(f"smoke:{include_tools}")

    def integration_tests(self) -> None:
        self.calls.append("integration")


def test_build_steps_includes_safe_default_sequence():
    runner = FakeRunner()

    steps = build_steps(BootstrapOptions(), runner)

    assert [step.name for step in steps] == [
        "alembic",
        "seed",
        "documents",
        "smoke",
    ]
    assert [step.destructive for step in steps] == [False, True, True, False]


def test_build_steps_honors_skip_and_integration_options():
    runner = FakeRunner()

    steps = build_steps(
        BootstrapOptions(skip_documents=True, skip_smoke=True, run_integration=True),
        runner,
    )

    assert [step.name for step in steps] == ["alembic", "seed", "integration"]


def test_build_steps_can_skip_seed_for_migration_only_plan():
    runner = FakeRunner()

    steps = build_steps(
        BootstrapOptions(skip_seed=True, skip_documents=True, skip_smoke=True),
        runner,
    )

    assert [step.name for step in steps] == ["alembic"]
    assert all(not step.destructive for step in steps)


def test_run_bootstrap_without_execute_only_prints_plan(monkeypatch, capsys):
    runner = FakeRunner()
    monkeypatch.setattr(
        bootstrap_postgres,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+psycopg://user:secret@127.0.0.1:5432/app"
        ),
    )

    steps = run_bootstrap(BootstrapOptions(execute=False), runner)

    output = capsys.readouterr().out
    assert len(steps) == 4
    assert runner.calls == []
    assert "user:***" in output
    assert "--execute" in output


def test_run_bootstrap_execute_requires_confirm_for_destructive_steps(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(
        bootstrap_postgres,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://user:secret@db/app"),
    )

    with pytest.raises(BootstrapSafetyError, match="--confirm-clear"):
        run_bootstrap(BootstrapOptions(execute=True), runner)

    assert runner.calls == []


def test_run_bootstrap_execute_allows_non_destructive_plan_without_confirm(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(
        bootstrap_postgres,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://user:secret@db/app"),
    )

    run_bootstrap(
        BootstrapOptions(
            execute=True,
            skip_seed=True,
            skip_documents=True,
            skip_smoke=True,
        ),
        runner,
    )

    assert runner.calls == ["alembic"]


def test_run_bootstrap_execute_runs_steps_in_order(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(
        bootstrap_postgres,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://user:secret@db/app"),
    )

    run_bootstrap(
        BootstrapOptions(
            execute=True,
            confirm_clear=True,
            include_tool_smoke=True,
            run_integration=True,
        ),
        runner,
    )

    assert runner.calls == [
        "alembic",
        "seed",
        "documents",
        "smoke:True",
        "integration",
    ]
