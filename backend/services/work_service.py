"""The corporate / work track.

Deliberately separate from missions. Work is what pays the salary; missions are
what build the person. Mixing them means the job quietly colours the measure of
the self — so this lives in its own tables, with its own service, and **never
awards Bat Points**.

What it gives you:
  - tasks with a working status (todo / doing / blocked / done) and free-text
    project grouping;
  - a work journal: plain notes, things LEARNED, and period REFLECTIONS;
  - reports over a day / week / month built only from work data, ending in a
    question — because the point isn't the list, it's "was it worth it?".

"Work day" is never declared: any day with work activity on it (a task made,
moved, finished, time logged, or a note written) counts as one. Days you didn't
touch work simply don't appear.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

import models
from services.timezones import day_bounds_utc, local_date, user_tz

STATUSES = models.WORK_STATUSES
NOTE_KINDS = models.WORK_NOTE_KINDS
OPEN_STATUSES = ("todo", "doing", "blocked")
PERIODS = ("today", "week", "month")


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt_hm(minutes: int) -> str:
    h, m = divmod(max(0, int(minutes or 0)), 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


# --- tasks ------------------------------------------------------------------

def list_tasks(db: Session, user: models.BatAccount, *, status: Optional[str] = None,
               project: Optional[str] = None, include_done: bool = False) -> List[models.BatWorkTask]:
    q = db.query(models.BatWorkTask).filter(models.BatWorkTask.owner_id == user.id)
    if status:
        q = q.filter(models.BatWorkTask.status == status)
    elif not include_done:
        q = q.filter(models.BatWorkTask.status != "done")
    if project:
        q = q.filter(models.BatWorkTask.project == project)
    return q.order_by(models.BatWorkTask.created_at.asc()).all()


def get_task(db: Session, user: models.BatAccount, task_id: int) -> Optional[models.BatWorkTask]:
    return (
        db.query(models.BatWorkTask)
        .filter(models.BatWorkTask.owner_id == user.id, models.BatWorkTask.id == task_id)
        .first()
    )


def _norm(title: str) -> str:
    return " ".join((title or "").split()).casefold()


def create_task(db: Session, user: models.BatAccount, *, title: str, detail: Optional[str] = None,
                status: str = "todo", project: Optional[str] = None,
                due_date: Optional[datetime] = None) -> models.BatWorkTask:
    title = (title or "").strip()
    if not title:
        raise ValueError("A work task needs a title.")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}.")
    task = models.BatWorkTask(owner_id=user.id, title=title, detail=detail,
                              status=status, project=project, due_date=due_date)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def find_open_by_title(db: Session, user: models.BatAccount, title: str) -> Optional[models.BatWorkTask]:
    key = _norm(title)
    for t in list_tasks(db, user):
        if _norm(t.title) == key:
            return t
    return None


def update_task(db: Session, user: models.BatAccount, task_id: int, *,
                title: Optional[str] = None, detail: Optional[str] = None,
                status: Optional[str] = None, project: Optional[str] = None,
                due_date: Optional[datetime] = None) -> Optional[models.BatWorkTask]:
    task = get_task(db, user, task_id)
    if task is None:
        return None
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}.")
    if title is not None:
        if not title.strip():
            raise ValueError("A work task needs a title.")
        task.title = title.strip()
    if detail is not None:
        task.detail = detail
    if project is not None:
        task.project = project.strip() or None
    if due_date is not None:
        task.due_date = due_date
    if status is not None:
        task.status = status
        # completed_at tracks the moment it was actually finished, for reports.
        task.completed_at = datetime.now(timezone.utc) if status == "done" else None
    db.commit()
    db.refresh(task)
    return task


def complete_task(db: Session, user: models.BatAccount, task_id: int) -> Optional[models.BatWorkTask]:
    """Finish a work task. Awards NO points — this is the job, not the person."""
    return update_task(db, user, task_id, status="done")


def delete_task(db: Session, user: models.BatAccount, task_id: int) -> bool:
    task = get_task(db, user, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True


# --- journal ----------------------------------------------------------------

def add_note(db: Session, user: models.BatAccount, *, content: str, kind: str = "note",
             work_task_id: Optional[int] = None) -> models.BatWorkNote:
    content = (content or "").strip()
    if not content:
        raise ValueError("A work note needs content.")
    if kind not in NOTE_KINDS:
        raise ValueError(f"kind must be one of {NOTE_KINDS}.")
    if work_task_id is not None and get_task(db, user, work_task_id) is None:
        work_task_id = None
    note = models.BatWorkNote(owner_id=user.id, content=content, kind=kind,
                              work_task_id=work_task_id)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def list_notes(db: Session, user: models.BatAccount, *, kind: Optional[str] = None,
               limit: int = 50) -> List[models.BatWorkNote]:
    q = db.query(models.BatWorkNote).filter(models.BatWorkNote.owner_id == user.id)
    if kind:
        q = q.filter(models.BatWorkNote.kind == kind)
    return q.order_by(models.BatWorkNote.created_at.desc()).limit(limit).all()


# --- reporting --------------------------------------------------------------

def period_range(user: models.BatAccount, period: str, today: date):
    """[start, end) as UTC instants, plus a human label."""
    tz = user_tz(user)
    if period == "today":
        start, end = day_bounds_utc(today, tz)
        return start, end, today.strftime("%A, %-d %B")
    if period == "week":
        first = today - timedelta(days=6)           # last 7 days, inclusive
        start, _ = day_bounds_utc(first, tz)
        _, end = day_bounds_utc(today, tz)
        return start, end, f"{first.strftime('%-d %b')} – {today.strftime('%-d %b')}"
    if period == "month":
        first = today.replace(day=1)
        start, _ = day_bounds_utc(first, tz)
        _, end = day_bounds_utc(today, tz)
        return start, end, today.strftime("%B %Y")
    raise ValueError(f"period must be one of {PERIODS}.")


def build_report(db: Session, user: models.BatAccount, period: str, today: Optional[date] = None) -> Dict:
    """Everything the report needs, from work data only."""
    tz = user_tz(user)
    today = today or datetime.now(tz).date()
    start, end, label = period_range(user, period, today)
    ns, ne = _naive(start), _naive(end)

    completed = (
        db.query(models.BatWorkTask)
        .filter(models.BatWorkTask.owner_id == user.id,
                models.BatWorkTask.completed_at.isnot(None),
                models.BatWorkTask.completed_at >= ns,
                models.BatWorkTask.completed_at < ne)
        .order_by(models.BatWorkTask.completed_at.asc())
        .all()
    )
    open_tasks = list_tasks(db, user)
    by_status = {s: [t for t in open_tasks if t.status == s] for s in OPEN_STATUSES}

    focus_rows = (
        db.query(models.BatFocus)
        .filter(models.BatFocus.owner_id == user.id,
                models.BatFocus.work_task_id.isnot(None),
                models.BatFocus.start_time >= ns,
                models.BatFocus.start_time < ne)
        .all()
    )
    minutes = sum((f.duration_minutes or 0) for f in focus_rows)

    notes = (
        db.query(models.BatWorkNote)
        .filter(models.BatWorkNote.owner_id == user.id,
                models.BatWorkNote.created_at >= ns,
                models.BatWorkNote.created_at < ne)
        .order_by(models.BatWorkNote.created_at.asc())
        .all()
    )
    learnings = [n for n in notes if n.kind == "learning"]
    reflections = [n for n in notes if n.kind == "reflection"]
    plain_notes = [n for n in notes if n.kind == "note"]

    # A day counts as a work day if anything moved on it — never declared.
    created_in = (
        db.query(models.BatWorkTask)
        .filter(models.BatWorkTask.owner_id == user.id,
                models.BatWorkTask.created_at >= ns, models.BatWorkTask.created_at < ne)
        .all()
    )
    days = set()
    for t in completed:
        days.add(local_date(t.completed_at, tz))
    for t in created_in:
        days.add(local_date(t.created_at, tz))
    for f in focus_rows:
        days.add(local_date(f.start_time, tz))
    for n in notes:
        days.add(local_date(n.created_at, tz))

    return {
        "period": period, "label": label, "today": today,
        "completed": completed,
        "open_by_status": by_status,
        "open_total": len(open_tasks),
        "minutes": minutes,
        "work_days": sorted(days),
        "learnings": learnings,
        "reflections": reflections,
        "notes": plain_notes,
    }


REFLECTION_PROMPTS = {
    "today": "Was today worth the hours, sir — or spent on someone else's priorities?",
    "week": "Looking at the week: what moved you forward, and what was merely motion?",
    "month": "A month of it, sir. Worth the salary — and worth your time? Tell me and I'll keep the note.",
}


def render_report(user: models.BatAccount, data: Dict) -> str:
    """The work report in Alfred's voice. Ends with a question, by design: the
    point of this is the reflection, not the list."""
    addr = (getattr(user, "alfred_address", None) or "").strip() or user.username
    heading = {"today": "Work — today", "week": "Work — last 7 days",
               "month": "Work — this month"}[data["period"]]
    lines = [f"{heading} ({data['label']}), {addr}.", ""]

    days = data["work_days"]
    bits = []
    if days:
        bits.append(f"{len(days)} working day{'s' if len(days) != 1 else ''}")
    if data["minutes"]:
        bits.append(f"{_fmt_hm(data['minutes'])} logged")
    bits.append(f"{len(data['completed'])} finished")
    lines.append(" · ".join(bits))

    if data["completed"]:
        lines.append("")
        lines.append("Finished:")
        for t in data["completed"][:10]:
            proj = f" [{t.project}]" if t.project else ""
            lines.append(f"  • {t.title}{proj}")

    doing = data["open_by_status"]["doing"]
    blocked = data["open_by_status"]["blocked"]
    todo = data["open_by_status"]["todo"]
    if doing:
        lines.append("")
        lines.append("In hand:")
        for t in doing[:6]:
            lines.append(f"  • {t.title}")
    if blocked:
        lines.append("")
        lines.append("Blocked — these are the ones worth raising:")
        for t in blocked[:6]:
            lines.append(f"  • {t.title}")
    if todo:
        lines.append("")
        lines.append(f"Waiting: {len(todo)} not yet started.")

    if data["learnings"]:
        lines.append("")
        lines.append("Learned:")
        for n in data["learnings"][:6]:
            lines.append(f"  • {n.content}")

    if data["period"] == "month" and data["reflections"]:
        lines.append("")
        lines.append("Your reflections this month:")
        for n in data["reflections"][:5]:
            lines.append(f"  • {n.content}")

    if not days and not data["completed"] and not data["open_total"]:
        lines.append("")
        lines.append("Nothing on the work ledger for this period — which is an answer in itself.")

    lines.append("")
    lines.append(REFLECTION_PROMPTS[data["period"]])
    return "\n".join(lines).strip()
