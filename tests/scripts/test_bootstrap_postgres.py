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

    def provision_prerequisites(self) -> None:
        self.calls.append("prerequisites")

    def seed_postgres(self) -> None:
        self.calls.append("seed")

    def seed_shopmind_catalog(self) -> None:
        self.calls.append("shopmind-catalog")

    def index_documents(self) -> None:
        self.calls.append("documents")

    def smoke_check(
        self,
        *,
        include_tools: bool = False,
        require_documents: bool = True,
    ) -> None:
        self.calls.append(f"smoke:{include_tools}:{require_documents}")

    def integration_tests(self) -> None:
        self.calls.append("integration")


def test_build_steps_includes_safe_default_sequence():
    runner = FakeRunner()

    steps = build_steps(BootstrapOptions(), runner)

    assert [step.name for step in steps] == [
        "prerequisites",
        "alembic",
        "seed",
        "shopmind-catalog",
        "documents",
        "smoke",
    ]
    assert [step.destructive for step in steps] == [False, False, True, True, True, False]


def test_build_steps_honors_skip_and_integration_options():
    runner = FakeRunner()

    steps = build_steps(
        BootstrapOptions(skip_documents=True, skip_smoke=True, run_integration=True),
        runner,
    )

    assert [step.name for step in steps] == ["prerequisites", "alembic", "seed", "shopmind-catalog", "integration"]


def test_build_steps_can_skip_seed_for_migration_only_plan():
    runner = FakeRunner()

    steps = build_steps(
        BootstrapOptions(skip_seed=True, skip_documents=True, skip_smoke=True),
        runner,
    )

    assert [step.name for step in steps] == ["prerequisites", "alembic"]
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
    assert len(steps) == 6
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

    assert runner.calls == ["prerequisites", "alembic"]


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
        "prerequisites",
        "alembic",
        "seed",
        "shopmind-catalog",
        "documents",
        "smoke:True:True",
        "integration",
    ]


def test_missing_vector_fails_before_migration(monkeypatch):
    monkeypatch.setattr(bootstrap_postgres, "_has_vector_extension", lambda _url: False)
    monkeypatch.delenv("POSTGRES_ADMIN_URL", raising=False)

    with pytest.raises(BootstrapSafetyError, match="pgvector extension prerequisite missing"):
        bootstrap_postgres.ensure_pgvector_prerequisite(
            "postgresql+psycopg://app:secret@127.0.0.1:5432/release_test"
        )


def test_admin_target_must_match_application_target(monkeypatch):
    monkeypatch.setattr(bootstrap_postgres, "_has_vector_extension", lambda _url: False)
    monkeypatch.setenv(
        "POSTGRES_ADMIN_URL",
        "postgresql+psycopg://admin:secret@127.0.0.1:5432/other_db",
    )

    with pytest.raises(BootstrapSafetyError, match="同一 PostgreSQL 数据库"):
        bootstrap_postgres.ensure_pgvector_prerequisite(
            "postgresql+psycopg://app:secret@127.0.0.1:5432/release_test"
        )
