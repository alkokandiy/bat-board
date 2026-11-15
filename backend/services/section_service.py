"""Sections: a subdivision of one list.

This is not `list_service` with a different table name. It carries one
invariant that lists do not:

**A mission's section must belong to the mission's own list.**

A section is a subdivision of a particular list, so it means nothing
outside it. Everything awkward here follows from that — moving a mission
between lists cannot carry its section along, and `resolve` needs to know
which list the mission will be in, not which one it is in now.

As with the Inbox, "no section" is not a row: NULL means in the list and
not in a section, which is where every mission that already exists sits.
"""

from typing import Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from services import list_service

# The same shape as list_service.INBOX, for the same reason: the ungrouped
# bucket has no row, so the API needs a word for it.
NONE_SECTION = "none"

MAX_NAME = 60
MAX_PER_LIST = 40


def _owned(db: Session, user: models.BatAccount):
    return db.query(models.BatSection).filter(models.BatSection.owner_id == user.id)


def list_sections(
    db: Session, user: models.BatAccount, list_id: Optional[int] = None
) -> List[models.BatSection]:
    q = _owned(db, user)
    if list_id is not None:
        q = q.filter(models.BatSection.list_id == list_id)
    return q.order_by(models.BatSection.list_id,
                      models.BatSection.position,
                      models.BatSection.id).all()


def get_section(db: Session, user: models.BatAccount, section_id: int) -> Optional[models.BatSection]:
    return _owned(db, user).filter(models.BatSection.id == section_id).first()


def resolve(db: Session, user: models.BatAccount, value, list_id: Optional[int]) -> Optional[int]:
    """Turn what the caller sent into a `section_id` for a mission in `list_id`.

    `list_id` is the list the mission *will be in*, not the one it is in
    now: a request may move it and set its section in the same breath, and
    the section has to be checked against where it is going.

    A section in the right list, owned by this user, is accepted. Anything
    else is refused with the same message, including a section that exists
    and belongs to them but sits in a different list — it would otherwise
    be possible to build a mission in list A that claims a section of
    list B, and every view that groups by section would then have to decide
    which of the two to believe.
    """
    if value is None or value == NONE_SECTION or value == "":
        return None
    try:
        section_id = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{value}' is not a section")

    row = get_section(db, user, section_id)
    if row is None:
        raise ValueError("No such section")
    if list_id is None:
        # The Inbox is not a list, so it has nowhere to hang a section.
        raise ValueError("A mission in the Inbox cannot be in a section — give it a list first")
    if row.list_id != list_id:
        raise ValueError("That section belongs to a different list")
    return section_id


def _clean_name(name: Optional[str]) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("A section needs a name")
    if len(name) > MAX_NAME:
        raise ValueError(f"A section name is at most {MAX_NAME} characters")
    return name


def _name_taken(db, user, list_id: int, name: str, exclude: Optional[int]) -> bool:
    q = _owned(db, user).filter(
        models.BatSection.list_id == list_id,
        func.lower(models.BatSection.name) == name.lower(),
    )
    if exclude is not None:
        q = q.filter(models.BatSection.id != exclude)
    return q.first() is not None


def create_section(
    db: Session, user: models.BatAccount, list_id: int, name: str
) -> models.BatSection:
    # Through list_service so a section cannot be hung off another user's
    # list: this is the same chokepoint a mission's list_id goes through.
    owned_list_id = list_service.resolve(db, user, list_id)
    if owned_list_id is None:
        raise ValueError("A section needs a list — the Inbox cannot have sections")

    name = _clean_name(name)
    # Scoped per list, not per account: two projects may each want a
    # "Research" section and neither is a duplicate of the other.
    if _name_taken(db, user, owned_list_id, name, exclude=None):
        raise ValueError(f"That list already has a section called '{name}'")
    if len(list_sections(db, user, owned_list_id)) >= MAX_PER_LIST:
        raise ValueError(f"That is {MAX_PER_LIST} sections in one list.")

    last = (_owned(db, user)
            .filter(models.BatSection.list_id == owned_list_id)
            .order_by(models.BatSection.position.desc()).first())
    row = models.BatSection(
        name=name,
        list_id=owned_list_id,
        position=(last.position + 1) if last else 0,
        owner_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def rename_section(
    db: Session, user: models.BatAccount, section_id: int, name: str
) -> Optional[models.BatSection]:
    row = get_section(db, user, section_id)
    if row is None:
        return None
    cleaned = _clean_name(name)
    if _name_taken(db, user, row.list_id, cleaned, exclude=section_id):
        raise ValueError(f"That list already has a section called '{cleaned}'")
    row.name = cleaned
    db.commit()
    db.refresh(row)
    return row


def delete_section(db: Session, user: models.BatAccount, section_id: int) -> bool:
    """Delete the section. Its missions are ungrouped, never deleted, and
    they stay in the list — only the subdivision goes."""
    row = get_section(db, user, section_id)
    if row is None:
        return False
    db.query(models.BatMission).filter(
        models.BatMission.owner_id == user.id,
        models.BatMission.section_id == section_id,
    ).update({"section_id": None}, synchronize_session="fetch")
    db.delete(row)
    db.commit()
    return True


def reorder(
    db: Session, user: models.BatAccount, list_id: int, ordered_ids: Sequence[int]
) -> List[models.BatSection]:
    """Set positions within one list. Ids outside that list are ignored, so
    a stale client cannot drag a section out of the list it belongs to."""
    rows = {
        row.id: row
        for row in _owned(db, user).filter(models.BatSection.list_id == list_id).all()
    }
    position = 0
    for section_id in ordered_ids:
        row = rows.get(section_id)
        if row is None:
            continue
        row.position = position
        position += 1
    db.commit()
    return list_sections(db, user, list_id)


def open_counts(db: Session, user: models.BatAccount) -> Dict[str, int]:
    """Open missions per section. Same definition of open as the list
    badges: a count including finished work would never go down."""
    rows = (
        db.query(models.BatMission.section_id, func.count(models.BatMission.id))
        .filter(
            models.BatMission.owner_id == user.id,
            models.BatMission.section_id.isnot(None),
            models.BatMission.status != "completed",
            models.BatMission.is_dismissed.is_(False),
        )
        .group_by(models.BatMission.section_id)
        .all()
    )
    return {str(section_id): count for section_id, count in rows}


def find_by_name(
    db: Session, user: models.BatAccount, list_id: int, name: str
) -> Optional[models.BatSection]:
    """For Alfred, who is given a name and the list it is in."""
    name = (name or "").strip()
    if not name or list_id is None:
        return None
    return _owned(db, user).filter(
        models.BatSection.list_id == list_id,
        func.lower(models.BatSection.name) == name.lower(),
    ).first()
