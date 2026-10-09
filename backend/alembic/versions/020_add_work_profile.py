"""Work profile: the shape of the user's job (days, hours, expectations).

Lets the corporate track behave sensibly — no "are you drifting?" at 3pm on a
working Tuesday, and reports that compare logged hours against expected ones.

Revision ID: 020
Revises: 019
Create Date: 2026-10-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "bat_work_profiles" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "bat_work_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employer", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("work_days", sa.String(), nullable=True),
        sa.Column("work_start", sa.String(), nullable=True),
        sa.Column("work_end", sa.String(), nullable=True),
        sa.Column("expected_weekly_hours", sa.Integer(), nullable=True),
        sa.Column("started_on", sa.String(), nullable=True),
        sa.Column("report_time", sa.String(), nullable=True),
        sa.Column("daily_report", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("weekly_report_day", sa.Integer(), nullable=True),
        sa.Column("monthly_report", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("owner_id", name="uq_bat_work_profiles_owner"),
    )
    op.create_index("ix_bat_work_profiles_owner_id", "bat_work_profiles", ["owner_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "bat_work_profiles" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("bat_work_profiles")
