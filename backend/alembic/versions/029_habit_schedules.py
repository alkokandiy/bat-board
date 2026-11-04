"""A habit can say which days it is actually due.

"If I choose every week, it's just guess? Which day of the week? And what if
I choose every month?"

Correct, and worse than a guess. `frequency` was the only scheduling field a
habit had, so "weekly" meant nothing more than "one check-in somewhere in a
Monday-to-Sunday bucket". A weekly habit therefore showed as still-to-keep on
all seven days until ticked once, a monthly one for a whole month, and the
adherence denominator counted raw days — so a twice-a-week habit kept
perfectly read as "2 of your last 14".

Reminders have had `weekdays` and `day_of_month` since migration 014. Habits
had neither.

Three columns, all nullable, plus a fourth frequency value:

    weekdays       CSV of 0-6, Mon=0   weekly: "every Monday and Thursday"
    day_of_month   1-31, clamped       monthly: "on the 1st"
    interval_days  N                   interval: "every third day"

NULL everywhere means exactly the old behaviour — any day in the period — so
every habit that exists today keeps meaning what it meant this morning. The
new "interval" frequency is additive; nothing is rewritten.

Revision ID: 029
Revises: 028
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bat_habits") as batch:
        batch.add_column(sa.Column("weekdays", sa.String(), nullable=True))
        batch.add_column(sa.Column("day_of_month", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("interval_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bat_habits") as batch:
        batch.drop_column("interval_days")
        batch.drop_column("day_of_month")
        batch.drop_column("weekdays")
