"""add scheduled_tasks table

Revision ID: d4e5f6a7b8c9
Revises: c6d7e8f9a0b1
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("goal_template", sa.Text, nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("allowed_tools", sa.JSON, nullable=True),
        sa.Column("max_iterations", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scheduled_tasks_user_id", "scheduled_tasks", ["user_id"])
    op.create_index("ix_scheduled_tasks_next_run_at", "scheduled_tasks", ["next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_next_run_at", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_user_id", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
