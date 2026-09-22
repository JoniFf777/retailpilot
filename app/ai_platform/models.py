"""PostgreSQL-backed shopping evidence lifecycle models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


JSONB_TYPE = JSON().with_variant(JSONB, "postgresql")
BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class ShoppingEvidenceVersion(Base):
    """A validated but not necessarily active business-scoped evidence version."""

    __tablename__ = "shopmind_evidence_versions"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('product_guide', 'compatibility', 'buying_guide', 'store_policy')",
            name="ck_shopmind_evidence_type",
        ),
        CheckConstraint(
            "status IN ('processing', 'published', 'failed', 'revoked')",
            name="ck_shopmind_evidence_status",
        ),
        CheckConstraint("version >= 1", name="ck_shopmind_evidence_version_positive"),
        Index("idx_shopmind_evidence_scope", "evidence_type", "category_code", "policy_type"),
        Index("idx_shopmind_evidence_source", "source_fingerprint", "content_fingerprint"),
        Index("idx_shopmind_evidence_product", "product_ids", postgresql_using="gin"),
        Index("idx_shopmind_evidence_validity", "policy_type", "valid_from", "valid_until"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    evidence_key: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[Optional[str]] = mapped_column(String(255))
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    product_ids: Mapped[list] = mapped_column(JSONB_TYPE, nullable=False, default=list)
    sku_codes: Mapped[list] = mapped_column(JSONB_TYPE, nullable=False, default=list)
    category_code: Mapped[Optional[str]] = mapped_column(String(64))
    compatibility_keys: Mapped[list] = mapped_column(JSONB_TYPE, nullable=False, default=list)
    policy_type: Mapped[Optional[str]] = mapped_column(String(64))
    region: Mapped[Optional[str]] = mapped_column(String(64))
    channel: Mapped[Optional[str]] = mapped_column(String(64))
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")
    metadata_json: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ShoppingIngestionTask(Base):
    """Leased, resumable execution state for one evidence version."""

    __tablename__ = "shopmind_evidence_ingestion_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_shopmind_ingestion_task_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_shopmind_ingestion_attempts_nonnegative"),
        UniqueConstraint("idempotency_key", name="uq_shopmind_ingestion_idempotency"),
        Index("idx_shopmind_ingestion_claim", "status", "lease_until", "available_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    evidence_version_id: Mapped[int] = mapped_column(
        ForeignKey("shopmind_evidence_versions.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    current_node: Mapped[Optional[str]] = mapped_column(String(16))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(128))
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_error_code: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evidence_version: Mapped[ShoppingEvidenceVersion] = relationship()
    nodes: Mapped[list["ShoppingIngestionNode"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="ShoppingIngestionNode.id"
    )


class ShoppingIngestionNode(Base):
    """Per-node checkpoint and bounded execution facts."""

    __tablename__ = "shopmind_evidence_ingestion_nodes"
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('fetcher', 'parser', 'chunker', 'enricher', 'indexer')",
            name="ck_shopmind_ingestion_node_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
            name="ck_shopmind_ingestion_node_status",
        ),
        UniqueConstraint("task_id", "node_type", name="uq_shopmind_ingestion_task_node"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("shopmind_evidence_ingestion_tasks.id", ondelete="CASCADE"), nullable=False
    )
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    task: Mapped[ShoppingIngestionTask] = relationship(back_populates="nodes")


class ShoppingEvidencePublication(Base):
    """One active evidence version per stable business evidence key."""

    __tablename__ = "shopmind_evidence_publications"
    __table_args__ = (
        UniqueConstraint("evidence_key", name="uq_shopmind_evidence_publication_key"),
        UniqueConstraint("evidence_version_id", name="uq_shopmind_evidence_publication_version"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    evidence_key: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_version_id: Mapped[int] = mapped_column(
        ForeignKey("shopmind_evidence_versions.id", ondelete="CASCADE"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    evidence_version: Mapped[ShoppingEvidenceVersion] = relationship()


class AIExtensionDefinition(Base):
    """Versioned server-owned Prompt/Skill/MCP metadata and content."""

    __tablename__ = "shopmind_ai_extension_definitions"
    __table_args__ = (
        CheckConstraint(
            "extension_type IN ('prompt', 'skill', 'mcp_tool')",
            name="ck_shopmind_ai_extension_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'revoked')",
            name="ck_shopmind_ai_extension_status",
        ),
        UniqueConstraint("extension_type", "extension_key", "version", name="uq_shopmind_ai_extension_version"),
        Index("idx_shopmind_ai_extension_active", "extension_type", "extension_key", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    extension_type: Mapped[str] = mapped_column(String(16), nullable=False)
    extension_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_names: Mapped[list] = mapped_column(JSONB_TYPE, nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_ids: Mapped[list] = mapped_column(JSONB_TYPE, nullable=False, default=list)
    side_effect: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    metadata_json: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AIExtensionPublication(Base):
    __tablename__ = "shopmind_ai_extension_publications"
    __table_args__ = (UniqueConstraint("extension_type", "extension_key", name="uq_shopmind_ai_extension_publication"),)

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    extension_type: Mapped[str] = mapped_column(String(16), nullable=False)
    extension_key: Mapped[str] = mapped_column(String(128), nullable=False)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("shopmind_ai_extension_definitions.id", ondelete="CASCADE"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    definition: Mapped[AIExtensionDefinition] = relationship()


__all__ = [
    "AIExtensionDefinition",
    "AIExtensionPublication",
    "ShoppingEvidencePublication",
    "ShoppingEvidenceVersion",
    "ShoppingIngestionNode",
    "ShoppingIngestionTask",
]
