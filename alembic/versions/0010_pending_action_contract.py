"""add versioned PendingAction resolution fields

Revision ID: 0010_pending_action_contract
Revises: 0009_shopmind_skus_inventory
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_pending_action_contract"
down_revision: Union[str, None] = "0009_shopmind_skus_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.add_column(
        "pending_actions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "pending_actions",
        sa.Column("result_json", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "pending_actions",
        sa.Column("resolution_request_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "pending_actions",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_pending_actions_version_positive", "pending_actions", "version >= 1"
    )


def downgrade() -> None:
    op.drop_constraint("ck_pending_actions_version_positive", "pending_actions", type_="check")
    op.drop_column("pending_actions", "resolved_at")
    op.drop_column("pending_actions", "resolution_request_hash")
    op.drop_column("pending_actions", "result_json")
    op.drop_column("pending_actions", "version")
