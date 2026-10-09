"""Corporate / work track: bat_work_tasks, bat_work_notes, bat_focus.work_task_id.

A separate domain from missions on purpose — work must never leak into personal
lists, counts, briefings, nudges, stats or Bat Points.

Revision ID: 019
Revises: 018
Create Date: 2026-10-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def _focus_cols(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("bat_focus")}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _tables(bind)

    if "bat_work_tasks" not in existing:
        op.create_table(
            "bat_work_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("detail", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="todo"),
            sa.Column("project", sa.String(), nullable=True),
            sa.Column("due_date", sa.DateTime(), nullable=True),
            sa.Column("focus_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("owner_id", sa.Integer(),
                      sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
        )
        op.create_index("ix_bat_work_tasks_owner_id", "bat_work_tasks", ["owner_id"])

    if "bat_work_notes" not in existing:
        op.create_table(
            "bat_work_notes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False, server_default="note"),
            sa.Column("content", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("work_task_id", sa.Integer(),
                      sa.ForeignKey("bat_work_tasks.id", ondelete="SET NULL"), nullable=True),
            sa.Column("owner_id", sa.Integer(),
                      sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
        )
        op.create_index("ix_bat_work_notes_owner_id", "bat_work_notes", ["owner_id"])

    if "work_task_id" not in _focus_cols(bind):
        # batch_alter_table, not add_column: SQLite cannot ALTER in a foreign
        # key, so it needs the copy-and-move strategy. On PostgreSQL this is a
        # plain ALTER, so production is unaffected.
        with op.batch_alter_table("bat_focus") as batch:
            batch.add_column(sa.Column("work_task_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_bat_focus_work_task_id", "bat_work_tasks",
                ["work_task_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if "work_task_id" in _focus_cols(bind):
        with op.batch_alter_table("bat_focus") as batch:
            batch.drop_column("work_task_id")
    existing = _tables(bind)
    for table in ("bat_work_notes", "bat_work_tasks"):
        if table in existing:
            op.drop_table(table)
