"""A reminder that counts back from a mission's due date.

Reminders already fire at a clock time the user typed: "08:00 daily". That
is right for taking a tablet and wrong for a deadline, because the thing
the user means is "warn me *before* it is due", and the due date moves.
Phase 14 made it move with a drag of the wrist, so a fixed-time reminder
pointing at a mission now goes stale in one gesture: the mission slides to
next Tuesday and the warning still goes off on Thursday morning about work
that is not due for five days.

So a reminder gains one column, `offset_days`, and the recurrence gains
one value, `relative`. A relative reminder stores *how many days ahead* to
warn and reads the date from the mission it points at, which means it has
nothing of its own to go stale: reschedule the mission and every warning
on it moves too, with nothing to update.

Days rather than minutes, and it keeps its own `send_time`. Counting back
from the due *moment* sounds more precise and is worse for the common
case: a mission due Friday 23:59 with a one-day warning would ring on
Thursday at 23:59, which is nobody's idea of a day's notice. "One day
before, at 09:00" is what a day's notice means. 0 days is the warning on
the morning of, so "1 day ahead, and again on the day" is two rows.

Nullable, and no existing row is touched. `offset_days` is meaningless for
the four existing recurrences and stays NULL on them; `relative` is a new
value, so nothing that reads the old four changes meaning. That is also
why this is a new recurrence rather than a flag on the old ones — a weekly
reminder counting back from a due date is not a thing anyone asked for,
and allowing it would mean deciding what it meant.

Several warnings on one mission need no table: they are several rows
pointing at the same `mission_id` with different offsets, which is what
`mission_id` already allowed and nothing used.

Revision ID: 034
Revises: 033
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bat_reminders") as batch:
        batch.add_column(sa.Column("offset_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Rows that depend on the column go with it. A `relative` reminder with
    # no offset would fire on a date nothing defines, so leaving them behind
    # would be worse than losing them — and this runs only on a rollback,
    # where the code that understands them is going away too.
    op.execute("DELETE FROM bat_reminders WHERE recurrence = 'relative'")
    with op.batch_alter_table("bat_reminders") as batch:
        batch.drop_column("offset_days")
