"""add multi-agent columns to tasks

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("parent_task_id", sa.UUID(), nullable=True))
    op.add_column("tasks", sa.Column("agent_role", sa.String(50), nullable=True))
    op.create_foreign_key(
        "fk_tasks_parent_task_id", "tasks",
        "tasks", ["parent_task_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_tasks_parent", "tasks", ["parent_task_id"])


def downgrade() -> None:
    op.drop_index("idx_tasks_parent", table_name="tasks")
    op.drop_constraint("fk_tasks_parent_task_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "agent_role")
    op.drop_column("tasks", "parent_task_id")
