"""Add bat_alfred_messages, bat_pending_alfred_actions, bat_telegram_seen_updates, bat_alfred_usage

Revision ID: 007
Revises: 006
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_with_indexes(table_name, *columns, indexes=()):
    if sa.inspect(op.get_bind()).has_table(table_name):
        return
    op.create_table(table_name, *columns)
    with op.batch_alter_table(table_name) as batch_op:
        for name, cols, unique in indexes:
            if unique:
                batch_op.create_unique_constraint(name, cols)
            else:
                batch_op.create_index(name, cols, unique=False)


def upgrade() -> None:
    _create_with_indexes(
        'bat_alfred_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], name='fk_bat_alfred_messages_owner_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_bat_alfred_messages'),
        indexes=[
            ('ix_bat_alfred_messages_id', ['id'], False),
            ('ix_bat_alfred_messages_owner_id', ['owner_id'], False),
        ],
    )
    _create_with_indexes(
        'bat_pending_alfred_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('action_args', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('confirmation_message', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], name='fk_bat_pending_alfred_actions_owner_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_bat_pending_alfred_actions'),
        # owner_id uniqueness comes from the Column(unique=True) equivalent:
        # enforced here as a named constraint (create_table has no inline name).
        sa.UniqueConstraint('owner_id', name='uq_bat_pending_alfred_actions_owner_id'),
        indexes=[
            ('ix_bat_pending_alfred_actions_id', ['id'], False),
        ],
    )
    _create_with_indexes(
        'bat_telegram_seen_updates',
        sa.Column('update_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('update_id', name='pk_bat_telegram_seen_updates'),
    )
    _create_with_indexes(
        'bat_alfred_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('day', sa.String(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], name='fk_bat_alfred_usage_owner_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_bat_alfred_usage'),
        indexes=[
            ('ix_bat_alfred_usage_id', ['id'], False),
            ('ix_bat_alfred_usage_owner_id', ['owner_id'], False),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in (
        'bat_alfred_usage',
        'bat_telegram_seen_updates',
        'bat_pending_alfred_actions',
        'bat_alfred_messages',
    ):
        if inspector.has_table(table):
            op.drop_table(table)
