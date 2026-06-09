"""add marketplace_plugins table

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_plugins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("version", sa.String(50), nullable=False, server_default="1.0.0"),
        sa.Column("author", sa.String(100), nullable=False, server_default="community"),
        sa.Column("installed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("registered_tool_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_marketplace_plugins_slug"),
    )
    op.create_index("ix_marketplace_plugins_slug", "marketplace_plugins", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_marketplace_plugins_slug", table_name="marketplace_plugins")
    op.drop_table("marketplace_plugins")
