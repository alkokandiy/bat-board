"""Focus can record work that already happened.

"Add two hours focus for each, overall 10 hours for work tasks on the 17th and
18th" could not be done at all: every session had to be measured by a timer
running at the time, so real work done away from the board was simply lost.

`logged_manually` marks a session entered after the fact. It is a real record
of real work, but it is not the same evidence as a timer that ran, and blending
the two silently would make the figures mean less. Backfilled time earns no Bat
Points for the same reason.

(Focus already had `work_task_id` from migration 019 — the missing half was the
ability to record time retrospectively, not the link.)

Nullable/defaulted and additive; existing sessions are untouched.

Revision ID: 025
Revises: 024
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '025'
down_revision: Union[str, None] = '024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns("bat_focus")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind)
    # batch_alter_table so the FK is created correctly on SQLite too.
    with op.batch_alter_table("bat_focus") as batch:
        if "logged_manually" not in cols:
            # sa.false() renders per dialect. A literal "0" is an INTEGER to
            # PostgreSQL and it refuses it as a boolean default — SQLite takes
            # it without complaint, so this only shows up in production.
            batch.add_column(sa.Column("logged_manually", sa.Boolean(),
                                       nullable=False, server_default=sa.false()))


def downgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind)
    with op.batch_alter_table("bat_focus") as batch:
        if "logged_manually" in cols:
            batch.drop_column("logged_manually")
