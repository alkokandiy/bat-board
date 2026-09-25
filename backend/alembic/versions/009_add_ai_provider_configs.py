"""Add bat_ai_provider_configs (per-user BYOK provider config, key encrypted)

Revision ID: 009
Revises: 008
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name):
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, 'bat_ai_provider_configs'):
        op.create_table(
            'bat_ai_provider_configs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('provider', sa.String(), nullable=False),
            sa.Column('model_name', sa.String(), nullable=False),
            sa.Column('api_key_encrypted', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'],
                                    name='fk_bat_ai_provider_configs_owner_id',
                                    ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name='pk_bat_ai_provider_configs'),
            sa.UniqueConstraint('owner_id', name='uq_bat_ai_provider_configs_owner_id'),
        )
        with op.batch_alter_table('bat_ai_provider_configs') as batch_op:
            batch_op.create_index('ix_bat_ai_provider_configs_id', ['id'], unique=False)
            batch_op.create_index('ix_bat_ai_provider_configs_owner_id', ['owner_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table('bat_ai_provider_configs'):
        op.drop_table('bat_ai_provider_configs')
