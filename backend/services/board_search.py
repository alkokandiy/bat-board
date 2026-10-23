"""One way to find anything on the board by what the user called it.

Alfred had no search. To act on "Restart screen time challenge" he had to
list every mission and match it by eye, and when the stored title was
"Restart the screen-time challenge" he announced it did not exist. Telling
somebody their own item is missing, when it is sitting on the board, is worse
than being slow: they stop believing the board.

Matching is deliberately generous. People paraphrase their own titles, drop
articles, mistype, and switch language mid-sentence; the cost of offering one
extra candidate is a glance, while the cost of missing the right one is a
flat denial.
"""

from __future__ import annotations

import difflib
import re
from typing import List, Optional

from sqlalchemy.orm import Session

import models

# Below this, two titles are not plausibly the same thing.
MATCH_FLOOR = 0.45
MAX_RESULTS = 8
_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def _norm(text: str) -> str:
    return " ".join(_WORD.sub(" ", (text or "").lower()).split())


def score(query: str, title: str) -> float:
    """How plausibly `title` is what the user meant by `query`."""
    q, t = _norm(query), _norm(title)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if q in t or t in q:
        return 0.92
    ratio = difflib.SequenceMatcher(None, q, t).ratio()
    # Shared words matter more than character order: "screen time challenge"
    # and "challenge of screen-time" are the same thing to a person.
    qw, tw = set(q.split()), set(t.split())
    overlap = len(qw & tw) / max(1, min(len(qw), len(tw)))
    return max(ratio, overlap * 0.9)


def search(db: Session, user: models.BatAccount, query: str,
           kinds: Optional[List[str]] = None) -> dict:
    """Everything on this user's board plausibly matching `query`."""
    wanted = set(kinds) if kinds else None

    def want(kind: str) -> bool:
        return wanted is None or kind in wanted

    rows = []

    if want("mission"):
        for m in db.query(models.BatMission).filter(
                models.BatMission.owner_id == user.id).all():
            rows.append(("mission", m.id, m.title,
                         {"status": m.status, "due_date": str(m.due_date) if m.due_date else None}))
    if want("habit"):
        for h in db.query(models.BatHabit).filter(
                models.BatHabit.owner_id == user.id).all():
            rows.append(("habit", h.id, h.name, {"streak": h.streak or 0}))
    if want("note"):
        for n in db.query(models.BatNote).filter(
                models.BatNote.owner_id == user.id).all():
            rows.append(("note", n.id, n.title or "", {"tags": n.tags or ""}))
    if want("work_task"):
        for t in db.query(models.BatWorkTask).filter(
                models.BatWorkTask.owner_id == user.id).all():
            rows.append(("work_task", t.id, t.title, {"status": t.status}))
    if want("event"):
        for e in db.query(models.CalendarEvent).filter(
                models.CalendarEvent.owner_id == user.id).all():
            rows.append(("event", e.id, e.title,
                         {"start_time": str(e.start_time) if e.start_time else None}))
    if want("countdown"):
        for c in db.query(models.BatCountdown).filter(
                models.BatCountdown.owner_id == user.id).all():
            rows.append(("countdown", c.id, c.title,
                         {"target_date": str(c.target_date) if c.target_date else None}))

    scored = []
    for kind, rid, title, extra in rows:
        sc = score(query, title)
        if sc >= MATCH_FLOOR:
            scored.append({"kind": kind, "id": rid, "title": title,
                           "match": round(sc, 2), **extra})
    scored.sort(key=lambda r: (-r["match"], r["kind"]))

    out = {"query": query, "matches": scored[:MAX_RESULTS],
           "total_searched": len(rows)}
    if not scored:
        out["note"] = (
            "Nothing matched. Before telling them it does not exist, consider "
            "listing that kind of item and reading the titles yourself — they "
            "may have described it rather than named it.")
    else:
        out["note"] = (
            "Use the id of the match you believe they meant, and pass its "
            "exact title as expected_title. If two are close, ask which.")
    return out
