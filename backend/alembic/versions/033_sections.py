"""Sections inside a list.

A list groups missions; a section groups them again inside it — the
`Getting Started / Feature Modules / Explore More` shape. Named by the
user, never fixed: TickTick hard-codes its habit sections to
Morning/Afternoon/Evening, and a fixed vocabulary is the wrong call for
something whose whole job is to match how one person thinks about one
project.

`bat_sections` hangs off a list, and `section_id` on a mission is nullable
in the same way `list_id` is: NULL means "in the list but not in any
section", which is where every mission that exists today sits. Ungrouped is
not a row, for the same reason the Inbox is not one.

The invariant this table adds, and the reason the service is not a copy of
`list_service`: **a mission's section must belong to the mission's own
list.** A section is meaningless outside the list that owns it, so moving a
mission to another list cannot carry its section along.

`section_id` is ON DELETE SET NULL — deleting a section ungroups its
missions rather than deleting them. `list_id` on the section is CASCADE,
which is a different answer on purpose: a section cannot outlive the list
it is a subdivision of, and the missions themselves are protected by their
own SET NULL on both columns.

Revision ID: 033
Revises: 032
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bat_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("list_id", sa.Integer(),
                  sa.ForeignKey("bat_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sections_list", "bat_sections", ["list_id"])
    op.create_index("ix_sections_owner", "bat_sections", ["owner_id"])

    with op.batch_alter_table("bat_missions") as batch:
        batch.add_column(sa.Column("section_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_missions_section", "bat_sections", ["section_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_missions_section", "bat_missions", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_missions_section", table_name="bat_missions")
    with op.batch_alter_table("bat_missions") as batch:
        batch.drop_constraint("fk_missions_section", type_="foreignkey")
        batch.drop_column("section_id")
    op.drop_index("ix_sections_owner", table_name="bat_sections")
    op.drop_index("ix_sections_list", table_name="bat_sections")
    op.drop_table("bat_sections")
