"""A reminder can point at the thing it is about.

Until now a reminder was free text and nothing else: "Take the medicine" and
"Work on the pricelist" were the same kind of object, so the buttons under
them had to be the same too. That is why offering "Start focus" on every
reminder is wrong — most reminders are not work, and taking a tablet takes a
minute, which is below MIN_FOCUS_MINUTES and would never have become a
session anyway.

With an optional link the reminder can carry what it is for, and the buttons
follow from that:

  - no link      → Done · Not today · Stop this
  - a link       → the same, plus Start focus, because there is now something
                   to attach the session to
  - a habit link → "Done" also checks the habit in, so the reminder closes
                   the loop it exists to start rather than recording a
                   private note that the reminder was acknowledged

At most one link is meaningful at a time; nothing enforces that in the
schema, and the service picks the first it finds, because a stricter
constraint here would be a migration risk for no practical gain.

All three columns are nullable with ON DELETE SET NULL: deleting a mission
must not delete the reminder about it, and must not leave a dangling id.

Revision ID: 028
Revises: 027
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bat_reminders") as batch:
        batch.add_column(sa.Column("mission_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("habit_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("work_task_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_bat_reminders_mission", "bat_missions", ["mission_id"], ["id"],
            ondelete="SET NULL")
        batch.create_foreign_key(
            "fk_bat_reminders_habit", "bat_habits", ["habit_id"], ["id"],
            ondelete="SET NULL")
        batch.create_foreign_key(
            "fk_bat_reminders_work_task", "bat_work_tasks", ["work_task_id"], ["id"],
            ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("bat_reminders") as batch:
        batch.drop_constraint("fk_bat_reminders_work_task", type_="foreignkey")
        batch.drop_constraint("fk_bat_reminders_habit", type_="foreignkey")
        batch.drop_constraint("fk_bat_reminders_mission", type_="foreignkey")
        batch.drop_column("work_task_id")
        batch.drop_column("habit_id")
        batch.drop_column("mission_id")
