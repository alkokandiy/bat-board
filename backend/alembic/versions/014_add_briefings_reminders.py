"""Phase F: proactive briefings & reminders.

Four tables:
- bat_briefings       — per-user morning/night briefing config (unique owner+kind)
- bat_briefing_log    — exactly-once record of sent briefings (unique owner+kind+date)
- bat_reminders       — user-defined recurring/one-off reminders
- bat_reminder_log    — exactly-once record of sent reminder occurrences

All timestamps are TIMESTAMP WITHOUT TIME ZONE (naive UTC), matching the rest
of the schema and the models.DateTime TypeDecorator.

Revision ID: 014
Revises: 013
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _tables(bind)

    if "bat_briefings" not in existing:
        op.create_table(
            "bat_briefings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("send_time", sa.String(), nullable=False),
            sa.Column("include_missions", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_habits", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_events", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_focus", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_news", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("news_topics", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("owner_id", sa.Integer(),
                      sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("owner_id", "kind", name="uq_bat_briefings_owner_kind"),
        )
        op.create_index("ix_bat_briefings_owner_id", "bat_briefings", ["owner_id"])

    if "bat_briefing_log" not in existing:
        op.create_table(
            "bat_briefing_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("local_date", sa.String(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=False),
            sa.Column("owner_id", sa.Integer(),
                      sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("owner_id", "kind", "local_date",
                                name="uq_bat_briefing_log_owner_kind_date"),
        )
        op.create_index("ix_bat_briefing_log_owner_id", "bat_briefing_log", ["owner_id"])

    if "bat_reminders" not in existing:
        op.create_table(
            "bat_reminders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("message", sa.String(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("recurrence", sa.String(), nullable=False),
            sa.Column("send_time", sa.String(), nullable=False),
            sa.Column("weekdays", sa.String(), nullable=True),
            sa.Column("day_of_month", sa.Integer(), nullable=True),
            sa.Column("run_date", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("owner_id", sa.Integer(),
                      sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
        )
        op.create_index("ix_bat_reminders_owner_id", "bat_reminders", ["owner_id"])

    if "bat_reminder_log" not in existing:
        op.create_table(
            "bat_reminder_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("local_date", sa.String(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=False),
            sa.Column("reminder_id", sa.Integer(),
                      sa.ForeignKey("bat_reminders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("owner_id", sa.Integer(),
                      sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("reminder_id", "local_date",
                                name="uq_bat_reminder_log_reminder_date"),
        )
        op.create_index("ix_bat_reminder_log_reminder_id", "bat_reminder_log", ["reminder_id"])
        op.create_index("ix_bat_reminder_log_owner_id", "bat_reminder_log", ["owner_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = _tables(bind)
    for table in ("bat_reminder_log", "bat_reminders", "bat_briefing_log", "bat_briefings"):
        if table in existing:
            op.drop_table(table)
