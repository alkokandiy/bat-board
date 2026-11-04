"""Alfred's own unprompted messages become part of the conversation.

"it's just firing messages without knowing the context, what sent last time
and what received."

Correct, and the cause was structural rather than a prompt failure. Every
message Alfred sent on his own — a reminder, a briefing, a nudge, a work
report — went straight to Telegram and was never written to
`bat_alfred_messages`. His conversation history therefore contained only the
turns the user started. He genuinely could not see what he had said an hour
earlier, because nothing recorded it.

And a Telegram reply carries `reply_to_message`, which the webhook never
read. Replying to a specific message was indistinguishable from typing the
same words cold, so "Change it's time" arrived with no referent at all and
got resolved by guesswork.

Four nullable columns on bat_alfred_messages:

    telegram_message_id   the id Telegram gave the message, so a reply to it
                          can be resolved back to what it actually said
    origin                NULL/'chat' for a turn the user started, else what
                          sent it ('reminder', 'briefing', 'nudge', ...)
    about_kind/about_id   what the message was about, so a reply inherits a
                          hard target instead of searching the board for one

All nullable: every existing row is a chat turn with no Telegram id and
nothing attached, which is exactly what NULL means here.

Revision ID: 030
Revises: 029
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bat_alfred_messages") as batch:
        batch.add_column(sa.Column("telegram_message_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("origin", sa.String(), nullable=True))
        batch.add_column(sa.Column("about_kind", sa.String(), nullable=True))
        batch.add_column(sa.Column("about_id", sa.Integer(), nullable=True))
    # Resolving a reply is a lookup by (owner, telegram id) on every inbound
    # reply, so it should not be a scan of the whole message table.
    op.create_index("ix_alfred_messages_tg", "bat_alfred_messages",
                    ["owner_id", "telegram_message_id"])


def downgrade() -> None:
    op.drop_index("ix_alfred_messages_tg", table_name="bat_alfred_messages")
    with op.batch_alter_table("bat_alfred_messages") as batch:
        batch.drop_column("about_id")
        batch.drop_column("about_kind")
        batch.drop_column("origin")
        batch.drop_column("telegram_message_id")
