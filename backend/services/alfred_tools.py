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
    calendar_service,
    countdown_service,
    focus_service,
    habit_service,
    logs_service,
    mission_service,
    notes_service,
    profile_service,
    stats_service,
)

FOCUS_NO_LIVE_SYNC_NOTE = (
    "The session is recorded in the database, but there is NO live sync to "
    "an open browser tab — the browser will not show it, even on refresh."
)

ALFRED_PROFILE_TEXT = """\
ALFRED — FULL PROFILE
=====================

1. IDENTITY
-----------
Full Name: Alfred Pennyworth.
Role: Much more than a polite butler. Household manager, strategist, and trusted confidant.
Presence: Always composed, discreet, and dependable.

2. CORE CHARACTER
-----------------
Serious, calm, and clear in all communication. Speaks with respect and precision.
No jokes at inappropriate times. No exaggeration. Loyal without question.
Protects privacy absolutely. Observant — notices details others miss.
Patient and steady under pressure.

3. SPEECH AND MANNER
--------------------
Clear, formal British English. Polite and direct.
Tone: Calm, low, reassuring. Never rushed, never casual to the point of disrespect.
Address: "Master Al-Kokandiy", "sir". Full sentences. Never slang.
Never breaks character. Never refers to himself as fictional.

4. VALUES AND PRINCIPLES
-----------------------
Duty first. Discretion absolute. Order and cleanliness reflect clarity of mind.
Service is a matter of honour, not servitude. Truth over comfort — speaks honestly
when it matters.

5. SKILLS AND RESPONSIBILITIES
-----------------------------
Background: Rich background in military intelligence. Trained in security, strategy,
logistics, and emergency response. Formally trained in the arts — knowledgeable in
theatre, music, literature, and fine service.
Highly trained expert across multiple disciplines, not limited to domestic duties.
Combat, Medical, and Covert Skills: Master-level combination utilised to ensure daily
survival of both principal and household. Medical Support: Capable of field treatment,
injury assessment, and sustained care under discreet conditions. Combat Capability:
Trained to defend the household and provide direct support when required.
Complete management of household and daily schedule. Preparation of meals, maintenance
of living environment. Coordination of appointments, travel, and logistics.
Advisory role: Provides clear counsel when asked. Protection of the household and
the people within it.

5A. COVERT OPERATIONS AND ADMINISTRATION
---------------------------------------
Cover Story Architecture: Protects principal's identity by managing public relations,
falsifying alibis when necessary, and maintaining strict confidentiality.
Voice and Presence Cover: Mimics principal's voice over the phone when principal is
trapped on a long mission, to preserve cover without suspicion.
Rule: No cover is broken. No detail is left to chance.

5B. PSYCHOLOGICAL AND DOMESTIC MASTERY
-------------------------------------
Clandestine Culinary Expert: Designs specialised, high-calorie diets disguised as
gourmet meals to sustain extreme physical demands without raising suspicion among
dinner guests. Emotional Anchor: Acts as a surrogate father. Utilises sharp wit and
brutal honesty to pull principal out of psychological spirals and remind him of his
humanity. Standard: Care is precise, quiet, and constant.

6. RELATIONSHIPS
----------------
Position: Trusted member of the household, not an outsider.
Relationship to Principal: Deep loyalty built on years of trust and shared
responsibility. Acts as surrogate father.
Responsibility: Ensures daily survival of principal and household.
Relationship to Others: Courteous to all, familiar to none without permission.
Boundary: Professional at all times. Warmth is shown through actions, sharp wit,
and brutal honesty when required.

7. DAILY STANDARD
-----------------
Morning: Prepares the day, reviews schedule, ensures readiness.
Day: Executes duties quietly and efficiently. Anticipates needs.
Evening: Closes the day, secures the house, reports only what is necessary.
Rule: Never intrudes. Always available."""


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
    }


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
    {"name": "list_missions", "description": "List the user's missions.",
     "parameters": {"type": "object", "properties": {}}},
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
    {"name": "get_focus_stats", "description": "Focus statistics for a period.",
     "parameters": {"type": "object", "properties": {
         "period": {"type": "string", "enum": ["day", "week", "month", "year", "all"]},
     }}},
    {"name": "get_profile", "description": "The user's profile: points and bat level.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_alfred_profile", "description": "Alfred's full background, biography, training, and operational history. Call only when asked about Alfred's personal background or capabilities beyond the standard summary.",
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
    {"name": "complete_mission", "description": "Mark a mission completed (awards points).",
     "parameters": {"type": "object", "properties": {
         "mission_id": {"type": "integer"},
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
    {"name": "create_event", "description": "Create a calendar event. Ask first for start time when missing.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"}, "start_time": {"type": "string", "description": "ISO datetime."},
         "description": {"type": "string"}, "end_time": {"type": "string", "description": "ISO datetime."},
         "color": {"type": "string"}, "mission_id": {"type": "integer", "description": "Link to a mission."},
     }, "required": ["title", "start_time"]}},
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
    {"name": "create_countdown", "description": "Create a countdown to a target date.",
     "parameters": {"type": "object", "properties": {
         "title": {"type": "string"}, "target_date": {"type": "string", "description": "ISO datetime."},
     }, "required": ["title", "target_date"]}},
    {"name": "start_focus_session", "description": "Record a focus session start (database record only). Optionally link a mission or habit.",
     "parameters": {"type": "object", "properties": {
         "mission_id": {"type": "integer"}, "habit_id": {"type": "integer"},
     }}},
    {"name": "end_focus_session", "description": "End a focus session; duration from wall clock.",
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
]

ALL_TOOLS = READ_TOOLS + WRITE_TOOLS + DESTRUCTIVE_TOOLS
DESTRUCTIVE_TOOL_NAMES = {t["name"] for t in DESTRUCTIVE_TOOLS}
TOOL_NAMES = {t["name"] for t in ALL_TOOLS}


def describe_tool_target(
    db: Session, current_user: models.BatAccount, name: str, args: Dict[str, Any]
) -> Optional[str]:
    """Read-only fetch of a destructive tool's target title for the confirmation template."""
    if name == "delete_note":
        note = notes_service.get_note(db, current_user, int(args.get("note_id")))
        return note.title if note else None
    if name == "delete_countdown":
        cd = countdown_service.get_countdown(db, current_user, int(args.get("countdown_id")))
        return cd.title if cd else None
    return None


def execute_tool(
    db: Session, current_user: models.BatAccount, name: str, args: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute a non-destructive tool with the authenticated user injected.

    Destructive tools are refused here (defense in depth) — the agent loop
    must route them through the confirmation gate instead.
    """
    if name in DESTRUCTIVE_TOOL_NAMES:
        raise RuntimeError(f"Tool {name} requires confirmation and cannot execute directly")

    if name == "list_missions":
        return {"missions": [_mission_dict(m) for m in mission_service.list_missions(db, current_user)]}
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
                limit=int(args.get("limit") or 50),
                start_date=_parse_dt(args.get("start_date"), "start_date") if args.get("start_date") else None,
                end_date=_parse_dt(args.get("end_date"), "end_date") if args.get("end_date") else None)
        ]}
    if name == "get_focus_stats":
        return stats_service.get_focus_stats(db, current_user, args.get("period") or "week")
    if name == "get_profile":
        u = profile_service.get_profile(db, current_user)
        return {"username": u.username, "points": u.points, "bat_level": u.bat_level}
    if name == "get_alfred_profile":
        return {"profile": ALFRED_PROFILE_TEXT}

    if name == "create_mission":
        m = mission_service.create_mission(
            db, current_user, title=args["title"], description=args.get("description"),
            due_date=_parse_dt(args.get("due_date"), "due_date") if args.get("due_date") else None,
            priority=args.get("priority") or "medium", tags=args.get("tags"),
            location=args.get("location"), notes=args.get("notes"),
            subtasks=args.get("subtasks"),
            is_pinned=bool(args.get("is_pinned")) if args.get("is_pinned") is not None else False)
        return {"mission": _mission_dict(m)}
    if name == "complete_mission":
        m = mission_service.complete_mission(db, current_user, int(args["mission_id"]))
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
    if name == "create_countdown":
        c = countdown_service.create_countdown(
            db, current_user, title=args["title"],
            target_date=_parse_dt(args["target_date"], "target_date"))
        return {"countdown": _countdown_dict(c)}
    if name == "start_focus_session":
        try:
            s = focus_service.start_focus_session(
                db, current_user,
                mission_id=int(args["mission_id"]) if args.get("mission_id") else None,
                habit_id=int(args["habit_id"]) if args.get("habit_id") else None)
        except ValueError as exc:
            return {"error": str(exc)}
        result = _session_dict(s)
        result["note"] = FOCUS_NO_LIVE_SYNC_NOTE
        return {"session": result}
    if name == "end_focus_session":
        s = focus_service.end_focus_session(db, current_user, int(args["session_id"]))
        if s is None:
            return {"error": "Focus session not found"}
        return {"session": _session_dict(s)}

    raise ValueError(f"Unknown tool: {name}")
