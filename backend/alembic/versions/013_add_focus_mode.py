"""Add bat_focus.mode: the timer's visual mode when a session started.

Nullable: existing rows stay valid and show as "unknown" in stats.
Allowed values (enforced by the API, not the database): normal, flip,
signal, batmobile.

Revision ID: 013
Revises: 012
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _focus_columns(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("bat_focus")}


def upgrade() -> None:
    # Guarded: database._ensure_columns() may have added it already on a
    # database whose alembic_version is still behind.
    if "mode" not in _focus_columns(op.get_bind()):
        op.add_column("bat_focus", sa.Column("mode", sa.String(), nullable=True))


def downgrade() -> None:
    if "mode" in _focus_columns(op.get_bind()):
        with op.batch_alter_table("bat_focus") as batch:
            batch.drop_column("mode")
