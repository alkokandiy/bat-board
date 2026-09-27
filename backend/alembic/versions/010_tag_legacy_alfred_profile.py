"""Tag the legacy 'Alfred Context — Master Profile' note as alfred-memory.

Data-only migration: finds the note by exact title and appends the
alfred-memory tag if absent, so alfred_recall finds it going forward.
Content untouched, no auto-splitting. No-op wherever the note is absent.
Idempotent — safe to re-run.

Revision ID: 010
Revises: 009
Create Date: 2026-09-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_TITLE = "Alfred Context — Master Profile"
MEMORY_TAG = "alfred-memory"


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, tags FROM bat_notes WHERE title = :title"),
        {"title": LEGACY_TITLE},
    ).fetchall()
    for note_id, tags in rows:
        present = [t.strip().lower() for t in (tags or "").split(",") if t.strip()]
        if MEMORY_TAG in present:
            continue
        new_tags = f"{tags}, {MEMORY_TAG}" if (tags or "").strip() else MEMORY_TAG
        conn.execute(
            sa.text("UPDATE bat_notes SET tags = :tags WHERE id = :id"),
            {"tags": new_tags, "id": note_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, tags FROM bat_notes WHERE title = :title"),
        {"title": LEGACY_TITLE},
    ).fetchall()
    for note_id, tags in rows:
        kept = [t for t in (tags or "").split(",")
                if t.strip() and t.strip().lower() != MEMORY_TAG]
        conn.execute(
            sa.text("UPDATE bat_notes SET tags = :tags WHERE id = :id"),
            {"tags": ", ".join(t.strip() for t in kept), "id": note_id},
        )
