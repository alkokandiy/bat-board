"""Lists: the grouping a mission belongs to.

Two rules shape everything here.

**The Inbox is not a row.** A mission with `list_id IS NULL` is unfiled, and
that is what the Inbox shows. Making it a real list would mean it could be
renamed, archived, reordered or deleted, and then unfiled missions would
have nowhere to be. `INBOX` is the id the API uses to talk about it.

**Nothing crosses owners.** `resolve(...)` is the only way a list id enters
a mission, and it refuses an id belonging to somebody else by returning the
same error as an id that does not exist — telling the two apart would
confirm that another user's list exists.
"""

from typing import Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

import models

# The Inbox is addressed by a sentinel rather than an id, because it has no
# row. "inbox" over None so it survives a query string and a JSON body.
INBOX = "inbox"

MAX_NAME = 60
MAX_LISTS = 60


def _live(q):
    return q.filter(models.BatList.archived.is_(False))


def _owned(db: Session, user: models.BatAccount):
    return db.query(models.BatList).filter(models.BatList.owner_id == user.id)


def list_lists(
    db: Session, user: models.BatAccount, include_archived: bool = False
) -> List[models.BatList]:
    q = _owned(db, user)
    if not include_archived:
        q = _live(q)
    # Position, then id: two lists created in the same request would
    # otherwise come back in whatever order the database felt like.
    return q.order_by(models.BatList.position, models.BatList.id).all()


def get_list(db: Session, user: models.BatAccount, list_id: int) -> Optional[models.BatList]:
    return _owned(db, user).filter(models.BatList.id == list_id).first()


def resolve(db: Session, user: models.BatAccount, value) -> Optional[int]:
    """Turn whatever the caller sent into a `list_id` for a mission.

    `None` and the Inbox sentinel both mean unfiled. Anything else must be
    one of this user's own lists, archived or not — a mission already in a
    list that was archived must still be editable.
    """
    if value is None or value == INBOX or value == "":
        return None
    try:
        list_id = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{value}' is not a list")
    if get_list(db, user, list_id) is None:
        raise ValueError("No such list")
    return list_id


def _name_taken(db: Session, user: models.BatAccount, name: str, exclude: Optional[int]) -> bool:
    q = _live(_owned(db, user)).filter(func.lower(models.BatList.name) == name.lower())
    if exclude is not None:
        q = q.filter(models.BatList.id != exclude)
    return q.first() is not None


def _clean_name(name: Optional[str]) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("A list needs a name")
    if len(name) > MAX_NAME:
        raise ValueError(f"A list name is at most {MAX_NAME} characters")
    return name


def create_list(
    db: Session,
    user: models.BatAccount,
    name: str,
    color: Optional[str] = None,
    icon: Optional[str] = None,
) -> models.BatList:
    name = _clean_name(name)
    if _name_taken(db, user, name, exclude=None):
        raise ValueError(f"You already have a list called '{name}'")
    if len(list_lists(db, user, include_archived=True)) >= MAX_LISTS:
        raise ValueError(f"That is {MAX_LISTS} lists. Archive one before adding another.")

    last = _owned(db, user).order_by(models.BatList.position.desc()).first()
    row = models.BatList(
        name=name,
        color=color,
        icon=icon,
        position=(last.position + 1) if last else 0,
        owner_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


_UNSET = object()


def update_list(
    db: Session,
    user: models.BatAccount,
    list_id: int,
    name=_UNSET,
    color=_UNSET,
    icon=_UNSET,
    archived=_UNSET,
) -> Optional[models.BatList]:
    row = get_list(db, user, list_id)
    if row is None:
        return None

    if name is not _UNSET:
        cleaned = _clean_name(name)
        if _name_taken(db, user, cleaned, exclude=list_id):
            raise ValueError(f"You already have a list called '{cleaned}'")
        row.name = cleaned
    # A sentinel, not `is not None`, so a colour or icon can be cleared
    # back to the default rather than only ever changed to another value.
    if color is not _UNSET:
        row.color = color
    if icon is not _UNSET:
        row.icon = icon
    if archived is not _UNSET:
        row.archived = bool(archived)

    db.commit()
    db.refresh(row)
    return row


def delete_list(db: Session, user: models.BatAccount, list_id: int) -> bool:
    """Delete the list. Its missions are refiled to the Inbox, never deleted.

    Three things would each do this on their own: the column's
    `ondelete="SET NULL"`, SQLAlchemy nulling the foreign key of children it
    has loaded, and the statement below. Removing it changes no test.

    It stays because "deleting a list must never delete the work in it" is
    the kind of promise that should be visible in the function that makes
    it, rather than resting on which of two databases is running and
    whether the session happened to load the rows.
    """
    row = get_list(db, user, list_id)
    if row is None:
        return False
    db.query(models.BatMission).filter(
        models.BatMission.owner_id == user.id,
        models.BatMission.list_id == list_id,
    ).update({"list_id": None}, synchronize_session="fetch")
    db.delete(row)
    db.commit()
    return True


def reorder(db: Session, user: models.BatAccount, ordered_ids: Sequence[int]) -> List[models.BatList]:
    """Set positions from the order given. Ids that are not this user's are
    ignored rather than refused, so a stale rail cannot wedge a drag."""
    rows = {row.id: row for row in _owned(db, user).all()}
    position = 0
    for list_id in ordered_ids:
        row = rows.get(list_id)
        if row is None:
            continue
        row.position = position
        position += 1
    db.commit()
    return list_lists(db, user)


def open_counts(db: Session, user: models.BatAccount) -> Dict[str, int]:
    """How many missions are waiting in each list, Inbox included.

    Open means pending and not dismissed: a count that included finished
    work would never go down, which is the opposite of what a badge beside
    a list name is for.
    """
    rows = (
        db.query(models.BatMission.list_id, func.count(models.BatMission.id))
        .filter(
            models.BatMission.owner_id == user.id,
            models.BatMission.status != "completed",
            models.BatMission.is_dismissed.is_(False),
        )
        .group_by(models.BatMission.list_id)
        .all()
    )
    counts = {INBOX: 0}
    for list_id, count in rows:
        counts[INBOX if list_id is None else str(list_id)] = count
    return counts


def find_by_name(db: Session, user: models.BatAccount, name: str) -> Optional[models.BatList]:
    """For Alfred, who is given a name and not an id."""
    name = (name or "").strip()
    if not name:
        return None
    return _live(_owned(db, user)).filter(
        func.lower(models.BatList.name) == name.lower()
    ).first()
