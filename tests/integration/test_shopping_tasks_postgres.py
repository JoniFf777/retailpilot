"""Real PostgreSQL task migration and lease-fencing acceptance."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1", allow_module_level=True)

from app.core.settings import get_settings
from app.shopping_tasks.contracts import ShoppingTaskRequest, StepResult
from app.shopping_tasks.models import ShoppingTask, ShoppingTaskArtifact, ShoppingTaskAttempt, ShoppingTaskCommand, ShoppingTaskEvent, ShoppingTaskPlan, ShoppingTaskStep
from app.repositories.owner_data import delete_all_owner_data
from app.shopping_tasks.budget import BudgetExceeded
from app.shopping_tasks.repository import LeaseConflict, claim_ready_step, claim_task, create_task, save_step_result


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def test_shopping_task_migration_two_workers_and_late_result() -> None:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    schema = f"shopmind_task_test_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            connection.execute(text(f'CREATE TABLE "{schema}".alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
            connection.commit()
            command.upgrade(_alembic(connection), "0018_shopping_task_workbench")
            tables = set(inspect(connection).get_table_names(schema=schema))
            assert {"shopmind_shopping_tasks", "shopmind_shopping_task_steps", "shopmind_shopping_task_attempts", "shopmind_shopping_task_artifacts", "shopmind_shopping_task_events", "shopmind_shopping_task_commands", "shopmind_shopping_task_actions", "shopmind_after_sales_drafts"}.issubset(tables)
            first_connection = engine.connect()
            second_connection = engine.connect()
            first_connection.execute(text(f'SET search_path TO "{schema}", public'))
            second_connection.execute(text(f'SET search_path TO "{schema}", public'))
            first_connection.commit(); second_connection.commit()
            first = sessionmaker(bind=first_connection, expire_on_commit=False)()
            task = create_task(first, owner_id="pg-task-owner", request=ShoppingTaskRequest(kind="compatibility_diagnosis", goal_text="连接无画面"), idempotency_key="pg-create-1")
            first.commit()
            assert first.scalars(select(ShoppingTaskStep).where(ShoppingTaskStep.task_id == task.id)).all()
            claimed = claim_task(first, worker_id="worker-a", lease_seconds=30)
            assert claimed is not None
            task, task_token = claimed
            first.commit()
            second = sessionmaker(bind=second_connection, expire_on_commit=False)()
            assert claim_task(second, worker_id="worker-b", lease_seconds=30) is None
            second.rollback()
            leased_task = first.get(ShoppingTask, task.id)
            assert leased_task.lease_token == task_token
            assert [row.status for row in first.scalars(select(ShoppingTaskStep).where(ShoppingTaskStep.task_id == task.id)).all()]
            step, attempt = claim_ready_step(first, task=leased_task, lease_token=task_token, lease_seconds=1)
            first.commit()
            old_token = step.lease_token
            step.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            first.commit()
            takeover = second.get(ShoppingTask, task.id)
            takeover.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            second.commit()
            replacement = claim_task(second, worker_id="worker-b", lease_seconds=30)
            assert replacement is not None
            _, replacement_token = replacement
            second.commit()
            late = StepResult(task_id=task.id, plan_revision=1, step_key=step.step_key, role=step.role, status="completed", output_kind=step.output_kind, output={}, input_fingerprint="late")
            with pytest.raises(LeaseConflict):
                save_step_result(first, task=first.get(ShoppingTask, task.id), step=first.get(ShoppingTaskStep, step.id), attempt=first.get(ShoppingTaskAttempt, attempt.id), lease_token=old_token or "", result=late)
            first.rollback()
            budget_task = create_task(second, owner_id="pg-budget-owner", request=ShoppingTaskRequest(kind="compatibility_diagnosis", goal_text="预算连续性"), idempotency_key="pg-budget-create")
            second.commit()
            budget_task.budget_json = {**budget_task.budget_json, "max_step_attempts": 1}
            second.commit()
            budget_claim = claim_task(second, worker_id="worker-budget", lease_seconds=30)
            assert budget_claim is not None
            budget_task, budget_token = budget_claim
            second.commit()
            budget_step, _budget_attempt = claim_ready_step(second, task=budget_task, lease_token=budget_token, lease_seconds=30)
            budget_step.status = "completed"
            budget_step.lease_token = None
            budget_step.lease_until = None
            second.commit()
            with pytest.raises(BudgetExceeded):
                claim_ready_step(second, task=second.get(ShoppingTask, budget_task.id), lease_token=budget_token, lease_seconds=30)
            delete_task = create_task(second, owner_id="pg-delete-owner", request=ShoppingTaskRequest(kind="compatibility_diagnosis", goal_text="删除 fencing"), idempotency_key="pg-delete-create")
            second.commit()
            delete_claim = claim_task(second, worker_id="worker-delete", lease_seconds=30)
            assert delete_claim is not None
            delete_task, delete_token = delete_claim
            second.commit()
            delete_step, delete_attempt = claim_ready_step(second, task=delete_task, lease_token=delete_token, lease_seconds=30)
            second.commit()
            delete_all_owner_data(second, owner_id="pg-delete-owner")
            second.commit()
            with pytest.raises(LeaseConflict):
                save_step_result(second, task=delete_task, step=delete_step, attempt=delete_attempt, lease_token=delete_step.lease_token or "", result=late.model_copy(update={"task_id": delete_task.id, "step_key": delete_step.step_key}))
            first.close(); second.close(); first_connection.close(); second_connection.close()
            command.downgrade(_alembic(connection), "0017_ai_extension_registry")
            assert "shopmind_shopping_tasks" not in set(inspect(connection).get_table_names(schema=schema))
            command.upgrade(_alembic(connection), "0018_shopping_task_workbench")
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()
