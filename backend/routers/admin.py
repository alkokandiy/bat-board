"""Admin endpoints: list users, see counts, disable/enable, delete.

Entirely additive and opt-in. Access is gated by the `ADMIN_USERNAMES` env var
(empty by default → no admins → every endpoint here returns 403). Nothing in
this module touches existing user flows; it only adds routes under /api/admin.

Destructive actions are guarded: an admin cannot disable or delete themselves,
and cannot delete another admin. Deleting a user cascades (SQLAlchemy
delete-orphan) to all their data — missions, habits, notes, Alfred chats/memory,
Telegram link, briefings and reminders — in one transaction.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from config import get_settings
from dependencies import get_current_active_user, get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin_names() -> set:
    """Configured admin usernames, case-folded.

    Folding matters in both directions: it stops a case variant of the
    configured name being claimable, and stops an owner configured as "Thomas"
    silently having no powers because they registered as "thomas".
    """
    raw = get_settings().admin_usernames or ""
    return {n.strip().casefold() for n in raw.split(",") if n.strip()}


def is_admin(user: models.BatAccount) -> bool:
    return (user.username or "").casefold() in _admin_names()


def is_reserved_admin_name(name: str, actor: models.BatAccount = None) -> bool:
    """True if taking this username would hand someone admin rights.

    Admin authority is keyed on the username, and usernames are chosen freely
    at registration and changeable afterwards — so an admin name that nobody
    currently holds (fresh deploy, a typo in ADMIN_USERNAMES, the owner having
    renamed) is a claimable escalation. Registration into an admin name is
    refused outright; renaming into one is allowed only for an account that is
    already an admin, so a legitimate admin can still adjust their own name.
    """
    if (name or "").strip().casefold() not in _admin_names():
        return False
    return actor is None or not is_admin(actor)


def require_admin(current_user: models.BatAccount = Depends(get_current_active_user)) -> models.BatAccount:
    if not is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user


@router.get("/me")
def admin_me(current_user: models.BatAccount = Depends(get_current_active_user)):
    """Whether the caller is an admin. Non-admins get a plain false, not a 403,
    so the frontend can decide whether to render the admin panel."""
    return {"is_admin": is_admin(current_user)}


def _counts_by_owner(db: Session, model) -> dict:
    rows = db.query(model.owner_id, func.count(model.id)).group_by(model.owner_id).all()
    return {owner_id: n for owner_id, n in rows}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _admin: models.BatAccount = Depends(require_admin)):
    """All users with per-user counts and setup status. Read-only."""
    users = db.query(models.BatAccount).order_by(models.BatAccount.created_at.asc()).all()

    missions = _counts_by_owner(db, models.BatMission)
    habits = _counts_by_owner(db, models.BatHabit)
    notes = _counts_by_owner(db, models.BatNote)
    focus = _counts_by_owner(db, models.BatFocus)

    # Telegram-linked owners (any live PAT with a chat id)
    linked = {
        oid for (oid,) in db.query(models.BatPersonalAccessToken.owner_id)
        .filter(models.BatPersonalAccessToken.revoked.is_(False),
                models.BatPersonalAccessToken.telegram_chat_id.isnot(None))
        .distinct()
    }
    with_provider = {
        oid for (oid,) in db.query(models.BatAIProviderConfig.owner_id).distinct()
    }

    admins = _admin_names()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "username": u.username,
            "is_active": u.is_active,
            "is_admin": (u.username or "").casefold() in admins,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "points": u.points,
            "bat_level": u.bat_level,
            "timezone": u.timezone,
            "telegram_linked": u.id in linked,
            "provider_configured": u.id in with_provider,
            "counts": {
                "missions": missions.get(u.id, 0),
                "habits": habits.get(u.id, 0),
                "notes": notes.get(u.id, 0),
                "focus_sessions": focus.get(u.id, 0),
            },
        })

    return {
        "total_users": len(users),
        "active_users": sum(1 for u in users if u.is_active),
        "users": out,
    }


def _get_target(db: Session, user_id: int) -> models.BatAccount:
    target = db.get(models.BatAccount, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return target


@router.post("/users/{user_id}/disable")
def disable_user(user_id: int, db: Session = Depends(get_db),
                 admin: models.BatAccount = Depends(require_admin)):
    target = _get_target(db, user_id)
    if target.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't disable yourself.")
    target.is_active = False
    db.commit()
    logger.info("admin_user_disabled", admin=admin.username, target=target.username)
    return {"ok": True, "id": target.id, "is_active": target.is_active}


@router.post("/users/{user_id}/enable")
def enable_user(user_id: int, db: Session = Depends(get_db),
                admin: models.BatAccount = Depends(require_admin)):
    target = _get_target(db, user_id)
    target.is_active = True
    db.commit()
    logger.info("admin_user_enabled", admin=admin.username, target=target.username)
    return {"ok": True, "id": target.id, "is_active": target.is_active}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db),
                admin: models.BatAccount = Depends(require_admin)):
    target = _get_target(db, user_id)
    if target.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't delete yourself.")
    if is_admin(target):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't delete another admin.")
    username = target.username
    db.delete(target)  # cascades to all of the user's data
    db.commit()
    logger.info("admin_user_deleted", admin=admin.username, target=username)
    return {"ok": True, "deleted": username}
