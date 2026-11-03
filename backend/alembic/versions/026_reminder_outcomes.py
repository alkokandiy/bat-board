"""A reminder can be answered.

The owner's medicine reminder fired every evening for a month. He took none of
them, and it kept going, because the system had no way to know. `BatReminder`
held no outcome field of any kind, `BatReminderLog` recorded only `sent_at`,
and the message went out as plain text with no buttons — so even a user who
wanted to answer had nothing to press.

A cue that fires and is never closed by a reward does not stay neutral: it
trains the association away. Repeating it unchanged is the one response
guaranteed to make it worse.

`outcome` and `responded_at` give the occurrence a reply. NULL means exactly
what it meant before — sent, never answered — so every existing row keeps its
meaning and no backfill is needed.

`consecutive_ignored` lives on the reminder itself so the scheduler can act on
a run without recounting the log on every tick, every minute, for every user.

Revision ID: 026
Revises: 025
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bat_reminder_log") as batch:
        # 'done' | 'skipped' | 'snoozed'. NULL = sent and never answered.
        batch.add_column(sa.Column("outcome", sa.String(), nullable=True))
        batch.add_column(sa.Column("responded_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("bat_reminders") as batch:
        # How many in a row went unanswered. Reset by any answer.
        batch.add_column(sa.Column(
            "consecutive_ignored", sa.Integer(),
            nullable=False, server_default=sa.text("0")))
        # Set when a run of silence suspends it, so Alfred can raise it once
        # and the scheduler can leave it alone.
        batch.add_column(sa.Column("suspended_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bat_reminders") as batch:
        batch.drop_column("suspended_at")
        batch.drop_column("consecutive_ignored")

    with op.batch_alter_table("bat_reminder_log") as batch:
        batch.drop_column("responded_at")
        batch.drop_column("outcome")
