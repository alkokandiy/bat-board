"""The finance ledger — accounts, categories, transactions.

Three tables and one invariant: every record MOVES MONEY BETWEEN ACCOUNTS.
Income lands in one, an expense leaves one, a transfer does both. There is no
fourth shape, which is what stops a credit-card payment being counted as
spending on top of the purchases it settles.

Amounts are BigInteger counts of minor units, never Float. Floating point
cannot represent 0.10, so a ledger built on it drifts, and the symptom is a
balance wrong by a few units that nobody can explain. BigInteger rather than
Integer because a modest year in a low-denomination currency already runs to
1.5e9 minor units and anything car-sized overflows 32 bits.

`rate_to_main` lives on the transaction rather than being looked up at read
time: re-deriving history from today's rate would make last year's spending
change every time the exchange rate moved.

All three tables are CASCADE on the owner. `category_id` is SET NULL, because
deleting a category must uncategorise its transactions, never delete money that
was really spent. Account links are CASCADE: a transaction whose account is
gone has no meaning, and leaving it would corrupt every balance it touches.

Nothing here is destructive — three new tables and three nullable columns on
`bat_account`, so existing users are untouched and the downgrade is clean.

Revision ID: 035
Revises: 034
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("group", sa.String(), nullable=False, server_default="cash"),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("opening_balance_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("settlement_day", sa.Integer(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_finance_accounts_owner_id", "finance_accounts", ["owner_id"])

    op.create_table(
        "finance_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("parent_id", sa.Integer(),
                  sa.ForeignKey("finance_categories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_finance_categories_owner_id", "finance_categories", ["owner_id"])
    op.create_index("ix_finance_categories_parent_id", "finance_categories", ["parent_id"])

    op.create_table(
        "finance_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("rate_to_main", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("fee_minor", sa.BigInteger(), nullable=True),
        sa.Column("from_account_id", sa.Integer(),
                  sa.ForeignKey("finance_accounts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("to_account_id", sa.Integer(),
                  sa.ForeignKey("finance_accounts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("category_id", sa.Integer(),
                  sa.ForeignKey("finance_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_finance_transactions_owner_id", "finance_transactions", ["owner_id"])
    op.create_index("ix_finance_transactions_occurred_on", "finance_transactions", ["occurred_on"])
    op.create_index("ix_finance_transactions_from_account_id", "finance_transactions", ["from_account_id"])
    op.create_index("ix_finance_transactions_to_account_id", "finance_transactions", ["to_account_id"])
    op.create_index("ix_finance_transactions_category_id", "finance_transactions", ["category_id"])

    # Nullable on purpose. `finance_enabled` NULL means "never decided" and is
    # resolved at read time, exactly as `work_enabled` is, so nobody gets a
    # money module they did not ask for and nobody using one loses it.
    # `main_currency` is never defaulted in code: rule 1 says no currency is
    # the house one, and guessing would mislabel every figure on the page.
    op.add_column("bat_account", sa.Column("finance_enabled", sa.Boolean(), nullable=True))
    op.add_column("bat_account", sa.Column("main_currency", sa.String(), nullable=True))
    op.add_column("bat_account", sa.Column("period_start_day", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("bat_account", "period_start_day")
    op.drop_column("bat_account", "main_currency")
    op.drop_column("bat_account", "finance_enabled")
    op.drop_table("finance_transactions")
    op.drop_table("finance_categories")
    op.drop_table("finance_accounts")
