"""add_memory_entries

Revision ID: b3e9f1a2d7c4
Revises: 8fca78cf1516
Create Date: 2026-06-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision: str = 'b3e9f1a2d7c4'
down_revision: Union[str, Sequence[str], None] = '8fca78cf1516'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'memory_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('qdrant_point_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('source_task_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('importance', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Composite index for user queries sorted by importance
    op.execute("CREATE INDEX idx_memory_user ON memory_entries(user_id, importance DESC)")
    # Index for task-scoped memory lookups
    op.create_index('idx_memory_task', 'memory_entries', ['source_task_id'])
    # Partial index for decay job (only entries worth keeping)
    op.execute("CREATE INDEX idx_memory_decay ON memory_entries(updated_at) WHERE importance > 0.05")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_memory_decay")
    op.drop_index('idx_memory_task', 'memory_entries')
    op.execute("DROP INDEX IF EXISTS idx_memory_user")
    op.drop_table('memory_entries')
