"""add task_templates table

Revision ID: c6d7e8f9a0b1
Revises: c1d2e3f4a5b6
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c6d7e8f9a0b1"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("goal_template", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_task_templates_created_by", "task_templates", ["created_by"])
    op.create_index("ix_task_templates_created_at", "task_templates", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_task_templates_created_at", table_name="task_templates")
    op.drop_index("ix_task_templates_created_by", table_name="task_templates")
    op.drop_table("task_templates")
