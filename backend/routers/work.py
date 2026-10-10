"""The corporate / work track over HTTP.

Thin handlers over `services.work_service` — the same service Alfred's tools
call, so the web view and the Telegram conversation can never drift apart or
disagree about what is on the work ledger.

Two things are load-bearing here:

1. **The switch.** Every route except the status/toggle pair depends on
   `require_work_enabled`. With the track off, the whole surface answers 409 and
   the UI hides it — nothing half-shown, nothing half-working.
2. **No points, ever.** Nothing in this module touches `points`, `bat_level` or
   the logs that feed them. Work is the job; Bat Points measure the person.
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from schemas.work import (
    WorkNoteCreate,
    WorkNoteResponse,
    WorkProfileUpdate,
    WorkStatusResponse,
    WorkTaskCreate,
    WorkTaskResponse,
    WorkTaskUpdate,
    WorkToggle,
)
from services import work_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/work", tags=["work"])

WORK_OFF_DETAIL = "The work track is switched off. Turn it on to use it."


def require_work_enabled(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
) -> models.BatAccount:
    if not work_service.is_enabled(db, current_user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=WORK_OFF_DETAIL)
    return current_user


def _status_payload(db: Session, user: models.BatAccount) -> dict:
    st = work_service.profile_status(db, user)
    return {
        "enabled": work_service.is_enabled(db, user),
        "chosen": getattr(user, "work_enabled", None) is not None,
        "has_data": work_service.has_work_data(db, user),
        "configured": st["configured"],
        "missing_essential": st["missing_essential"],
        "next_question": st["next_question"],
        "profile": st["profile"],
        "statuses": list(models.WORK_STATUSES),
        "note_kinds": list(models.WORK_NOTE_KINDS),
    }


# --- the switch -------------------------------------------------------------
# Deliberately always reachable: this is how the UI learns whether to render the
# work side at all, and how the track gets switched back on once it is off.


@router.get("/status", response_model=WorkStatusResponse)
def work_status(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return _status_payload(db, current_user)


@router.put("/status", response_model=WorkStatusResponse)
@limiter.limit("30/minute")
def set_work_status(
    request: Request,
    payload: WorkToggle,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """Turn the work track on or off. Keeps all work data either way."""
    work_service.set_enabled(db, current_user, payload.enabled)
    logger.info("work_track_toggled", user_id=current_user.id, enabled=payload.enabled)
    return _status_payload(db, current_user)


# --- profile ----------------------------------------------------------------


@router.put("/profile", response_model=WorkStatusResponse)
@limiter.limit("30/minute")
def update_profile(
    request: Request,
    payload: WorkProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    try:
        work_service.upsert_profile(db, current_user,
                                    **payload.model_dump(exclude_unset=True))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _status_payload(db, current_user)


# --- tasks ------------------------------------------------------------------


@router.get("/tasks", response_model=List[WorkTaskResponse])
def list_tasks(
    task_status: Optional[str] = None,
    project: Optional[str] = None,
    include_done: bool = False,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    if task_status is not None and task_status not in models.WORK_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(models.WORK_STATUSES)}",
        )
    return work_service.list_tasks(db, current_user, status=task_status,
                                   project=project, include_done=include_done)


@router.post("/tasks", response_model=WorkTaskResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def create_task(
    request: Request,
    payload: WorkTaskCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    try:
        return work_service.create_task(
            db, current_user, title=payload.title, detail=payload.detail,
            status=payload.status, project=payload.project, due_date=payload.due_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.put("/tasks/{task_id}", response_model=WorkTaskResponse)
@limiter.limit("60/minute")
def update_task(
    request: Request,
    task_id: int,
    payload: WorkTaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    try:
        task = work_service.update_task(db, current_user, task_id,
                                        **payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work task not found")
    return task


@router.post("/tasks/{task_id}/complete", response_model=WorkTaskResponse)
@limiter.limit("60/minute")
def complete_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    """Finish a work task. Awards no Bat Points, by design."""
    task = work_service.complete_task(db, current_user, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work task not found")
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    if not work_service.delete_task(db, current_user, task_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work task not found")
    return None


# --- journal ----------------------------------------------------------------


@router.get("/notes", response_model=List[WorkNoteResponse])
def list_notes(
    kind: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    if kind is not None and kind not in models.WORK_NOTE_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid kind. Must be one of: {', '.join(models.WORK_NOTE_KINDS)}",
        )
    return work_service.list_notes(db, current_user, kind=kind,
                                   limit=max(1, min(limit, 200)))


@router.post("/notes", response_model=WorkNoteResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def create_note(
    request: Request,
    payload: WorkNoteCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    try:
        return work_service.add_note(db, current_user, content=payload.content,
                                     kind=payload.kind, work_task_id=payload.work_task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


# --- reports ----------------------------------------------------------------


@router.get("/report")
def work_report(
    period: str = "today",
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(require_work_enabled),
):
    """The same report Alfred gives, as numbers plus his rendered text.

    The reflection question is part of the report on purpose — the point of this
    is the reflection, not the list.
    """
    if period not in work_service.PERIODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid period. Must be one of: {', '.join(work_service.PERIODS)}",
        )
    data = work_service.build_report(db, current_user, period)
    return {
        "period": period,
        "label": data["label"],
        "minutes": data["minutes"],
        "expected_minutes": data["expected_minutes"],
        "work_days": len(data["work_days"]),
        "expected_days": data["expected_days"],
        "completed": [WorkTaskResponse.model_validate(t).model_dump(mode="json")
                      for t in data["completed"]],
        "open_counts": {s: len(v) for s, v in data["open_by_status"].items()},
        "open_total": data["open_total"],
        "learnings": [WorkNoteResponse.model_validate(n).model_dump(mode="json")
                      for n in data["learnings"]],
        "reflections": [WorkNoteResponse.model_validate(n).model_dump(mode="json")
                        for n in data["reflections"]],
        "text": work_service.render_report(current_user, data),
    }
