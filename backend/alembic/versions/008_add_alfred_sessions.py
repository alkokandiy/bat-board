"""Add bat_alfred_sessions, session_id to messages, active_alfred_session_id to account

Revision ID: 008
Revises: 007
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name):
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create bat_alfred_sessions
    if not _has_table(bind, 'bat_alfred_sessions'):
        op.create_table(
            'bat_alfred_sessions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['owner_id'], ['bat_account.id'],
                                    name='fk_bat_alfred_sessions_owner_id',
                                    ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name='pk_bat_alfred_sessions'),
        )
        with op.batch_alter_table('bat_alfred_sessions') as batch_op:
            batch_op.create_index('ix_bat_alfred_sessions_id', ['id'], unique=False)
            batch_op.create_index('ix_bat_alfred_sessions_owner_id', ['owner_id'], unique=False)

    # 2. Add session_id to bat_alfred_messages (nullable initially)
    with op.batch_alter_table('bat_alfred_messages') as batch_op:
        cols = [c['name'] for c in sa.inspect(bind).get_columns('bat_alfred_messages')]
        if 'session_id' not in cols:
            batch_op.add_column(sa.Column('session_id', sa.Integer(), nullable=True))
            batch_op.create_index('ix_bat_alfred_messages_session_id', ['session_id'], unique=False)
            batch_op.create_foreign_key(
                'fk_bat_alfred_messages_session_id',
                'bat_alfred_sessions', ['session_id'], ['id'],
                ondelete='CASCADE',
            )

    # 3. Backfill: for each owner with existing messages, create one session
    #    and point all their messages at it.
    conn = op.get_bind()
    owner_rows = conn.execute(
        sa.text("SELECT DISTINCT owner_id FROM bat_alfred_messages WHERE session_id IS NULL")
    ).fetchall()
    for (owner_id,) in owner_rows:
        result = conn.execute(
            sa.text(
                "INSERT INTO bat_alfred_sessions (title, created_at, updated_at, owner_id) "
                "VALUES ('Earlier conversation', NOW(), NOW(), :owner_id) "
                "RETURNING id"
            ),
            {"owner_id": owner_id},
        )
        session_id = result.fetchone()[0]
        conn.execute(
            sa.text(
                "UPDATE bat_alfred_messages SET session_id = :session_id "
                "WHERE owner_id = :owner_id AND session_id IS NULL"
            ),
            {"session_id": session_id, "owner_id": owner_id},
        )

    # 4. Make session_id NOT NULL
    with op.batch_alter_table('bat_alfred_messages') as batch_op:
        batch_op.alter_column('session_id', nullable=False)

    # 5. Add active_alfred_session_id to bat_account
    with op.batch_alter_table('bat_account') as batch_op:
        cols = [c['name'] for c in sa.inspect(bind).get_columns('bat_account')]
        if 'active_alfred_session_id' not in cols:
            batch_op.add_column(sa.Column('active_alfred_session_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_bat_account_active_alfred_session_id',
                'bat_alfred_sessions', ['active_alfred_session_id'], ['id'],
                ondelete='SET NULL',
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    with op.batch_alter_table('bat_account') as batch_op:
        cols = [c['name'] for c in inspector.get_columns('bat_account')]
        if 'active_alfred_session_id' in cols:
            batch_op.drop_constraint('fk_bat_account_active_alfred_session_id', type_='foreignkey')
            batch_op.drop_column('active_alfred_session_id')

    with op.batch_alter_table('bat_alfred_messages') as batch_op:
        cols = [c['name'] for c in inspector.get_columns('bat_alfred_messages')]
        if 'session_id' in cols:
            batch_op.drop_constraint('fk_bat_alfred_messages_session_id', type_='foreignkey')
            batch_op.drop_index('ix_bat_alfred_messages_session_id')
            batch_op.drop_column('session_id')

    if inspector.has_table('bat_alfred_sessions'):
        op.drop_table('bat_alfred_sessions')
