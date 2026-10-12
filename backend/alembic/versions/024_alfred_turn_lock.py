"""One turn at a time, per user.

Telegram updates are processed in parallel threads. Two messages sent seconds
apart therefore ran as two concurrent turns that could not see each other:
replies answered the wrong message, and both turns could arm the destructive
confirmation gate, so a single YES confirmed whichever one happened to win.

This table is the serialisation point. The primary key is the owner, so
claiming it is one race-safe INSERT that behaves identically on SQLite and
PostgreSQL and across multiple workers.

Revision ID: 024
Revises: 023
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '024'
down_revision: Union[str, None] = '023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "bat_alfred_turn_lock"


def upgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(TABLE)
