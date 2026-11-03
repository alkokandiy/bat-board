"""Shrink the habit instead of losing it.

Two additions, both from the owner's research.

`minimum_viable` is the two-minute version of a habit, named by the user:
"put the running shoes on" for a five-mile run, "one page" for a chapter. The
point is not the reduced effort — it is that initiating the cue and closing
the reward keeps the loop intact, and the loop is what is being built. A day
that is too much for the full thing is not a day the habit has to break.

`grace_used_in_run` is the paper's `grace_periods_applied`. A single missed
period inside a run no longer resets it, provided the habit is otherwise
being kept. A counter that can only ever go to zero is one you can only
lose, and losing it measurably reduces the chance anyone carries on — which
is the whole reason the reward here follows recent adherence and not the
consecutive count. The run is the softer, visible number; it should survive a
blameless Tuesday.

Both nullable or defaulted. `best_streak` is untouched, and nothing here
changes what a check-in earns.

Revision ID: 027
Revises: 026
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bat_habits") as batch:
        batch.add_column(sa.Column("minimum_viable", sa.String(), nullable=True))
        batch.add_column(sa.Column(
            "grace_used_in_run", sa.Integer(),
            nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    with op.batch_alter_table("bat_habits") as batch:
        batch.drop_column("grace_used_in_run")
        batch.drop_column("minimum_viable")
