"""Add mission_id to bat_focus, focus_minutes + completed_focus_sessions to bat_missions

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
    op.add_column('bat_missions', sa.Column('focus_minutes', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('bat_missions', sa.Column('completed_focus_sessions', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('bat_focus', sa.Column('mission_id', sa.Integer(), sa.ForeignKey('bat_missions.id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    op.drop_column('bat_focus', 'mission_id')
    op.drop_column('bat_missions', 'completed_focus_sessions')
    op.drop_column('bat_missions', 'focus_minutes')
