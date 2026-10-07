"""Add bat_focus.planned_minutes for timed (auto-ending) focus sessions.

Nullable: existing and web (stopwatch) sessions stay NULL and are untouched by
the auto-end cron. A timed session set to N minutes is ended by the cron tick N
minutes after it starts, and the user is pinged on Telegram.

Revision ID: 016
Revises: 015
Create Date: 2026-10-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("bat_focus")}


def upgrade() -> None:
    if "planned_minutes" not in _cols(op.get_bind()):
        op.add_column("bat_focus", sa.Column("planned_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    if "planned_minutes" in _cols(op.get_bind()):
        with op.batch_alter_table("bat_focus") as batch:
            batch.drop_column("planned_minutes")
