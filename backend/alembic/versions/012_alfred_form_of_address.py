"""Per-user form of address for Alfred (bat_account.alfred_address).

Alfred's prompt used to call every user "Master Al-Kokandiy". The original
owner keeps that address: the account that owns the legacy
"Alfred Context — Master Profile" note (migration 010) is backfilled, and
only when exactly one account owns it. Everyone else defaults to their
username until they choose a form of address in Profile.

Idempotent — safe to re-run.

Revision ID: 012
Revises: 011
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_PROFILE_TITLE = "Alfred Context — Master Profile"
LEGACY_ADDRESS = "Master Al-Kokandiy"


def upgrade() -> None:
    bind = op.get_bind()
    if "alfred_address" in {c["name"] for c in sa.inspect(bind).get_columns("bat_account")}:
        return
    op.add_column("bat_account", sa.Column("alfred_address", sa.String(), nullable=True))

    owners = bind.execute(
        sa.text("SELECT DISTINCT owner_id FROM bat_notes WHERE title = :title"),
        {"title": LEGACY_PROFILE_TITLE},
    ).fetchall()
    if len(owners) == 1:
        bind.execute(
            sa.text("UPDATE bat_account SET alfred_address = :addr WHERE id = :id AND alfred_address IS NULL"),
            {"addr": LEGACY_ADDRESS, "id": owners[0][0]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "alfred_address" in {c["name"] for c in sa.inspect(bind).get_columns("bat_account")}:
        with op.batch_alter_table("bat_account") as batch:
            batch.drop_column("alfred_address")
