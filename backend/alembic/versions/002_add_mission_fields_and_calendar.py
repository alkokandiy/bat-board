"""Add mission fields and calendar events

Revision ID: 002
Revises: 001
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bat_missions', sa.Column('tags', sa.String(), nullable=True))
    op.add_column('bat_missions', sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('bat_missions', sa.Column('is_dismissed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('bat_missions', sa.Column('location', sa.String(), nullable=True))
    op.add_column('bat_missions', sa.Column('notes', sa.String(), nullable=True))
    op.add_column('bat_missions', sa.Column('subtasks', sa.String(), nullable=True))

    op.create_table(
        'bat_calendar_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('mission_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mission_id'], ['bat_missions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bat_calendar_events_id'), 'bat_calendar_events', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bat_calendar_events_id'), table_name='bat_calendar_events')
    op.drop_table('bat_calendar_events')
    op.drop_column('bat_missions', 'subtasks')
    op.drop_column('bat_missions', 'notes')
    op.drop_column('bat_missions', 'location')
    op.drop_column('bat_missions', 'is_dismissed')
    op.drop_column('bat_missions', 'is_pinned')
    op.drop_column('bat_missions', 'tags')
