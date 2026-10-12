"""Habits get a cue, and a streak you cannot lose.

Two evidence-led additions:

`cue` — an implementation intention ("after I put the kettle on"). Specifying
when and where a habit happens is the strongest single lever in the habit
literature, and bat-board had no field for it at all.

`best_streak` — the longest run ever reached. A consecutive-day counter that
resets to zero is a measure you can only ever lose, and a broken streak reduces
people's willingness to continue even when the break was outside their control.
Keeping the best run permanently means a miss costs the current count, never
the achievement.

Both nullable/defaulted and additive: existing habits keep working untouched.

It also repairs a latent gap found while verifying this migration: `focus_minutes`
and `target_date` are declared on BatHabit in models.py but were never added by any
migration — they only exist on databases that were created by metadata.create_all
before migrations took over. A database built purely by `alembic upgrade head`
therefore had no such columns and would fail on any habit query. Every add here is
guarded, so databases that already have them are untouched.

Revision ID: 023
Revises: 022
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '023'
down_revision: Union[str, None] = '022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns("bat_habits")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind)
    if "cue" not in cols:
        op.add_column("bat_habits", sa.Column("cue", sa.String(), nullable=True))
    if "best_streak" not in cols:
        op.add_column("bat_habits", sa.Column(
            "best_streak", sa.Integer(), nullable=False, server_default="0"))
        # Nobody's best run is less than the streak they are already on.
        op.execute("UPDATE bat_habits SET best_streak = streak WHERE streak > best_streak")
    # Declared on the model but missing from the migration chain (see docstring).
    if "focus_minutes" not in cols:
        op.add_column("bat_habits", sa.Column(
            "focus_minutes", sa.Integer(), nullable=False, server_default="0"))
    if "target_date" not in cols:
        op.add_column("bat_habits", sa.Column(
            "target_date", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind)
    # SQLite cannot DROP COLUMN in older versions; batch mode handles both.
    # focus_minutes/target_date are deliberately NOT dropped: this migration did
    # not introduce them to the product, it only repaired their absence, and
    # removing them would break a downgraded database rather than restore it.
    with op.batch_alter_table("bat_habits") as batch:
        if "best_streak" in cols:
            batch.drop_column("best_streak")
        if "cue" in cols:
            batch.drop_column("cue")
