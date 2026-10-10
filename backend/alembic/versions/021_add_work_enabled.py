"""Per-user switch for the corporate/work track.

Nullable on purpose — NULL means "the user never said". The application
resolves that to "on if they already have work data, off otherwise", so the
track keeps working for anyone already using it and stays hidden for everyone
else without backfilling a single row.

Revision ID: 021
Revises: 020
Create Date: 2026-10-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '021'
down_revision: Union[str, None] = '020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind) -> bool:
    cols = {c["name"] for c in sa.inspect(bind).get_columns("bat_account")}
    return "work_enabled" in cols


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind):
        return
    op.add_column("bat_account", sa.Column("work_enabled", sa.Boolean(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    # SQLite cannot DROP COLUMN in older versions; batch mode handles both.
    with op.batch_alter_table("bat_account") as batch:
        batch.drop_column("work_enabled")
