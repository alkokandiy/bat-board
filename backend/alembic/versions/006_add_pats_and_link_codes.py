"""Add bat_pats and bat_telegram_link_codes tables

Revision ID: 006
Revises: 005
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("bat_pats"):
        op.create_table(
            'bat_pats',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False, server_default='Telegram — Alfred'),
            sa.Column('token_hash', sa.String(), nullable=False),
            sa.Column('telegram_chat_id', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.Column('revoked', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], name='fk_bat_pats_owner_id', ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name='pk_bat_pats'),
        )
        with op.batch_alter_table('bat_pats') as batch_op:
            batch_op.create_index('ix_bat_pats_id', ['id'], unique=False)
            batch_op.create_index('ix_bat_pats_owner_id', ['owner_id'], unique=False)
            batch_op.create_unique_constraint('uq_bat_pats_telegram_chat_id', ['telegram_chat_id'])

    if not inspector.has_table("bat_telegram_link_codes"):
        op.create_table(
            'bat_telegram_link_codes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code_hash', sa.String(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], name='fk_bat_telegram_link_codes_owner_id', ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name='pk_bat_telegram_link_codes'),
        )
        with op.batch_alter_table('bat_telegram_link_codes') as batch_op:
            batch_op.create_index('ix_bat_telegram_link_codes_id', ['id'], unique=False)
            batch_op.create_index('ix_bat_telegram_link_codes_owner_id', ['owner_id'], unique=False)
            batch_op.create_unique_constraint('uq_bat_telegram_link_codes_code_hash', ['code_hash'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("bat_telegram_link_codes"):
        op.drop_table('bat_telegram_link_codes')
    if inspector.has_table("bat_pats"):
        op.drop_table('bat_pats')
