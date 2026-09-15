"""Notes business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models

VALID_SORTS = ("updated", "created", "title")


def create_note(
    db: Session,
    current_user: models.BatAccount,
    title: str = "",
    body: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    is_pinned: bool = False,
) -> models.BatNote:
    note = models.BatNote(
        title=title or "",
        body=body,
        category=category,
        tags=tags,
        is_pinned=is_pinned,
        owner_id=current_user.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def list_notes(
    db: Session,
    current_user: models.BatAccount,
    search: Optional[str] = None,
    sort: str = "updated",
) -> List[models.BatNote]:
    query = db.query(models.BatNote).filter(models.BatNote.owner_id == current_user.id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                models.BatNote.title.ilike(like),
                models.BatNote.body.ilike(like),
            )
        )
    notes = query.all()
    # Pinned first (matches frontend), then the requested sort.
    if sort == "title":
        notes.sort(key=lambda n: ((n.title or "").lower(), n.id))
    elif sort == "created":
        notes.sort(key=lambda n: (n.created_at, n.id), reverse=True)
    else:  # "updated" default
        notes.sort(key=lambda n: (n.updated_at, n.id), reverse=True)
    notes.sort(key=lambda n: (not n.is_pinned,))
    return notes


def get_note(
    db: Session,
    current_user: models.BatAccount,
    note_id: int,
) -> Optional[models.BatNote]:
    return (
        db.query(models.BatNote)
        .filter(models.BatNote.id == note_id, models.BatNote.owner_id == current_user.id)
        .first()
    )


def update_note(
    db: Session,
    current_user: models.BatAccount,
    note_id: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    is_pinned: Optional[bool] = None,
) -> Optional[models.BatNote]:
    note = get_note(db, current_user, note_id)
    if note is None:
        return None
    if title is not None:
        note.title = title
    if body is not None:
        note.body = body
    if category is not None:
        note.category = category
    if tags is not None:
        note.tags = tags
    if is_pinned is not None:
        note.is_pinned = is_pinned
    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


def delete_note(
    db: Session,
    current_user: models.BatAccount,
    note_id: int,
) -> bool:
    note = get_note(db, current_user, note_id)
    if note is None:
        return False
    db.delete(note)
    db.commit()
    return True


def toggle_pin(
    db: Session,
    current_user: models.BatAccount,
    note_id: int,
) -> Optional[models.BatNote]:
    note = get_note(db, current_user, note_id)
    if note is None:
        return None
    return update_note(db, current_user, note_id, is_pinned=not note.is_pinned)
