"""Remember the words Alfred actually used in each proactive message.

Variety is the point: before speaking again he is shown what he has recently
said, so he can avoid reusing an opening, a structure or a turn of phrase.
Nullable and additive — existing rows simply have no text, which reads as
"nothing known about that one".

Revision ID: 022
Revises: 021
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '022'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind) -> bool:
    cols = {c["name"] for c in sa.inspect(bind).get_columns("bat_nudge_log")}
    return "sent_text" in cols


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind):
        return
    op.add_column("bat_nudge_log", sa.Column("sent_text", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    # SQLite cannot DROP COLUMN in older versions; batch mode handles both.
    with op.batch_alter_table("bat_nudge_log") as batch:
        batch.drop_column("sent_text")
