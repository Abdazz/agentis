"""add tool_configs table

Revision ID: d1e2f3a4b5c6
Revises: c1a2b3d4e5f6
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "d1e2f3a4b5c6"
down_revision = "c1a2b3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled_globally", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allowed_orgs", JSON, nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="builtin"),
        sa.Column("mcp_url", sa.String(2048), nullable=True),
        sa.Column("openapi_spec_url", sa.String(2048), nullable=True),
        sa.Column("tool_metadata", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("name", name="uq_tool_configs_name"),
    )
    op.create_index("ix_tool_configs_name", "tool_configs", ["name"])


def downgrade() -> None:
    op.drop_index("ix_tool_configs_name", "tool_configs")
    op.drop_table("tool_configs")
