"""Add mission_id + habit_id to bat_focus, focus_minutes + completed_focus_sessions to bat_missions

Revision ID: 004
Revises: 003
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    mission_columns = {c["name"] for c in inspector.get_columns("bat_missions")}
    if 'focus_minutes' not in mission_columns:
        op.add_column('bat_missions', sa.Column('focus_minutes', sa.Integer(), nullable=False, server_default='0'))
    if 'completed_focus_sessions' not in mission_columns:
        op.add_column('bat_missions', sa.Column('completed_focus_sessions', sa.Integer(), nullable=False, server_default='0'))

    # Batch mode is required on SQLite: ALTER TABLE ADD COLUMN with a foreign
    # key is unsupported there, so the table is copied-and-recreated instead.
    # The column-existence guards are defensive: on SQLite dev databases,
    # database._ensure_columns() may have already backfilled these columns via
    # raw SQL while alembic_version was still pinned at 003, which would
    # otherwise fail the migration with "duplicate column name".
    focus_columns = {c["name"] for c in inspector.get_columns("bat_focus")}
    with op.batch_alter_table('bat_focus') as batch_op:
        if 'mission_id' not in focus_columns:
            batch_op.add_column(sa.Column('mission_id', sa.Integer(), sa.ForeignKey('bat_missions.id', name='fk_bat_focus_mission_id', ondelete='SET NULL'), nullable=True))
        if 'habit_id' not in focus_columns:
            batch_op.add_column(sa.Column('habit_id', sa.Integer(), sa.ForeignKey('bat_habits.id', name='fk_bat_focus_habit_id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    focus_columns = {c["name"] for c in inspector.get_columns("bat_focus")}
    with op.batch_alter_table('bat_focus') as batch_op:
        if 'mission_id' in focus_columns:
            batch_op.drop_column('mission_id')
        if 'habit_id' in focus_columns:
            batch_op.drop_column('habit_id')
    mission_columns = {c["name"] for c in inspector.get_columns("bat_missions")}
    if 'completed_focus_sessions' in mission_columns:
        op.drop_column('bat_missions', 'completed_focus_sessions')
    if 'focus_minutes' in mission_columns:
        op.drop_column('bat_missions', 'focus_minutes')
