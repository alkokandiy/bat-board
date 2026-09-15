"""Focus-stats business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.

_completed_sessions_query / _compute_focus_stats moved verbatim out of
main.py (not duplicated); get_focus_stats is the thin wrapper Alfred
will call.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import models


def _completed_sessions_query(db: Session, current_user: models.BatAccount):
    return db.query(models.BatFocus).filter(
        models.BatFocus.owner_id == current_user.id,
        models.BatFocus.end_time.isnot(None),
        models.BatFocus.duration_minutes > 0,
    )


def _compute_focus_stats(db: Session, current_user: models.BatAccount, period: str) -> dict:
    today = datetime.now(timezone.utc).date()

    if period == "day":
        range_start = today
        range_end = today
    elif period == "week":
        range_start = today - timedelta(days=today.weekday())
        range_end = range_start + timedelta(days=6)
    elif period == "month":
        range_start = today.replace(day=1)
        range_end = (range_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    elif period == "year":
        range_start = today.replace(month=1, day=1)
        range_end = today.replace(month=12, day=31)
    else:  # all
        range_start = None
        range_end = None

    q = _completed_sessions_query(db, current_user)
    if range_start:
        q = q.filter(models.BatFocus.end_time >= datetime(range_start.year, range_start.month, range_start.day))
    if range_end:
        q = q.filter(
            models.BatFocus.end_time
            < datetime(range_end.year, range_end.month, range_end.day) + timedelta(days=1)
        )
    sessions = q.all()

    total_minutes = 0
    total_sessions = len(sessions)
    mission_agg = defaultdict(lambda: {"minutes": 0, "sessions": 0})
    habit_agg = defaultdict(lambda: {"minutes": 0, "sessions": 0})
    unassigned = {"minutes": 0, "sessions": 0}
    heatmap = defaultdict(int)
    days_with_sessions = set()

    for s in sessions:
        total_minutes += s.duration_minutes
        d = s.end_time.date()
        heatmap[d] += s.duration_minutes
        days_with_sessions.add(d)
        if s.mission_id is not None:
            mission_agg[s.mission_id]["minutes"] += s.duration_minutes
            mission_agg[s.mission_id]["sessions"] += 1
        elif s.habit_id is not None:
            habit_agg[s.habit_id]["minutes"] += s.duration_minutes
            habit_agg[s.habit_id]["sessions"] += 1
        else:
            unassigned["minutes"] += s.duration_minutes
            unassigned["sessions"] += 1

    breakdown = []
    if mission_agg:
        mission_rows = db.query(models.BatMission).filter(
            models.BatMission.id.in_(list(mission_agg.keys())),
            models.BatMission.owner_id == current_user.id,
        ).all()
        mission_names = {m.id: m.title for m in mission_rows}
        for mid, agg in mission_agg.items():
            breakdown.append({
                "type": "mission",
                "id": mid,
                "name": mission_names.get(mid, f"Mission #{mid}"),
                "minutes": agg["minutes"],
                "sessions": agg["sessions"],
                "percent": round(agg["minutes"] / total_minutes * 100, 1) if total_minutes else 0.0,
            })
    if habit_agg:
        habit_rows = db.query(models.BatHabit).filter(
            models.BatHabit.id.in_(list(habit_agg.keys())),
            models.BatHabit.owner_id == current_user.id,
        ).all()
        habit_names = {h.id: h.name for h in habit_rows}
        for hid, agg in habit_agg.items():
            breakdown.append({
                "type": "habit",
                "id": hid,
                "name": habit_names.get(hid, f"Habit #{hid}"),
                "minutes": agg["minutes"],
                "sessions": agg["sessions"],
                "percent": round(agg["minutes"] / total_minutes * 100, 1) if total_minutes else 0.0,
            })
    if unassigned["sessions"] > 0:
        breakdown.append({
            "type": "none",
            "id": None,
            "name": "Unassigned",
            "minutes": unassigned["minutes"],
            "sessions": unassigned["sessions"],
            "percent": round(unassigned["minutes"] / total_minutes * 100, 1) if total_minutes else 0.0,
        })
    breakdown.sort(key=lambda b: b["minutes"], reverse=True)

    streak = 0
    d = today
    while d in days_with_sessions:
        streak += 1
        d -= timedelta(days=1)

    daily_heatmap = [
        {"date": (today - timedelta(days=i)).isoformat(), "minutes": heatmap.get(today - timedelta(days=i), 0)}
        for i in range(34, -1, -1)
    ]

    return {
        "period": period,
        "range_start": range_start.isoformat() if range_start else None,
        "range_end": range_end.isoformat() if range_end else None,
        "total_minutes": total_minutes,
        "total_sessions": total_sessions,
        "current_streak_days": streak,
        "breakdown": breakdown,
        "daily_heatmap": daily_heatmap,
    }


def get_focus_stats(
    db: Session,
    current_user: models.BatAccount,
    period: str = "week",
) -> dict:
    """Thin wrapper Alfred's tool layer will call directly."""
    return _compute_focus_stats(db, current_user, period)
