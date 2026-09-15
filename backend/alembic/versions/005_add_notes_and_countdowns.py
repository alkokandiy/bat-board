"""Add bat_notes and bat_countdowns tables

Revision ID: 005
Revises: 004
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Guards are defensive: on SQLite dev databases Base.metadata.create_all
    # may have already created these tables while alembic_version lagged,
    # which would otherwise fail with "table already exists".
    if not inspector.has_table("bat_notes"):
        op.create_table(
            'bat_notes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(), nullable=False, server_default=''),
            sa.Column('body', sa.String(), nullable=True),
            sa.Column('category', sa.String(), nullable=True),
            sa.Column('tags', sa.String(), nullable=True),
            sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], name='fk_bat_notes_owner_id', ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name='pk_bat_notes'),
        )
        with op.batch_alter_table('bat_notes') as batch_op:
            batch_op.create_index('ix_bat_notes_id', ['id'], unique=False)
            batch_op.create_index('ix_bat_notes_owner_id', ['owner_id'], unique=False)

    if not inspector.has_table("bat_countdowns"):
        op.create_table(
            'bat_countdowns',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('target_date', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], name='fk_bat_countdowns_owner_id', ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name='pk_bat_countdowns'),
        )
        with op.batch_alter_table('bat_countdowns') as batch_op:
            batch_op.create_index('ix_bat_countdowns_id', ['id'], unique=False)
            batch_op.create_index('ix_bat_countdowns_owner_id', ['owner_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("bat_countdowns"):
        op.drop_table('bat_countdowns')
    if inspector.has_table("bat_notes"):
        op.drop_table('bat_notes')
