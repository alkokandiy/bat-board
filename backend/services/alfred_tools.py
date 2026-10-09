"""Alfred tool schemas + executor.

Schemas wrap existing service functions. The LLM NEVER selects whose data
it touches: no schema exposes owner_id/user_id/current_user — the backend
injects the already-resolved authenticated user server-side.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

import models
from services import (
    briefing_service,
    calendar_service,
    countdown_service,
    focus_service,
    habit_service,
    logs_service,
    mission_service,
    notes_service,
    profile_service,
    stats_service,
    telegram_service,
)

FOCUS_NO_LIVE_SYNC_NOTE = (
    "The session is recorded in the database, but there is NO live sync to "
    "an open browser tab — the browser will not show it, even on refresh."
)


MEMORY_TAG = "alfred-memory"


def _has_memory_tag(note) -> bool:
    return any(
        t.strip().lower() == MEMORY_TAG
        for t in (note.tags or "").split(",")
        if t.strip()
    )


def _memory_notes(db: Session, current_user: models.BatAccount):
    """Alfred's private memory notes only — never the user's own notes."""
    return [n for n in notes_service.list_notes(db, current_user) if _has_memory_tag(n)]


def _memory_brief(note) -> str:
    """One-line description: first non-empty body line, truncated."""
    for line in (note.body or "").splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


def _iso(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _mission_dict(m):
    return {
        "id": m.id, "title": m.title, "description": m.description,
        "status": m.status, "priority": m.priority,
        "due_date": _iso(m.due_date), "tags": m.tags,
        "is_pinned": m.is_pinned, "completed_at": _iso(m.completed_at),
    }


def _norm_title(t) -> str:
    return " ".join((t or "").split()).casefold()


def _open_mission_titles(db, user) -> dict:
    """Normalized title -> mission, for the user's open (non-completed,
    non-dismissed) missions. Used to skip duplicate creates."""
    rows = (
        db.query(models.BatMission)
        .filter(models.BatMission.owner_id == user.id,
                models.BatMission.status != "completed",
                models.BatMission.is_dismissed.is_(False))
        .all()
    )
    return {_norm_title(m.title): m for m in rows}


def _create_one_mission(db, user, spec: dict):
    """Create a single mission from a spec dict (shared by the single and
    batch tools). Caller handles duplicate checking."""
    return mission_service.create_mission(
        db, user, title=spec["title"], description=spec.get("description"),
        due_date=_parse_dt(spec.get("due_date"), "due_date") if spec.get("due_date") else None,
        priority=spec.get("priority") or "medium", tags=spec.get("tags"),
        location=spec.get("location"), notes=spec.get("notes"),
        subtasks=spec.get("subtasks"),
        is_pinned=bool(spec.get("is_pinned")) if spec.get("is_pinned") is not None else False)


def _habit_dict(h):
    return {
        "id": h.id, "name": h.name, "description": h.description,
        "frequency": h.frequency, "streak": h.streak,
        "last_completed": _iso(h.last_completed),
    }


def _event_dict(e):
    return {
        "id": e.id, "title": e.title, "description": e.description,
        "start_time": _iso(e.start_time), "end_time": _iso(e.end_time),
        "mission_id": e.mission_id,
    }


def _note_dict(n):
    return {
        "id": n.id, "title": n.title, "body": n.body,
        "category": n.category, "is_pinned": n.is_pinned,
        "created_at": _iso(n.created_at), "updated_at": _iso(n.updated_at),
    }


def _countdown_dict(c):
    return {
        "id": c.id, "title": c.title, "target_date": _iso(c.target_date),
        "days_remaining": countdown_service.days_remaining_for(c.target_date),
    }


def _session_dict(s):
    return {
        "id": s.id, "start_time": _iso(s.start_time),
        "end_time": _iso(s.end_time), "duration_minutes": s.duration_minutes,
        "mission_id": s.mission_id, "habit_id": s.habit_id,
        "discarded": getattr(s, "discarded", False),
    }


def _active_session_dict(s):
    from datetime import datetime, timezone
    start = s.start_time if s.start_time.tzinfo else s.start_time.replace(tzinfo=timezone.utc)
    elapsed = max(0, int((datetime.now(timezone.utc) - start).total_seconds() // 60))
    d = {"id": s.id, "elapsed_minutes": elapsed, "mission_id": s.mission_id,
         "habit_id": s.habit_id, "planned_minutes": s.planned_minutes}
    if s.planned_minutes:
        d["remaining_minutes"] = max(0, s.planned_minutes - elapsed)
    return d


def _briefing_dict(b):
    return {
        "kind": b.kind, "enabled": b.enabled, "send_time": b.send_time,
        "includes": {
            "missions": b.include_missions, "habits": b.include_habits,
            "events": b.include_events, "focus": b.include_focus, "news": b.include_news,
        },
        "news_topics": b.news_topics,
    }


def _reminder_dict(r):
    d = {
        "id": r.id, "message": r.message, "enabled": r.enabled,
        "recurrence": r.recurrence, "send_time": r.send_time,
        "ends_on": getattr(r, "ends_on", None) or "no end date",
    }
    if r.recurrence == "weekly":
        d["weekdays"] = briefing_service.weekdays_label(r.weekdays)
    elif r.recurrence == "monthly":
        d["day_of_month"] = r.day_of_month
    elif r.recurrence == "once":
        d["run_date"] = r.run_date
    return d


def _parse_dt(value, field_name):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"Invalid datetime for {field_name}: {value!r}")


READ_TOOLS = [
    {"name": "list_missions", "description": "List the user's missions AND get exact counts. Returns `missions` (filtered by `status`, default pending/active) plus `counts` {pending, completed, dismissed, total} computed server-side. For ANY 'how many missions' question, report the number straight from `counts` — never tally the list yourself. The default pending count matches the dashboard's Active Missions.",
     "parameters": {"type": "object", "properties": {
         "due_date": {"type": "string", "description": "ISO date to filter missions due on that day."},
         "status": {"type": "string", "enum": ["pending", "completed", "all"], "description": "Which missions to return (default pending). `counts` always covers everything regardless."},
     }}},
    {"name": "list_habits", "description": "List the user's habits with streaks.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "list_upcoming_events", "description": "List calendar events ordered by start time.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "list_notes", "description": "List notes. Optional substring search over title/body and sort.",
     "parameters": {"type": "object", "properties": {
         "search": {"type": "string", "description": "Substring to match in title or body."},
         "sort": {"type": "string", "enum": ["updated", "created", "title"]},
     }}},
    {"name": "list_countdowns", "description": "List countdowns, soonest first, with days_remaining.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "list_recent_logs", "description": "List recent activity log entries.",
     "parameters": {"type": "object", "properties": {
         "limit": {"type": "integer", "description": "Max entries (default 50)."},
         "start_date": {"type": "string", "description": "ISO datetime lower bound."},
         "end_date": {"type": "string", "description": "ISO datetime upper bound."},
     }}},
    {"name": "get_active_focus_session", "description": "Check whether a focus session is currently running, with elapsed and (for timed sessions) remaining minutes. Use for 'am I focusing?', 'how long left?'.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_focus_stats", "description": "Focus statistics for a period.",
     "parameters": {"type": "object", "properties": {
         "period": {"type": "string", "enum": ["day", "week", "month", "year", "all"]},
     }}},
    {"name": "get_profile", "description": "The user's profile: points and bat level.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "alfred_list_memory_topics", "description": "List Alfred's private memory topics (titles + one-line descriptions only). Call first to see what is already known before reading further or writing.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "alfred_recall", "description": "Search Alfred's private memory notes by title/body match. Returns matching bodies. Never includes the user's own notes.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Substring to match in memory title or body."},
     }, "required": ["query"]}},
    {"name": "show_focus_chart", "description": "Send the user an image chart of their focus time over the last 7 days (bars per day, total, streak). Use when they ask to see/visualise their focus or a weekly focus summary.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_briefings", "description": "Show the user's morning/night briefing settings: whether each is on, its time, which sections it includes, and news topics. Use when they ask about their briefings or before editing one.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "list_reminders", "description": "List the user's reminders (message, schedule, enabled). Use before editing or deleting one, or when they ask what reminders are set.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_nudge_settings", "description": "Show how you check in on the user unprompted: whether it's on, their quiet hours, and the daily limit. Read before changing it.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "show_daily_brief", "description": "Send the user a daily brief card (image): missions due today, habits still to do, next calendar event and countdown, points and level. Use for 'my day', 'daily brief', 'what's on today', 'morning summary'.",
     "parameters": {"type": "object", "properties": {}}},
]

WRITE_TOOLS = [
    {"name": "create_mission", "description": "Create a new mission. Ask first for priority and due date when missing; other fields optional.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"}, "description": {"type": "string"},
         "due_date": {"type": "string", "description": "ISO datetime."},
         "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
         "tags": {"type": "string", "description": "Comma-separated tags."},
         "location": {"type": "string"}, "notes": {"type": "string", "description": "Mission intel."},
         "subtasks": {"type": "string", "description": "JSON array of {title, done}."},
         "is_pinned": {"type": "boolean"},
     }, "required": ["title"]}},
    {"name": "create_missions", "description": "Create SEVERAL missions at once in a single call. ALWAYS use this (not repeated create_mission) when the user lists more than one mission in a message. Duplicates of existing or repeated titles are skipped automatically. Don't ask about each one — apply sensible defaults (priority medium, no due date unless stated) and report what you added.",
     "parameters": {"type": "object", "properties": {
         "missions": {"type": "array", "description": "The missions to create.", "items": {
             "type": "object", "properties": {
                 "title": {"type": "string"},
                 "description": {"type": "string"},
                 "due_date": {"type": "string", "description": "ISO datetime."},
                 "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                 "tags": {"type": "string", "description": "Comma-separated tags."},
                 "location": {"type": "string"}, "notes": {"type": "string"},
             }, "required": ["title"]}},
     }, "required": ["missions"]}},
    {"name": "complete_mission", "description": "Mark a mission completed (awards points).",
     "parameters": {"type": "object", "properties": {
         "mission_id": {"type": "integer"},
     }, "required": ["mission_id"]}},
    {"name": "update_mission", "description": "Update an existing mission's fields (due date, priority, title, etc).",
     "parameters": {"type": "object", "properties": {
         "mission_id": {"type": "integer"},
         "title": {"type": "string"}, "description": {"type": "string"},
         "due_date": {"type": "string", "description": "ISO datetime."},
         "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
         "tags": {"type": "string"}, "location": {"type": "string"},
         "notes": {"type": "string"}, "subtasks": {"type": "string"},
         "is_pinned": {"type": "boolean"}, "is_dismissed": {"type": "boolean"},
     }, "required": ["mission_id"]}},
    {"name": "create_habit", "description": "Create a new habit.",
     "parameters": {"type": "object", "properties": {
         "name": {"type": "string"}, "description": {"type": "string"},
         "frequency": {"type": "string", "enum": ["daily", "weekly", "monthly"]},
     }, "required": ["name"]}},
    {"name": "check_in_habit", "description": "Check in to a habit (streak + points).",
     "parameters": {"type": "object", "properties": {
         "habit_id": {"type": "integer"},
     }, "required": ["habit_id"]}},
    {"name": "update_habit", "description": "Update an existing habit's name, description, or frequency.",
     "parameters": {"type": "object", "properties": {
         "habit_id": {"type": "integer"},
         "name": {"type": "string"}, "description": {"type": "string"},
         "frequency": {"type": "string", "enum": ["daily", "weekly", "monthly"]},
         "target_date": {"type": "string", "description": "ISO datetime."},
     }, "required": ["habit_id"]}},
    {"name": "create_event", "description": "Create a calendar event. Ask first for start time when missing.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"}, "start_time": {"type": "string", "description": "ISO datetime."},
         "description": {"type": "string"}, "end_time": {"type": "string", "description": "ISO datetime."},
         "color": {"type": "string"}, "mission_id": {"type": "integer", "description": "Link to a mission."},
     }, "required": ["title", "start_time"]}},
    {"name": "update_event", "description": "Update an existing calendar event.",
     "parameters": {"type": "object", "properties": {
         "event_id": {"type": "integer"},
         "title": {"type": "string"}, "description": {"type": "string"},
         "start_time": {"type": "string", "description": "ISO datetime."},
         "end_time": {"type": "string", "description": "ISO datetime."},
         "color": {"type": "string"}, "mission_id": {"type": "integer"},
     }, "required": ["event_id"]}},
    {"name": "create_note", "description": "Create a note.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"}, "body": {"type": "string"},
         "category": {"type": "string"}, "tags": {"type": "string", "description": "Comma-separated."},
     }, "required": ["title"]}},
    {"name": "update_note", "description": "Partially update a note.",
     "parameters": {"type": "object", "properties": {
         "note_id": {"type": "integer"}, "title": {"type": "string"},
         "body": {"type": "string"}, "category": {"type": "string"},
         "tags": {"type": "string", "description": "Comma-separated."},
         "is_pinned": {"type": "boolean"},
     }, "required": ["note_id"]}},
    {"name": "toggle_pin", "description": "Toggle a note's pinned state.",
     "parameters": {"type": "object", "properties": {
         "note_id": {"type": "integer"},
     }, "required": ["note_id"]}},
    {"name": "alfred_remember", "description": "Write or update one of Alfred's private memory notes (upsert by exact title). One note per topic — update the existing topic note rather than creating near-duplicates. Only store what the user actually stated, never inferences.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string", "description": "Clear, specific topic title."},
         "content": {"type": "string", "description": "The stated fact, verbatim-ish."},
     }, "required": ["title", "content"]}},
    {"name": "create_countdown", "description": "Create a countdown to a target date.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"}, "target_date": {"type": "string", "description": "ISO datetime."},
     }, "required": ["title", "target_date"]}},
    {"name": "update_countdown", "description": "Update an existing countdown's title or target date.",
     "parameters": {"type": "object", "properties": {
         "countdown_id": {"type": "integer"},
         "title": {"type": "string"}, "target_date": {"type": "string", "description": "ISO datetime."},
     }, "required": ["countdown_id"]}},
    {"name": "set_briefing", "description": "Create or update a morning or night briefing that Alfred sends over Telegram on a schedule. Ask the user which kind, what time, and what to include before setting it. Briefings require a linked Telegram. Only pass fields the user specified; omitted toggles are left unchanged. To include news, set include_news true AND provide news_topics.",
     "parameters": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["morning", "night"]},
         "enabled": {"type": "boolean"},
         "send_time": {"type": "string", "description": "HH:MM, 24-hour, in the user's timezone."},
         "include_missions": {"type": "boolean"}, "include_habits": {"type": "boolean"},
         "include_events": {"type": "boolean"}, "include_focus": {"type": "boolean"},
         "include_news": {"type": "boolean"},
         "news_topics": {"type": "string", "description": "Comma-separated topics, e.g. 'AI, cybersecurity, defense'. Required if include_news."},
     }, "required": ["kind"]}},
    {"name": "set_nudge_settings", "description": "Change how you check in unprompted. Use when they say things like 'check in on me less', 'stop messaging me', 'don't message me after 9', 'you can nudge me more'. Only pass what they asked to change.",
     "parameters": {"type": "object", "properties": {
         "enabled": {"type": "boolean", "description": "False stops all unprompted check-ins."},
         "quiet_start": {"type": "string", "description": "HH:MM local — start of quiet hours (no messages)."},
         "quiet_end": {"type": "string", "description": "HH:MM local — end of quiet hours."},
         "per_day": {"type": "integer", "description": "Max unprompted check-ins per day (1-10)."},
     }}},
    {"name": "create_reminder", "description": "Create a reminder Alfred pushes over Telegram on a schedule (e.g. 'take medicine' every morning, 'call mum' every Sunday). Ask for the time and how often it should repeat when missing. Requires a linked Telegram.",
     "parameters": {"type": "object", "properties": {
         "message": {"type": "string", "description": "What to remind the user about."},
         "recurrence": {"type": "string", "enum": ["once", "daily", "weekly", "monthly"]},
         "send_time": {"type": "string", "description": "HH:MM, 24-hour, user's timezone."},
         "weekdays": {"type": "string", "description": "weekly only: comma-separated, e.g. 'Mon,Thu' or '0,3' (Mon=0)."},
         "day_of_month": {"type": "integer", "description": "monthly only: 1-31 (clamped to month end)."},
         "run_date": {"type": "string", "description": "once only: YYYY-MM-DD."},
         "ends_on": {"type": "string", "description": "Optional last day, YYYY-MM-DD, inclusive. Use whenever the user bounds it in time ('for one month', 'for two weeks', 'until 1 December') — work out the date from today. Omit for an open-ended reminder."},
     }, "required": ["message", "recurrence", "send_time"]}},
    {"name": "update_reminder", "description": "Update an existing reminder (message, time, recurrence, enable/disable). Only pass fields to change.",
     "parameters": {"type": "object", "properties": {
         "reminder_id": {"type": "integer"},
         "message": {"type": "string"}, "enabled": {"type": "boolean"},
         "recurrence": {"type": "string", "enum": ["once", "daily", "weekly", "monthly"]},
         "send_time": {"type": "string", "description": "HH:MM."},
         "weekdays": {"type": "string"}, "day_of_month": {"type": "integer"},
         "run_date": {"type": "string", "description": "YYYY-MM-DD."},
         "ends_on": {"type": "string", "description": "New last day (YYYY-MM-DD), or 'none' to make it open-ended again."},
     }, "required": ["reminder_id"]}},
    {"name": "start_focus_session", "description": "Start a focus session, optionally timed. Set `planned_minutes` (5-180) for a timer that auto-ends after that long and pings the user on Telegram when complete — prefer this. If the user names no duration, default to 25 and say so. Optionally link a mission or habit. Only one session runs at a time.",
     "parameters": {"type": "object", "properties": {
         "mission_id": {"type": "integer"}, "habit_id": {"type": "integer"},
         "planned_minutes": {"type": "integer", "description": "Timer length in minutes (5-180). Omit for an open-ended stopwatch the user must stop manually."},
     }}},
    {"name": "stop_focus_session", "description": "Stop the user's current open focus session now and log the elapsed time (no id needed). Use for 'I'm done', 'stop focus', 'end my session'. Under 5 minutes is discarded.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "end_focus_session", "description": "End a specific focus session by id; duration from wall clock. Prefer stop_focus_session for 'I'm done'.",
     "parameters": {"type": "object", "properties": {
         "session_id": {"type": "integer"},
     }, "required": ["session_id"]}},
]

DESTRUCTIVE_TOOLS = [
    {"name": "delete_note", "description": "Delete a note. Requires user confirmation — never call directly.",
     "parameters": {"type": "object", "properties": {
         "note_id": {"type": "integer"},
     }, "required": ["note_id"]}},
    {"name": "delete_countdown", "description": "Delete a countdown. Requires user confirmation — never call directly.",
     "parameters": {"type": "object", "properties": {
         "countdown_id": {"type": "integer"},
     }, "required": ["countdown_id"]}},
    {"name": "delete_mission", "description": "Delete a mission. Requires user confirmation — never call directly.",
     "parameters": {"type": "object", "properties": {
         "mission_id": {"type": "integer"},
     }, "required": ["mission_id"]}},
    {"name": "delete_habit", "description": "Delete a habit and its completion history. Requires user confirmation — never call directly.",
     "parameters": {"type": "object", "properties": {
         "habit_id": {"type": "integer"},
     }, "required": ["habit_id"]}},
    {"name": "delete_event", "description": "Delete a calendar event. Requires user confirmation — never call directly.",
     "parameters": {"type": "object", "properties": {
         "event_id": {"type": "integer"},
     }, "required": ["event_id"]}},
    {"name": "delete_briefing", "description": "Delete (turn off and remove) a morning or night briefing. Requires user confirmation — never call directly.",
     "parameters": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["morning", "night"]},
     }, "required": ["kind"]}},
    {"name": "delete_reminder", "description": "Delete a reminder. Requires user confirmation — never call directly.",
     "parameters": {"type": "object", "properties": {
         "reminder_id": {"type": "integer"},
     }, "required": ["reminder_id"]}},
]

ALL_TOOLS = READ_TOOLS + WRITE_TOOLS + DESTRUCTIVE_TOOLS
DESTRUCTIVE_TOOL_NAMES = {t["name"] for t in DESTRUCTIVE_TOOLS}
TOOL_NAMES = {t["name"] for t in ALL_TOOLS}


def describe_tool_target(
    db: Session, current_user: models.BatAccount, name: str, args: Dict[str, Any]
) -> Optional[str]:
    """Read-only fetch of a destructive tool's target title for the confirmation template.

    None when the target doesn't exist or the id argument is missing/invalid.
    """
    try:
        return _describe_tool_target(db, current_user, name, args)
    except (TypeError, ValueError):
        return None


def _describe_tool_target(
    db: Session, current_user: models.BatAccount, name: str, args: Dict[str, Any]
) -> Optional[str]:
    if name == "delete_note":
        note = notes_service.get_note(db, current_user, int(args.get("note_id")))
        return note.title if note else None
    if name == "delete_countdown":
        cd = countdown_service.get_countdown(db, current_user, int(args.get("countdown_id")))
        return cd.title if cd else None
    if name == "delete_mission":
        m = mission_service.list_missions(db, current_user)
        match = next((x for x in m if x.id == int(args.get("mission_id"))), None)
        return match.title if match else None
    if name == "delete_habit":
        h = habit_service.list_habits(db, current_user)
        match = next((x for x in h if x.id == int(args.get("habit_id"))), None)
        return match.name if match else None
    if name == "delete_event":
        e = calendar_service.list_upcoming_events(db, current_user)
        match = next((x for x in e if x.id == int(args.get("event_id"))), None)
        return match.title if match else None
    if name == "delete_briefing":
        kind = str(args.get("kind") or "")
        b = briefing_service.get_briefing(db, current_user, kind)
        return f"{kind} briefing" if b else None
    if name == "delete_reminder":
        r = briefing_service.get_reminder(db, current_user, int(args.get("reminder_id")))
        return r.message if r else None
    return None


def execute_tool(
    db: Session, current_user: models.BatAccount, name: str, args: Dict[str, Any],
    media_sink: Optional[list] = None,
) -> Dict[str, Any]:
    """Execute a non-destructive tool with the authenticated user injected.

    Destructive tools are refused here (defense in depth) — the agent loop
    must route them through the confirmation gate instead.
    """
    if name in DESTRUCTIVE_TOOL_NAMES:
        raise RuntimeError(f"Tool {name} requires confirmation and cannot execute directly")

    if name == "list_missions":
        due = _parse_dt(args.get("due_date"), "due_date") if args.get("due_date") else None
        all_m = mission_service.list_missions(db, current_user, due_date=due)
        # Code-computed counts so Alfred never has to tally the list itself.
        # "pending" matches the dashboard's Active Missions (status == 'pending').
        pending = [m for m in all_m if m.status == "pending"]
        completed = [m for m in all_m if m.status == "completed"]
        dismissed = [m for m in all_m if m.status == "dismissed" or m.is_dismissed]
        status = (args.get("status") or "pending").lower()
        shown = completed if status == "completed" else all_m if status == "all" else pending
        return {
            "missions": [_mission_dict(m) for m in shown],
            "showing": status,
            "counts": {
                "pending": len(pending),
                "completed": len(completed),
                "dismissed": len(dismissed),
                "total": len(all_m),
            },
        }
    if name == "list_habits":
        return {"habits": [_habit_dict(h) for h in habit_service.list_habits(db, current_user)]}
    if name == "list_upcoming_events":
        return {"events": [_event_dict(e) for e in calendar_service.list_upcoming_events(db, current_user)]}
    if name == "list_notes":
        return {"notes": [_note_dict(n) for n in notes_service.list_notes(
            db, current_user,
            search=args.get("search"), sort=args.get("sort") or "updated")]}
    if name == "list_countdowns":
        return {"countdowns": [_countdown_dict(c) for c in countdown_service.list_countdowns(db, current_user)]}
    if name == "list_recent_logs":
        return {"logs": [
            {"id": l.id, "timestamp": _iso(l.timestamp), "event_type": l.event_type, "details": l.details}
            for l in logs_service.list_recent_logs(
                db, current_user,
                limit=max(1, min(int(args.get("limit") or 50), 200)),
                start_date=_parse_dt(args.get("start_date"), "start_date") if args.get("start_date") else None,
                end_date=_parse_dt(args.get("end_date"), "end_date") if args.get("end_date") else None)
        ]}
    if name == "get_focus_stats":
        return stats_service.get_focus_stats(db, current_user, args.get("period") or "week")
    if name == "get_profile":
        u = profile_service.get_profile(db, current_user)
        return {"username": u.username, "points": u.points, "bat_level": u.bat_level}
    if name in ("show_focus_chart", "show_daily_brief"):
        # Image deliverables: rendered to PNG and queued for Telegram delivery.
        # The web chat can't display them, so there media_sink is None.
        if media_sink is None:
            return {"status": "unavailable_here",
                    "note": "I deliver charts as images on Telegram — ask me there."}
        from services import visuals

        render = visuals.render_focus_week if name == "show_focus_chart" else visuals.render_daily_brief
        png, caption = render(db, current_user)
        media_sink.append({"png": png, "caption": caption})
        return {"status": "sent", "visual": name, "note": "Image sent to the user."}
    if name == "alfred_list_memory_topics":
        return {"topics": [
            {"title": n.title, "description": _memory_brief(n)}
            for n in _memory_notes(db, current_user)
        ]}
    if name == "alfred_recall":
        query = (args.get("query") or "").strip()
        if not query:
            return {"error": "query is required"}
        matches = [
            n for n in notes_service.list_notes(db, current_user, search=query)
            if _has_memory_tag(n)
        ]
        return {"memories": [{"title": n.title, "body": n.body} for n in matches]}

    if name == "get_briefings":
        briefs = briefing_service.list_briefings(db, current_user)
        return {"briefings": [_briefing_dict(b) for b in briefs],
                "telegram_linked": telegram_service.is_telegram_linked(db, current_user)}
    if name == "list_reminders":
        rems = briefing_service.list_reminders(db, current_user)
        return {"reminders": [_reminder_dict(r) for r in rems],
                "telegram_linked": telegram_service.is_telegram_linked(db, current_user)}

    if name == "create_mission":
        title = (args.get("title") or "").strip()
        if not title:
            return {"error": "A mission needs a title."}
        existing = _open_mission_titles(db, current_user).get(_norm_title(title))
        if existing is not None:
            # Already on the board — don't make a second copy. This is NOT a
            # refusal: if the user's wording carries detail the existing mission
            # lacks, the right move is to enrich it with update_mission.
            return {
                "created": False,
                "reason": "A mission with this exact title is already open — not duplicated.",
                "existing_mission": _mission_dict(existing),
                "next_step": ("Compare what the user just said with existing_mission. If their "
                              "request adds anything new (a method, a tool, a date, a priority, "
                              "notes), call update_mission to add it and tell them precisely what "
                              "you changed. Only if nothing is new, say it's already on the board "
                              "and name it."),
            }
        m = _create_one_mission(db, current_user, {**args, "title": title})
        return {"mission": _mission_dict(m)}
    if name == "create_missions":
        items = args.get("missions") or []
        if not isinstance(items, list) or not items:
            return {"error": "Provide a non-empty 'missions' array."}
        existing = _open_mission_titles(db, current_user)
        seen = set()
        created, skipped = [], []
        for spec in items:
            if not isinstance(spec, dict):
                continue
            title = (spec.get("title") or "").strip()
            if not title:
                continue
            key = _norm_title(title)
            if key in seen or key in existing:
                skipped.append(title)
                continue
            seen.add(key)
            m = _create_one_mission(db, current_user, {**spec, "title": title})
            existing[key] = m  # guard against later dupes in the same batch
            created.append(_mission_dict(m))
        return {"created": created, "created_count": len(created),
                "skipped_duplicates": skipped}
    if name == "complete_mission":
        m = mission_service.complete_mission(db, current_user, int(args["mission_id"]))
        if m is None:
            return {"error": "Mission not found"}
        return {"mission": _mission_dict(m)}
    if name == "update_mission":
        m = mission_service.update_mission(
            db, current_user, int(args["mission_id"]),
            title=args.get("title"), description=args.get("description"),
            due_date=_parse_dt(args.get("due_date"), "due_date") if args.get("due_date") else None,
            priority=args.get("priority"), tags=args.get("tags"),
            location=args.get("location"), notes=args.get("notes"),
            subtasks=args.get("subtasks"),
            is_pinned=args.get("is_pinned"), is_dismissed=args.get("is_dismissed"))
        if m is None:
            return {"error": "Mission not found"}
        return {"mission": _mission_dict(m)}
    if name == "create_habit":
        h = habit_service.create_habit(
            db, current_user, name=args["name"],
            description=args.get("description"), frequency=args.get("frequency") or "daily")
        return {"habit": _habit_dict(h)}
    if name == "check_in_habit":
        h = habit_service.check_in_habit(db, current_user, int(args["habit_id"]))
        if h is None:
            return {"error": "Habit not found"}
        return {"habit": _habit_dict(h)}
    if name == "update_habit":
        h = habit_service.update_habit(
            db, current_user, int(args["habit_id"]),
            name=args.get("name"), description=args.get("description"),
            frequency=args.get("frequency"),
            target_date=_parse_dt(args.get("target_date"), "target_date") if args.get("target_date") else None)
        if h is None:
            return {"error": "Habit not found"}
        return {"habit": _habit_dict(h)}
    if name == "create_event":
        mission_id = args.get("mission_id")
        e = calendar_service.create_event(
            db, current_user, title=args["title"],
            start_time=_parse_dt(args["start_time"], "start_time"),
            description=args.get("description"),
            end_time=_parse_dt(args.get("end_time"), "end_time") if args.get("end_time") else None,
            color=args.get("color"),
            mission_id=int(mission_id) if mission_id is not None else None)
        if e is None:
            return {"error": "Event not created"}
        return {"event": _event_dict(e)}
    if name == "update_event":
        mission_id = args.get("mission_id")
        e = calendar_service.update_event(
            db, current_user, int(args["event_id"]),
            title=args.get("title"), description=args.get("description"),
            start_time=_parse_dt(args.get("start_time"), "start_time") if args.get("start_time") else None,
            end_time=_parse_dt(args.get("end_time"), "end_time") if args.get("end_time") else None,
            color=args.get("color"),
            mission_id=int(mission_id) if mission_id is not None else None)
        if e is None:
            return {"error": "Event not found"}
        return {"event": _event_dict(e)}
    if name == "create_note":
        n = notes_service.create_note(
            db, current_user, title=args.get("title") or "",
            body=args.get("body"), category=args.get("category"),
            tags=args.get("tags"))
        return {"note": _note_dict(n)}
    if name == "update_note":
        n = notes_service.update_note(
            db, current_user, int(args["note_id"]), title=args.get("title"),
            body=args.get("body"), category=args.get("category"),
            tags=args.get("tags"), is_pinned=args.get("is_pinned"))
        if n is None:
            return {"error": "Note not found"}
        return {"note": _note_dict(n)}
    if name == "toggle_pin":
        n = notes_service.toggle_pin(db, current_user, int(args["note_id"]))
        if n is None:
            return {"error": "Note not found"}
        return {"note": _note_dict(n)}
    if name == "alfred_remember":
        title = (args.get("title") or "").strip()
        content = (args.get("content") or "").strip()
        if not title or not content:
            return {"error": "title and content are both required"}
        existing = next(
            (n for n in _memory_notes(db, current_user) if (n.title or "").strip() == title),
            None,
        )
        if existing is not None:
            n = notes_service.update_note(db, current_user, existing.id, body=content)
            return {"note": {"id": n.id, "title": n.title}, "updated": True}
        n = notes_service.create_note(db, current_user, title=title, body=content, tags=MEMORY_TAG)
        return {"note": {"id": n.id, "title": n.title}, "updated": False}
    if name == "create_countdown":
        c = countdown_service.create_countdown(
            db, current_user, title=args["title"],
            target_date=_parse_dt(args["target_date"], "target_date"))
        return {"countdown": _countdown_dict(c)}
    if name == "update_countdown":
        c = countdown_service.update_countdown(
            db, current_user, int(args["countdown_id"]),
            title=args.get("title"),
            target_date=_parse_dt(args.get("target_date"), "target_date") if args.get("target_date") else None)
        if c is None:
            return {"error": "Countdown not found"}
        return {"countdown": _countdown_dict(c)}
    if name == "set_briefing":
        try:
            b = briefing_service.upsert_briefing(
                db, current_user, kind=args["kind"],
                enabled=args.get("enabled"), send_time=args.get("send_time"),
                include_missions=args.get("include_missions"),
                include_habits=args.get("include_habits"),
                include_events=args.get("include_events"),
                include_focus=args.get("include_focus"),
                include_news=args.get("include_news"),
                news_topics=args.get("news_topics"))
        except ValueError as exc:
            return {"error": str(exc)}
        result = {"briefing": _briefing_dict(b)}
        if not telegram_service.is_telegram_linked(db, current_user):
            result["note"] = ("Saved, but no Telegram is linked yet — briefings are "
                              "delivered over Telegram, so link it in Profile to receive them.")
        return result
    if name == "create_reminder":
        try:
            r = briefing_service.create_reminder(
                db, current_user, message=args["message"], recurrence=args["recurrence"],
                send_time=args["send_time"], weekdays=args.get("weekdays"),
                day_of_month=args.get("day_of_month"), run_date=args.get("run_date"),
                ends_on=args.get("ends_on"))
        except ValueError as exc:
            return {"error": str(exc)}
        result = {"reminder": _reminder_dict(r)}
        if not telegram_service.is_telegram_linked(db, current_user):
            result["note"] = ("Saved, but no Telegram is linked yet — reminders are "
                              "delivered over Telegram, so link it in Profile to receive them.")
        return result
    if name == "update_reminder":
        try:
            r = briefing_service.update_reminder(
                db, current_user, int(args["reminder_id"]),
                message=args.get("message"), enabled=args.get("enabled"),
                recurrence=args.get("recurrence"), send_time=args.get("send_time"),
                weekdays=args.get("weekdays"), day_of_month=args.get("day_of_month"),
                run_date=args.get("run_date"), ends_on=args.get("ends_on"))
        except ValueError as exc:
            return {"error": str(exc)}
        if r is None:
            return {"error": "Reminder not found"}
        return {"reminder": _reminder_dict(r)}
    if name == "get_nudge_settings":
        from services import nudges
        return {"nudges": {
            "enabled": bool(getattr(current_user, "nudges_enabled", True)),
            "quiet_start": getattr(current_user, "nudge_quiet_start", None) or nudges.DEFAULT_QUIET_START,
            "quiet_end": getattr(current_user, "nudge_quiet_end", None) or nudges.DEFAULT_QUIET_END,
            "per_day": getattr(current_user, "nudges_per_day", None) or nudges.DEFAULT_PER_DAY,
        }}
    if name == "set_nudge_settings":
        import re as _re
        hhmm = _re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
        if "enabled" in args and args["enabled"] is not None:
            current_user.nudges_enabled = bool(args["enabled"])
        for field, col in (("quiet_start", "nudge_quiet_start"), ("quiet_end", "nudge_quiet_end")):
            val = args.get(field)
            if val is not None:
                val = str(val).strip()
                if not hhmm.match(val):
                    return {"error": f"{field} must be HH:MM (24-hour), got {val!r}."}
                setattr(current_user, col, val)
        if args.get("per_day") is not None:
            try:
                per_day = int(args["per_day"])
            except (TypeError, ValueError):
                return {"error": "per_day must be a number."}
            if not 1 <= per_day <= 10:
                return {"error": "per_day must be between 1 and 10."}
            current_user.nudges_per_day = per_day
        db.commit()
        return execute_tool(db, current_user, "get_nudge_settings", {})
    if name == "get_active_focus_session":
        active = focus_service.active_focus_session(db, current_user)
        if active is None:
            return {"active": None, "note": "No focus session is currently running."}
        return {"active": _active_session_dict(active)}
    if name == "start_focus_session":
        existing = focus_service.active_focus_session(db, current_user)
        if existing is not None:
            return {"error": "A focus session is already running — stop it first.",
                    "active": _active_session_dict(existing)}
        planned = args.get("planned_minutes")
        if planned is not None:
            try:
                planned = int(planned)
            except (TypeError, ValueError):
                return {"error": "planned_minutes must be a number."}
            if not 5 <= planned <= 180:
                return {"error": "planned_minutes must be between 5 and 180."}
        try:
            s = focus_service.start_focus_session(
                db, current_user,
                mission_id=int(args["mission_id"]) if args.get("mission_id") else None,
                habit_id=int(args["habit_id"]) if args.get("habit_id") else None,
                planned_minutes=planned)
        except ValueError as exc:
            return {"error": str(exc)}
        result = _session_dict(s)
        if planned:
            result["planned_minutes"] = planned
            result["note"] = (f"Timer running for {planned} minutes. It ends on its own and I'll "
                              "message you here when it's complete — no screen to watch.")
        else:
            result["note"] = FOCUS_NO_LIVE_SYNC_NOTE + " Tell me 'stop' when you're done and I'll log the time."
        return {"session": result}
    if name == "stop_focus_session":
        active = focus_service.active_focus_session(db, current_user)
        if active is None:
            return {"note": "No focus session is currently running."}
        s = focus_service.end_focus_session(db, current_user, active.id)
        if s is None:
            return {"note": "No focus session is currently running."}
        out = _session_dict(s)
        if getattr(s, "discarded", False):
            out["note"] = "That was under 5 minutes, so it wasn't logged."
        return {"session": out}
    if name == "end_focus_session":
        s = focus_service.end_focus_session(db, current_user, int(args["session_id"]))
        if s is None:
            return {"error": "Focus session not found"}
        return {"session": _session_dict(s)}

    raise ValueError(f"Unknown tool: {name}")
