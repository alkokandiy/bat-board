"""Proactive check-ins: per-user nudge settings + the nudge log.

Alfred reaches out unprompted when something on the board deserves a word.
`bat_nudge_log.nudge_key` encodes the specific occasion, and the UNIQUE
(owner_id, nudge_key) makes each occasion fire exactly once.

Revision ID: 017
Revises: 016
Create Date: 2026-10-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _account_cols(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("bat_account")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _account_cols(bind)
    if "nudges_enabled" not in cols:
        op.add_column("bat_account", sa.Column(
            "nudges_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "nudge_quiet_start" not in cols:
        op.add_column("bat_account", sa.Column("nudge_quiet_start", sa.String(), nullable=True))
    if "nudge_quiet_end" not in cols:
        op.add_column("bat_account", sa.Column("nudge_quiet_end", sa.String(), nullable=True))
    if "nudges_per_day" not in cols:
        op.add_column("bat_account", sa.Column("nudges_per_day", sa.Integer(), nullable=True))

    if "bat_nudge_log" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "bat_nudge_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nudge_key", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("local_date", sa.String(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=False),
            sa.Column("owner_id", sa.Integer(),
                      sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("owner_id", "nudge_key", name="uq_bat_nudge_log_owner_key"),
        )
        op.create_index("ix_bat_nudge_log_owner_id", "bat_nudge_log", ["owner_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "bat_nudge_log" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("bat_nudge_log")
    cols = _account_cols(bind)
    with op.batch_alter_table("bat_account") as batch:
        for name in ("nudges_per_day", "nudge_quiet_end", "nudge_quiet_start", "nudges_enabled"):
            if name in cols:
                batch.drop_column(name)
