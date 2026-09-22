"""add durable shopping task workbench facts

Revision ID: 0018_shopping_task_workbench
Revises: 0017_ai_extension_registry
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_shopping_task_workbench"
down_revision: Union[str, None] = "0017_ai_extension_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.Uuid(as_uuid=True)
JSON = sa.JSON()
NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "shopmind_shopping_tasks",
        sa.Column("id", UUID, primary_key=True), sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False), sa.Column("thread_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("mode", sa.String(16), nullable=False, server_default="offline"),
        sa.Column("goal_json", JSON, nullable=False), sa.Column("goal_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active_plan_revision", sa.Integer(), nullable=False, server_default="1"), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("budget_json", JSON, nullable=False), sa.Column("output_json", JSON), sa.Column("pending_interaction_json", JSON),
        sa.Column("scheduler_epoch", sa.Integer(), nullable=False, server_default="0"), sa.Column("lease_token", sa.String(64)), sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("kind IN ('bundle_selection', 'compatibility_diagnosis', 'after_sales_assessment')", name="ck_shopmind_task_kind"),
        sa.CheckConstraint("status IN ('queued', 'running', 'waiting_input', 'awaiting_approval', 'succeeded', 'failed', 'cancelled', 'expired')", name="ck_shopmind_task_status"),
        sa.CheckConstraint("mode IN ('offline', 'agent')", name="ck_shopmind_task_mode"),
    )
    op.create_index("idx_shopmind_task_owner_created", "shopmind_shopping_tasks", ["owner_id", "created_at"])
    op.create_index("idx_shopmind_task_claim", "shopmind_shopping_tasks", ["status", "lease_until"])

    op.create_table(
        "shopmind_shopping_task_plans",
        sa.Column("id", UUID, primary_key=True), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("parent_revision", sa.Integer()), sa.Column("plan_json", JSON, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False), sa.Column("reason", sa.String(500), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("task_id", "revision", name="uq_shopmind_task_plan_revision"),
    )
    op.create_table(
        "shopmind_shopping_task_steps",
        sa.Column("id", UUID, primary_key=True), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False), sa.Column("step_key", sa.String(64), nullable=False), sa.Column("capability", sa.String(64), nullable=False), sa.Column("role", sa.String(32), nullable=False),
        sa.Column("dependencies_json", JSON, nullable=False), sa.Column("input_refs_json", JSON, nullable=False), sa.Column("output_kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"), sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("step_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_token", sa.String(64)), sa.Column("lease_until", sa.DateTime(timezone=True)), sa.Column("input_fingerprint", sa.String(64)), sa.Column("output_json", JSON), sa.Column("output_artifact_id", UUID), sa.Column("error_code", sa.String(96)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_id", "plan_revision", "step_key", name="uq_shopmind_task_step_key"),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'superseded')", name="ck_shopmind_task_step_status"),
    )
    op.create_index("idx_shopmind_task_step_ready", "shopmind_shopping_task_steps", ["task_id", "plan_revision", "status"])
    op.create_table(
        "shopmind_shopping_task_attempts",
        sa.Column("id", UUID, primary_key=True), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("step_id", UUID, sa.ForeignKey("shopmind_shopping_task_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False), sa.Column("run_id", sa.String(128)), sa.Column("trace_id", sa.String(128)), sa.Column("status", sa.String(32), nullable=False, server_default="running"), sa.Column("usage_json", JSON, nullable=False), sa.Column("error_code", sa.String(96)), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("step_id", "attempt_no", name="uq_shopmind_task_attempt_no"),
    )
    op.create_table(
        "shopmind_shopping_task_artifacts",
        sa.Column("id", UUID, primary_key=True), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("plan_revision", sa.Integer(), nullable=False), sa.Column("kind", sa.String(64), nullable=False), sa.Column("branch", sa.String(64), nullable=False), sa.Column("payload_json", JSON, nullable=False), sa.Column("input_fingerprint", sa.String(64), nullable=False), sa.Column("source_refs_json", JSON, nullable=False), sa.Column("evidence_versions_json", JSON, nullable=False), sa.Column("verification_status", sa.String(16), nullable=False, server_default="pending"), sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("verification_status IN ('pending', 'passed', 'failed', 'superseded')", name="ck_shopmind_task_artifact_status"),
    )
    op.create_index("idx_shopmind_task_artifact_owner_task", "shopmind_shopping_task_artifacts", ["task_id", "created_at"])
    op.create_table(
        "shopmind_shopping_task_events",
        sa.Column("id", UUID, primary_key=True), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("event_type", sa.String(64), nullable=False), sa.Column("public_payload_json", JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("task_id", "sequence", name="uq_shopmind_task_event_sequence"),
    )
    op.create_index("idx_shopmind_task_event_task_sequence", "shopmind_shopping_task_events", ["task_id", "sequence"])
    op.create_table(
        "shopmind_shopping_task_commands",
        sa.Column("id", UUID, primary_key=True), sa.Column("owner_id", sa.String(255), nullable=False), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE")), sa.Column("operation", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(255), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False), sa.Column("result_json", JSON), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW), sa.UniqueConstraint("owner_id", "operation", "idempotency_key", name="uq_shopmind_task_command_key"),
    )
    op.create_table(
        "shopmind_shopping_task_actions",
        sa.Column("id", UUID, primary_key=True), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("artifact_id", UUID, sa.ForeignKey("shopmind_shopping_task_artifacts.id", ondelete="RESTRICT"), nullable=False), sa.Column("action_type", sa.String(32), nullable=False), sa.Column("goal_version", sa.Integer(), nullable=False), sa.Column("plan_revision", sa.Integer(), nullable=False), sa.Column("action_version", sa.Integer(), nullable=False, server_default="1"), sa.Column("payload_json", JSON, nullable=False), sa.Column("status", sa.String(16), nullable=False, server_default="pending"), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("result_json", JSON), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("action_type IN ('add_bundle_to_cart', 'save_after_sales_draft')", name="ck_shopmind_task_action_type"), sa.CheckConstraint("status IN ('pending', 'confirmed', 'cancelled', 'expired', 'rejected')", name="ck_shopmind_task_action_status"), sa.UniqueConstraint("task_id", "action_version", name="uq_shopmind_task_action_version"),
    )
    op.create_table(
        "shopmind_after_sales_drafts",
        sa.Column("id", UUID, primary_key=True), sa.Column("action_id", UUID, sa.ForeignKey("shopmind_shopping_task_actions.id", ondelete="RESTRICT"), nullable=False), sa.Column("task_id", UUID, sa.ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("owner_id", sa.String(255), nullable=False), sa.Column("order_id", sa.String(128), nullable=False), sa.Column("status", sa.String(16), nullable=False, server_default="draft_only"), sa.Column("payload_json", JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW), sa.UniqueConstraint("action_id", name="uq_shopmind_after_sales_draft_action"),
    )
    op.create_table(
        "shopmind_catalog_compatibility_rules",
        sa.Column("id", UUID, primary_key=True), sa.Column("left_sku_code", sa.String(64), nullable=False), sa.Column("right_sku_code", sa.String(64), nullable=False), sa.Column("state", sa.String(16), nullable=False), sa.Column("reason", sa.String(500), nullable=False), sa.Column("rule_version", sa.String(32), nullable=False), sa.Column("source_ref_json", JSON, nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("left_sku_code", "right_sku_code", "rule_version", name="uq_shopmind_compatibility_rule"),
    )
    op.create_table(
        "shopmind_policy_rules",
        sa.Column("id", UUID, primary_key=True), sa.Column("policy_type", sa.String(64), nullable=False), sa.Column("region", sa.String(32), nullable=False), sa.Column("channel", sa.String(32), nullable=False), sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False), sa.Column("valid_until", sa.DateTime(timezone=True)), sa.Column("return_window_days", sa.Integer()), sa.Column("requires_unopened", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("source_ref_json", JSON, nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("idx_shopmind_policy_rule_scope", "shopmind_policy_rules", ["policy_type", "region", "channel", "active"])


def downgrade() -> None:
    op.drop_index("idx_shopmind_policy_rule_scope", table_name="shopmind_policy_rules")
    op.drop_table("shopmind_policy_rules")
    op.drop_table("shopmind_catalog_compatibility_rules")
    op.drop_table("shopmind_after_sales_drafts")
    op.drop_table("shopmind_shopping_task_actions")
    op.drop_index("idx_shopmind_task_event_task_sequence", table_name="shopmind_shopping_task_events")
    op.drop_table("shopmind_shopping_task_events")
    op.drop_table("shopmind_shopping_task_commands")
    op.drop_index("idx_shopmind_task_artifact_owner_task", table_name="shopmind_shopping_task_artifacts")
    op.drop_table("shopmind_shopping_task_artifacts")
    op.drop_table("shopmind_shopping_task_attempts")
    op.drop_index("idx_shopmind_task_step_ready", table_name="shopmind_shopping_task_steps")
    op.drop_table("shopmind_shopping_task_steps")
    op.drop_table("shopmind_shopping_task_plans")
    op.drop_index("idx_shopmind_task_claim", table_name="shopmind_shopping_tasks")
    op.drop_index("idx_shopmind_task_owner_created", table_name="shopmind_shopping_tasks")
    op.drop_table("shopmind_shopping_tasks")
