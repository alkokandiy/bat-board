"""Add bat_reminders.ends_on — an optional last day for a recurring reminder.

Lets "remind me ... for one month" actually stop. NULL keeps the previous
behaviour (runs indefinitely), so existing reminders are unaffected.

Revision ID: 018
Revises: 017
Create Date: 2026-10-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("bat_reminders")}


def upgrade() -> None:
    if "ends_on" not in _cols(op.get_bind()):
        op.add_column("bat_reminders", sa.Column("ends_on", sa.String(), nullable=True))


def downgrade() -> None:
    if "ends_on" in _cols(op.get_bind()):
        with op.batch_alter_table("bat_reminders") as batch:
            batch.drop_column("ends_on")
