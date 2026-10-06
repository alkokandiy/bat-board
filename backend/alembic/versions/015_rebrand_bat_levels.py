"""Rebrand the Bat Level ladder to clean Batman-canon names.

bat_level is a denormalised label derived from points; it's recomputed
whenever points change (services/common.calculate_bat_level). Existing rows
still hold the OLD label until their owner next earns/loses points, so this
data migration recomputes every row from its points with the NEW names.

No schema change — data only. Bands are unchanged.

Revision ID: 015
Revises: 014
Create Date: 2026-10-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _case(mapping) -> str:
    # mapping: list of (upper_exclusive_bound_or_None, label)
    whens = []
    for bound, label in mapping:
        safe = label.replace("'", "''")
        if bound is None:
            whens.append(f"ELSE '{safe}'")
        else:
            whens.append(f"WHEN points < {bound} THEN '{safe}'")
    return "UPDATE bat_account SET bat_level = CASE " + " ".join(whens) + " END"


NEW = [
    (2000, "The Recruit"), (5000, "The Vigilante"), (10000, "The Detective"),
    (20000, "Gotham's Shadow"), (35000, "The Caped Crusader"),
    (55000, "The Watchful Protector"), (80000, "The Dark Knight"),
    (120000, "Legend of Gotham"), (180000, "The Bat Incarnate"),
    (None, "The Dark Knight Eternal"),
]

OLD = [
    (2000, "The Orphan"), (5000, "The Vigilante"), (10000, "The Detective"),
    (20000, "Son of Gotham"), (35000, "The Caped Crusader"),
    (55000, "Heir of the Demon"), (80000, "The Dark Knight"),
    (120000, "Faris al-Khorasan"), (180000, "Sword of the Ummah"),
    (None, "Dark Knight of Khorasan"),
]


def upgrade() -> None:
    op.execute(_case(NEW))


def downgrade() -> None:
    op.execute(_case(OLD))
