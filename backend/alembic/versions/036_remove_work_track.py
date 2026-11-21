"""Remove the corporate/work track.

The owner stopped using it and asked for it gone from bat-board and from
Alfred both. This drops the three tables it owned, the switch on the account,
and the two foreign keys that pointed into it.

**This is destructive and the data is not recoverable.** It is done on the
owner's explicit instruction, which is what rule 3 requires. The downgrade
rebuilds the shape, not the contents, and says so rather than pretending.

The one thing that must NOT be lost is focus history. `bat_focus` rows could
carry a `work_task_id`, and those sessions are real hours somebody actually
sat through. Dropping the column leaves every one of those rows intact with
its minutes — they simply stop being labelled "work" and become unattached
sessions, which is what they always were underneath. Nothing cascades from
the work tables into focus, and the same holds for `bat_reminders`: a
reminder that pointed at a work task survives as a reminder with no link
rather than being deleted with it.

One behavioural consequence worth stating, because it is a rule change and
not a cleanup: a focus session on a work task used to earn **no** Bat Points,
deliberately — the job is not the person. With the track gone there is no
such thing as a work session, so sessions logged from now on all earn points
in the ordinary way. Nothing is awarded retroactively; past sessions keep the
points they were given at the time, which was none.

SQLite rewrites a table to drop a column, so every drop here goes through
batch_alter_table — the test database is SQLite and the production one is
Postgres, and this has to work on both.

Revision ID: 036
Revises: 035
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The links first: a column cannot outlive the table it references, and
    # dropping these keeps the rows that carried them.
    with op.batch_alter_table("bat_focus") as batch:
        batch.drop_column("work_task_id")
    with op.batch_alter_table("bat_reminders") as batch:
        batch.drop_column("work_task_id")

    op.drop_table("bat_work_notes")
    op.drop_table("bat_work_profiles")
    op.drop_table("bat_work_tasks")

    with op.batch_alter_table("bat_account") as batch:
        batch.drop_column("work_enabled")


def downgrade() -> None:
    """Rebuild the shape. The contents are gone and cannot be brought back."""
    op.create_table(
        "bat_work_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="todo"),
        sa.Column("project", sa.String(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("focus_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_table(
        "bat_work_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="note"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("work_task_id", sa.Integer(),
                  sa.ForeignKey("bat_work_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_table(
        "bat_work_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employer", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("work_days", sa.String(), nullable=True),
        sa.Column("work_start", sa.String(), nullable=True),
        sa.Column("work_end", sa.String(), nullable=True),
        sa.Column("weekly_hours", sa.Integer(), nullable=True),
        sa.Column("daily_report_time", sa.String(), nullable=True),
        sa.Column("weekly_report_day", sa.Integer(), nullable=True),
        sa.Column("monthly_report_day", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
    )
    with op.batch_alter_table("bat_account") as batch:
        batch.add_column(sa.Column("work_enabled", sa.Boolean(), nullable=True))
    # The reminder link must come back with the NAME migration 028 gave it.
    # Without it, downgrading further than this point fails: 028's own
    # downgrade drops `fk_bat_reminders_work_task` by name and cannot find a
    # constraint this file created anonymously.
    with op.batch_alter_table("bat_reminders") as batch:
        batch.add_column(sa.Column("work_task_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_bat_reminders_work_task", "bat_work_tasks", ["work_task_id"], ["id"],
            ondelete="SET NULL")
    # Focus never had a named constraint — 019 added the column plainly.
    with op.batch_alter_table("bat_focus") as batch:
        batch.add_column(sa.Column("work_task_id", sa.Integer(), nullable=True))
