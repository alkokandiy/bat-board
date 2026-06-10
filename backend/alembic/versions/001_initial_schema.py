"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bat_account',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False, default=0),
        sa.Column('bat_level', sa.String(), nullable=False, default='Gotham Recruit'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_bat_account_id'), 'bat_account', ['id'], unique=False)
    op.create_index(op.f('ix_bat_account_username'), 'bat_account', ['username'], unique=True)

    op.create_table(
        'bat_missions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('priority', sa.String(), nullable=False, default='medium'),
        sa.Column('status', sa.String(), nullable=False, default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bat_missions_id'), 'bat_missions', ['id'], unique=False)
    op.create_index(op.f('ix_bat_missions_title'), 'bat_missions', ['title'], unique=False)

    op.create_table(
        'bat_habits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('frequency', sa.String(), nullable=False, default='daily'),
        sa.Column('streak', sa.Integer(), nullable=False, default=0),
        sa.Column('last_completed', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bat_habits_id'), 'bat_habits', ['id'], unique=False)
    op.create_index(op.f('ix_bat_habits_name'), 'bat_habits', ['name'], unique=False)

    op.create_table(
        'habit_completion_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('habit_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['habit_id'], ['bat_habits.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_habit_completion_logs_id'), 'habit_completion_logs', ['id'], unique=False)

    op.create_table(
        'bat_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('details', sa.String(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bat_log_id'), 'bat_log', ['id'], unique=False)

    op.create_table(
        'bat_focus',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('soundtrack_metadata', sa.String(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bat_focus_id'), 'bat_focus', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bat_focus_id'), table_name='bat_focus')
    op.drop_table('bat_focus')
    op.drop_index(op.f('ix_bat_log_id'), table_name='bat_log')
    op.drop_table('bat_log')
    op.drop_index(op.f('ix_habit_completion_logs_id'), table_name='habit_completion_logs')
    op.drop_table('habit_completion_logs')
    op.drop_index(op.f('ix_bat_habits_id'), table_name='bat_habits')
    op.drop_index(op.f('ix_bat_habits_name'), table_name='bat_habits')
    op.drop_table('bat_habits')
    op.drop_index(op.f('ix_bat_missions_id'), table_name='bat_missions')
    op.drop_index(op.f('ix_bat_missions_title'), table_name='bat_missions')
    op.drop_table('bat_missions')
    op.drop_index(op.f('ix_bat_account_id'), table_name='bat_account')
    op.drop_index(op.f('ix_bat_account_username'), table_name='bat_account')
    op.drop_table('bat_account')