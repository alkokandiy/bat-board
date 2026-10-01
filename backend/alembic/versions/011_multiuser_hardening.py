"""Multi-user hardening: per-user timezone, token versioning, link-attempt
throttle, and one usage row per (user, day).

- bat_account.timezone: IANA zone. Existing accounts are backfilled with
  Asia/Tashkent — the zone the whole app was hard-coded to before — so
  their behaviour is unchanged until they pick another one.
- bat_account.token_version: bumped on password change to revoke tokens.
- bat_telegram_link_attempts: failed link-code attempts per chat.
- bat_alfred_usage: duplicate (owner_id, day) rows (possible under the old
  read-then-insert race) are merged, then a unique constraint is added.

Idempotent — safe to re-run.

Revision ID: 011
Revises: 010
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_TIMEZONE = "Asia/Tashkent"
USAGE_CONSTRAINT = "uq_bat_alfred_usage_owner_day"


def _columns(bind, table):
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    account_cols = _columns(bind, "bat_account")
    if "timezone" not in account_cols:
        op.add_column("bat_account", sa.Column("timezone", sa.String(), nullable=True))
        bind.execute(
            sa.text("UPDATE bat_account SET timezone = :tz WHERE timezone IS NULL"),
            {"tz": LEGACY_TIMEZONE},
        )
    if "token_version" not in account_cols:
        op.add_column(
            "bat_account",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )

    if not inspector.has_table("bat_telegram_link_attempts"):
        op.create_table(
            "bat_telegram_link_attempts",
            sa.Column("chat_id", sa.String(), nullable=False),
            sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("window_started_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("chat_id", name="pk_bat_telegram_link_attempts"),
        )

    existing = {uc["name"] for uc in inspector.get_unique_constraints("bat_alfred_usage")}
    if USAGE_CONSTRAINT not in existing:
        dupes = bind.execute(sa.text(
            "SELECT owner_id, day, MIN(id), SUM(count) FROM bat_alfred_usage "
            "GROUP BY owner_id, day HAVING COUNT(*) > 1"
        )).fetchall()
        for owner_id, day, keep_id, total in dupes:
            bind.execute(
                sa.text("UPDATE bat_alfred_usage SET count = :total WHERE id = :id"),
                {"total": total, "id": keep_id},
            )
            bind.execute(
                sa.text(
                    "DELETE FROM bat_alfred_usage "
                    "WHERE owner_id = :owner AND day = :day AND id <> :id"
                ),
                {"owner": owner_id, "day": day, "id": keep_id},
            )
        with op.batch_alter_table("bat_alfred_usage") as batch:
            batch.create_unique_constraint(USAGE_CONSTRAINT, ["owner_id", "day"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing = {uc["name"] for uc in inspector.get_unique_constraints("bat_alfred_usage")}
    if USAGE_CONSTRAINT in existing:
        with op.batch_alter_table("bat_alfred_usage") as batch:
            batch.drop_constraint(USAGE_CONSTRAINT, type_="unique")
    if inspector.has_table("bat_telegram_link_attempts"):
        op.drop_table("bat_telegram_link_attempts")
    account_cols = _columns(bind, "bat_account")
    with op.batch_alter_table("bat_account") as batch:
        if "token_version" in account_cols:
            batch.drop_column("token_version")
        if "timezone" in account_cols:
            batch.drop_column("timezone")
