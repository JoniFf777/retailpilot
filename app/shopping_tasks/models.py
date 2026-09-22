"""PostgreSQL-backed facts for the shopping task workbench."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


TASK_JSON = JSON().with_variant(JSONB, "postgresql")


class ShoppingTask(Base):
    __tablename__ = "shopmind_shopping_tasks"
    __table_args__ = (
        CheckConstraint("kind IN ('bundle_selection', 'compatibility_diagnosis', 'after_sales_assessment')", name="ck_shopmind_task_kind"),
        CheckConstraint("status IN ('queued', 'running', 'waiting_input', 'awaiting_approval', 'succeeded', 'failed', 'cancelled', 'expired')", name="ck_shopmind_task_status"),
        CheckConstraint("mode IN ('offline', 'agent')", name="ck_shopmind_task_mode"),
        Index("idx_shopmind_task_owner_created", "owner_id", "created_at"),
        Index("idx_shopmind_task_claim", "status", "lease_until"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="offline")
    goal_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False)
    goal_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active_plan_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    budget_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False, default=dict)
    output_json: Mapped[Optional[dict]] = mapped_column(TASK_JSON)
    pending_interaction_json: Mapped[Optional[dict]] = mapped_column(TASK_JSON)
    scheduler_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_token: Mapped[Optional[str]] = mapped_column(String(64))
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    plans: Mapped[list["ShoppingTaskPlan"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    steps: Mapped[list["ShoppingTaskStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    artifacts: Mapped[list["ShoppingTaskArtifact"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    events: Mapped[list["ShoppingTaskEvent"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class ShoppingTaskWorkerHeartbeat(Base):
    __tablename__ = "shopmind_shopping_task_worker_heartbeats"
    __table_args__ = (
        Index("idx_shopmind_task_worker_last_seen", "last_seen_at"),
    )

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ShoppingTaskPlan(Base):
    __tablename__ = "shopmind_shopping_task_plans"
    __table_args__ = (UniqueConstraint("task_id", "revision", name="uq_shopmind_task_plan_revision"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision: Mapped[Optional[int]] = mapped_column(Integer)
    plan_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    task: Mapped[ShoppingTask] = relationship(back_populates="plans")


class ShoppingTaskStep(Base):
    __tablename__ = "shopmind_shopping_task_steps"
    __table_args__ = (
        UniqueConstraint("task_id", "plan_revision", "step_key", name="uq_shopmind_task_step_key"),
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'superseded')", name="ck_shopmind_task_step_status"),
        Index("idx_shopmind_task_step_ready", "task_id", "plan_revision", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False)
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    dependencies_json: Mapped[list] = mapped_column(TASK_JSON, nullable=False, default=list)
    input_refs_json: Mapped[list] = mapped_column(TASK_JSON, nullable=False, default=list)
    output_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_token: Mapped[Optional[str]] = mapped_column(String(64))
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    output_json: Mapped[Optional[dict]] = mapped_column(TASK_JSON)
    output_artifact_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True))
    error_code: Mapped[Optional[str]] = mapped_column(String(96))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    task: Mapped[ShoppingTask] = relationship(back_populates="steps")


class ShoppingTaskAttempt(Base):
    __tablename__ = "shopmind_shopping_task_attempts"
    __table_args__ = (UniqueConstraint("step_id", "attempt_no", name="uq_shopmind_task_attempt_no"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_task_steps.id", ondelete="CASCADE"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(128))
    trace_id: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    usage_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False, default=dict)
    error_code: Mapped[Optional[str]] = mapped_column(String(96))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ShoppingTaskArtifact(Base):
    __tablename__ = "shopmind_shopping_task_artifacts"
    __table_args__ = (
        CheckConstraint("verification_status IN ('pending', 'passed', 'failed', 'superseded')", name="ck_shopmind_task_artifact_status"),
        Index("idx_shopmind_task_artifact_owner_task", "task_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False)
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    branch: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_refs_json: Mapped[list] = mapped_column(TASK_JSON, nullable=False, default=list)
    evidence_versions_json: Mapped[list] = mapped_column(TASK_JSON, nullable=False, default=list)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    task: Mapped[ShoppingTask] = relationship(back_populates="artifacts")


class ShoppingTaskEvent(Base):
    __tablename__ = "shopmind_shopping_task_events"
    __table_args__ = (UniqueConstraint("task_id", "sequence", name="uq_shopmind_task_event_sequence"), Index("idx_shopmind_task_event_task_sequence", "task_id", "sequence"))

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    public_payload_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    task: Mapped[ShoppingTask] = relationship(back_populates="events")


class ShoppingTaskCommand(Base):
    __tablename__ = "shopmind_shopping_task_commands"
    __table_args__ = (UniqueConstraint("owner_id", "operation", "idempotency_key", name="uq_shopmind_task_command_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[Optional[dict]] = mapped_column(TASK_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ShoppingTaskAction(Base):
    __tablename__ = "shopmind_shopping_task_actions"
    __table_args__ = (
        CheckConstraint("action_type IN ('add_bundle_to_cart', 'save_after_sales_draft')", name="ck_shopmind_task_action_type"),
        CheckConstraint("status IN ('pending', 'confirmed', 'cancelled', 'expired', 'rejected')", name="ck_shopmind_task_action_status"),
        UniqueConstraint("task_id", "action_version", name="uq_shopmind_task_action_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_task_artifacts.id", ondelete="RESTRICT"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    goal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_json: Mapped[Optional[dict]] = mapped_column(TASK_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AfterSalesDraft(Base):
    __tablename__ = "shopmind_after_sales_drafts"
    __table_args__ = (UniqueConstraint("action_id", name="uq_shopmind_after_sales_draft_action"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    action_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_task_actions.id", ondelete="RESTRICT"), nullable=False)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_shopping_tasks.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft_only")
    payload_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CatalogCompatibilityRule(Base):
    __tablename__ = "shopmind_catalog_compatibility_rules"
    __table_args__ = (UniqueConstraint("left_sku_code", "right_sku_code", "rule_version", name="uq_shopmind_compatibility_rule"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    left_sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    right_sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ShoppingPolicyRule(Base):
    __tablename__ = "shopmind_policy_rules"
    __table_args__ = (Index("idx_shopmind_policy_rule_scope", "policy_type", "region", "channel", "active"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    policy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    return_window_days: Mapped[Optional[int]] = mapped_column(Integer)
    requires_unopened: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_ref_json: Mapped[dict] = mapped_column(TASK_JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


__all__ = [
    "AfterSalesDraft", "CatalogCompatibilityRule", "ShoppingPolicyRule", "ShoppingTask",
    "ShoppingTaskAction", "ShoppingTaskArtifact", "ShoppingTaskAttempt", "ShoppingTaskCommand",
    "ShoppingTaskEvent", "ShoppingTaskPlan", "ShoppingTaskStep", "ShoppingTaskWorkerHeartbeat",
]
