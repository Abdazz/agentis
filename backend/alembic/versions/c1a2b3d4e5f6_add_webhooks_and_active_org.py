"""add_webhooks_and_active_org

Revision ID: c1a2b3d4e5f6
Revises: b3e9f1a2d7c4
Create Date: 2026-06-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'b3e9f1a2d7c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_webhooks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('secret_encrypted', sa.Text(), nullable=False),
        sa.Column('events', sa.String(512), nullable=False, server_default='task_completed'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_webhooks_user_id', 'user_webhooks', ['user_id'])

    op.add_column('users', sa.Column('active_organization_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_users_active_org',
        'users', 'organizations',
        ['active_organization_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_users_active_org', 'users', type_='foreignkey')
    op.drop_column('users', 'active_organization_id')
    op.drop_index('ix_user_webhooks_user_id', 'user_webhooks')
    op.drop_table('user_webhooks')
