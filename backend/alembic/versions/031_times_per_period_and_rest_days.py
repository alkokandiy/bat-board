"""Three times a week, and a rest day that is not a failure.

Two things a habit could not say.

**"Three times a week."** `frequency` said how often the period came round
and `weekdays` said which days — but a habit done whichever three days suit
that week had no way to be described. Picking three fixed days is a
different promise, and a stricter one than most people can keep.

`times_per_period` is how many check-ins make the period count as kept. NULL
means one, which is what every habit means today, so nothing in the database
changes meaning.

`last_met_period` is needed because of it: with a target above one, the run
advances when the target is REACHED, not on the last check-in, and
`last_completed` can no longer stand in for it. NULL is read as "derive it
from last_completed", which is exactly right for every row that exists.

**A planned rest.** Not doing a habit on purpose was indistinguishable from
failing to do it: the day counted against adherence and broke the run. That
is the most-criticised gap in TickTick's habit tracker, and the fix is
simply to let the person say so. A skipped occasion leaves the denominator
rather than entering it as a miss, and the run steps over it.

One row per (habit, local day), unique so a double tap is idempotent. Dates
are stored as the user's own local ISO day, like the reminder log, because
"I am resting today" is a statement about their day and not about UTC.

Revision ID: 031
Revises: 030
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bat_habits") as batch:
        batch.add_column(sa.Column("times_per_period", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("last_met_period", sa.Integer(), nullable=True))

    op.create_table(
        "bat_habit_skips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("habit_id", sa.Integer(),
                  sa.ForeignKey("bat_habits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_date", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("habit_id", "local_date", name="uq_habit_skip_day"),
    )
    op.create_index("ix_habit_skips_owner", "bat_habit_skips", ["owner_id"])
    op.create_index("ix_habit_skips_habit", "bat_habit_skips", ["habit_id"])


def downgrade() -> None:
    op.drop_index("ix_habit_skips_habit", table_name="bat_habit_skips")
    op.drop_index("ix_habit_skips_owner", table_name="bat_habit_skips")
    op.drop_table("bat_habit_skips")
    with op.batch_alter_table("bat_habits") as batch:
        batch.drop_column("last_met_period")
        batch.drop_column("times_per_period")
