"""A mission belongs to a list.

Until now the board was one pile. Forty-odd open missions with no grouping
is not a list of things to do, it is a wall, and every filter laid over it
was still a filter over one flat pile.

`bat_lists` is the grouping: a name, a colour, an icon, a position, and an
archived flag. Archived rather than only deletable because a finished
project should stop taking up room in the rail without taking its history
with it.

`list_id` on `bat_missions` is **nullable**, and that is the whole
compatibility story: every mission that exists today has no list and keeps
working exactly as it did. Those appear as an **Inbox**, which is "no list
yet" — deliberately not a real row, so nobody can rename, archive or delete
the place unfiled missions live.

`ondelete="SET NULL"` for the same reason. Deleting a list must never
delete the work inside it; the missions fall back to the Inbox where they
can be seen and refiled. A cascade here would be a destructive migration
hiding inside an ordinary button.

No unique constraint on the name. Uniqueness among a user's *live* lists is
enforced in the service, where an archived list with the same name is not a
collision — a DB constraint would either forbid reusing the name of
something archived years ago or need an index subtle enough to be wrong on
one of the two databases this runs on.

Revision ID: 032
Revises: 031
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bat_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_lists_owner", "bat_lists", ["owner_id"])

    with op.batch_alter_table("bat_missions") as batch:
        batch.add_column(sa.Column("list_id", sa.Integer(), nullable=True))
        # Named so the downgrade can drop it on both databases; SQLite
        # invents a name otherwise and batch mode cannot find it again.
        batch.create_foreign_key(
            "fk_missions_list", "bat_lists", ["list_id"], ["id"], ondelete="SET NULL",
        )
    op.create_index("ix_missions_list", "bat_missions", ["list_id"])


def downgrade() -> None:
    op.drop_index("ix_missions_list", table_name="bat_missions")
    with op.batch_alter_table("bat_missions") as batch:
        batch.drop_constraint("fk_missions_list", type_="foreignkey")
        batch.drop_column("list_id")
    op.drop_index("ix_lists_owner", table_name="bat_lists")
    op.drop_table("bat_lists")
