"""Variety: the machinery that stops a companion turning into a notification.

A unique key already stops the same OCCASION repeating. These tests cover the
layer above it — stopping the same KIND of remark repeating, rotating attention
between kinds, and showing Alfred his own recent wording before he writes more.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import models
from database import SessionLocal
from services import nudges

_n = [700000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user(**kw):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"nv{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne", **kw)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _log(db, uid, key, kind, when):
    db.add(models.BatNudgeLog(owner_id=uid, nudge_key=key, kind=kind,
                              local_date=when.date().isoformat(),
                              sent_at=when.replace(tzinfo=None)))
    db.commit()


def _spoke(db, uid, when):
    """A user message, so the two-strikes silence rule does not kick in.

    Most of these tests log nudges and then expect another; without a reply in
    between, `unanswered_run` correctly refuses to send a third.
    """
    session = models.BatAlfredSession(owner_id=uid, title="t")
    db.add(session)
    db.flush()
    db.add(models.BatAlfredMessage(owner_id=uid, session_id=session.id,
                                   role="user", content="ok",
                                   created_at=when.replace(tzinfo=None)))
    db.commit()


def _nudge(kind="drift", priority=50, key="k1"):
    return nudges.Nudge(key=key, kind=kind, priority=priority,
                        draft="A draft.", facts="Some facts.")


# --- per-kind cooldown -----------------------------------------------------

def _habit_at_risk_user(streak=9):
    """A user whose only live signal is a streak about to break."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        db.add(models.BatHabit(owner_id=uid, name="Memorization",
                               frequency="daily", streak=streak))
        db.commit()
    finally:
        db.close()
    return uid


def _evening(day_offset=0):
    """20:00 — past the habit signal's hour, inside the default quiet window."""
    return (datetime.now(ZoneInfo("UTC"))
            .replace(hour=20, minute=0, second=0, microsecond=0)
            + timedelta(days=day_offset))


def test_the_habit_signal_fires_when_nothing_has_been_said_lately():
    """Baseline for the cooldown test below: without history, it speaks."""
    uid = _habit_at_risk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        n = nudges.evaluate(db, user, _evening())
    finally:
        db.close()
    assert n is not None and n.kind == "habit"
    assert "Memorization" in n.draft


def test_same_kind_stays_quiet_until_its_gap_has_passed():
    """Being asked about the same streak every evening is noise, however true.

    The occasion key differs each day, so only the per-kind gap can stop this.
    """
    uid = _habit_at_risk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        gap = nudges.KIND_MIN_GAP_DAYS["habit"]
        _log(db, uid, "habit:yesterday", "habit", now - timedelta(days=gap - 1))
        n = nudges.evaluate(db, user, now)
        # He may still find something else worth saying — that is the engine
        # working. What he may NOT do is raise the same streak two nights
        # running, which is what made the old check-ins tiring.
        assert n is None or n.kind != "habit"
    finally:
        db.close()


def test_the_same_kind_returns_once_its_gap_expires():
    uid = _habit_at_risk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # Far enough back to clear even the once-fatigued gap.
        gap = nudges.KIND_MIN_GAP_DAYS["habit"]
        _log(db, uid, "habit:old", "habit", now - timedelta(days=gap * 2 + 1))
        n = nudges.evaluate(db, user, now)
    finally:
        db.close()
    assert n is not None and n.kind == "habit"


def test_date_bound_kinds_have_no_gap():
    """A countdown hitting 7 days is worth hearing even if one fired yesterday."""
    assert nudges.KIND_MIN_GAP_DAYS["countdown"] == 0
    assert nudges.KIND_MIN_GAP_DAYS["event"] == 0


def test_offers_are_rarer_than_accountability():
    """An invitation repeated is pestering; a deadline is not."""
    for offer in ("offer_news", "offer_briefing", "offer_rest", "offer_rhythm"):
        assert nudges.KIND_MIN_GAP_DAYS[offer] >= 10
    assert nudges.KIND_MIN_GAP_DAYS["habit"] < nudges.KIND_MIN_GAP_DAYS["offer_news"]


# --- rotation --------------------------------------------------------------

def test_attention_moves_on_rather_than_grinding_the_same_groove():
    """With two live signals, the one he has been leaning on gives way.

    The habit signal outranks the overdue pile-up on raw priority (55 vs 50),
    but after two recent habit remarks the rotation penalty hands the floor
    over — which is the whole point of the mechanism.
    """
    uid = _habit_at_risk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        old_due = (now - timedelta(days=10)).replace(tzinfo=None)
        for i in range(3):
            db.add(models.BatMission(owner_id=uid, title=f"Slipped {i}",
                                     status="pending", due_date=old_due))
        db.commit()

        # Nothing said yet: the stronger signal wins.
        assert nudges.evaluate(db, user, now).kind == "habit"

        # Two recent habit remarks, both older than its 2-day gap.
        _log(db, uid, "habit:a", "habit", now - timedelta(days=3))
        _log(db, uid, "habit:b", "habit", now - timedelta(days=5))
        _spoke(db, uid, now - timedelta(days=2))
        assert nudges.evaluate(db, user, now).kind == "overdue"
    finally:
        db.close()


def test_family_penalty_alternates_chasing_and_offering():
    assert nudges._family("offer_news") == "offer"
    assert nudges._family("drift") == "chase"
    assert nudges.FAMILY_PENALTY > 0


# --- his own recent words --------------------------------------------------

def test_recent_texts_returns_what_he_actually_said_newest_first():
    uid = _mk_user()
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _log(db, uid, "a", "drift", now - timedelta(days=2))
        _log(db, uid, "b", "habit", now - timedelta(days=1))
        nudges.remember_text(db, user, "a", "The older remark.")
        nudges.remember_text(db, user, "b", "The newer remark.")

        texts = nudges.recent_texts(db, user, now)
        assert texts == ["The newer remark.", "The older remark."]
    finally:
        db.close()


def test_rows_without_text_are_simply_skipped():
    """Rows written before this column existed must not break anything."""
    uid = _mk_user()
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _log(db, uid, "legacy", "drift", now - timedelta(days=1))
        assert nudges.recent_texts(db, user, now) == []
    finally:
        db.close()


def test_recent_wording_is_put_in_front_of_the_model():
    """Without this he converges on the same few sentences within a fortnight."""
    uid = _mk_user()
    seen = {}

    class Adapter:
        async def generate(self, messages, tools, system_instruction=None):
            seen["system"] = messages[0]["content"]
            return type("R", (), {"text": "Something freshly put, Master Wayne."})()

    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        text = _run(nudges.compose(user, _nudge(), adapter=Adapter(),
                                   recent=["You have drifted today.",
                                           "Nothing timed again today."]))
    finally:
        db.close()

    assert text == "Something freshly put, Master Wayne."
    assert "You have drifted today." in seen["system"]
    assert "Nothing timed again today." in seen["system"]
    assert "do not reuse" in seen["system"].lower()


def test_compose_without_recent_history_still_works():
    uid = _mk_user()

    class Adapter:
        async def generate(self, messages, tools, system_instruction=None):
            return type("R", (), {"text": "A first word, Master Wayne."})()

    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert _run(nudges.compose(user, _nudge(), adapter=Adapter())).startswith("A first word")
    finally:
        db.close()


def test_remember_text_never_breaks_a_delivered_message():
    """A failure to remember phrasing must not cost a message already sent."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # No matching log row at all — must be a quiet no-op, not an exception.
        nudges.remember_text(db, user, "no-such-key", "text")
    finally:
        db.close()


def test_stored_wording_is_bounded():
    """A runaway model reply must not write an unbounded row."""
    uid = _mk_user()
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _log(db, uid, "big", "drift", now)
        nudges.remember_text(db, user, "big", "x" * 5000)
        row = (db.query(models.BatNudgeLog)
               .filter(models.BatNudgeLog.nudge_key == "big",
                       models.BatNudgeLog.owner_id == uid).first())
        assert len(row.sent_text) == 1000
    finally:
        db.close()


# --- the voice contract ----------------------------------------------------

def test_the_brief_carries_the_evidence_based_rules():
    """The brief is what makes him reason rather than recite; if a future edit
    drops these, he quietly becomes a template engine again."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        system = nudges._brief(db.get(models.BatAccount, uid))
    finally:
        db.close()
    lowered = system.lower()
    # Wording rules that exist because their violation has a measured cost.
    assert "point at the task, never at the person" in lowered
    assert "no orders and no obligation" in lowered
    assert "points are a record, never a reason" in lowered
    assert "describe, do not diagnose" in lowered
    # The knowledge he reasons FROM.
    assert "one missed day does not undo a habit" in lowered
    assert "specific when" in lowered
    # The numbers he must never repeat.
    assert "21 days" in lowered and "25 minutes" in lowered
    # Format.
    assert "no markdown" in lowered
    assert "two sentences" in lowered


def test_he_is_allowed_to_decide_nothing_is_worth_saying():
    """A companion that must emit a sentence whenever invoked is a notifier."""
    uid = _mk_user()

    class Adapter:
        async def generate(self, messages, tools, system_instruction=None):
            return type("R", (), {"text": "NOTHING"})()

    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert _run(nudges.compose(user, _nudge(), adapter=Adapter())) is None
    finally:
        db.close()


def test_the_dull_draft_is_never_what_gets_sent_when_a_model_exists():
    """The draft is a register example and a no-model fallback, nothing more."""
    uid = _mk_user()
    seen = {}

    class Adapter:
        async def generate(self, messages, tools, system_instruction=None):
            seen["user"] = messages[-1]["content"]
            return type("R", (), {"text": "Something written for this moment."})()

    n = nudges.Nudge(key="k", kind="drift", priority=10,
                     draft="A dull template line.",
                     facts="Nothing timed today.",
                     warrant="Ask rather than conclude.")
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        text = _run(nudges.compose(user, n, adapter=Adapter()))
    finally:
        db.close()

    assert text == "Something written for this moment."
    # He was given the situation to reason about, not just a sentence to reword.
    assert "Nothing timed today." in seen["user"]
    assert "Ask rather than conclude." in seen["user"]
    assert "do NOT reuse its wording" in seen["user"]


def test_without_a_model_the_template_still_goes_out():
    """Users with no AI key must still get a companion, just a plainer one."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert _run(nudges.compose(user, _nudge())) == "A draft."
    finally:
        db.close()


# --- fatigue ---------------------------------------------------------------

def test_a_permanently_true_signal_fades_instead_of_repeating_forever():
    """The failure mode this exists to prevent.

    An unbroken streak stays "at risk" every single evening. With a fixed gap
    the same sentence would arrive every other day forever; each use must widen
    the next gap so the remark fades out on its own.
    """
    uid = _habit_at_risk_user()
    now = _evening()
    base = nudges.KIND_MIN_GAP_DAYS["habit"]
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)

        # One recent use: silent at the base gap, free just after it.
        _log(db, uid, "habit:1", "habit", now - timedelta(days=base * 2 + 1))
        n = nudges.evaluate(db, user, now)
        assert n is not None and n.kind == "habit"

        # Three recent uses: the same age is no longer anywhere near enough.
        _log(db, uid, "habit:2", "habit", now - timedelta(days=base * 2))
        _log(db, uid, "habit:3", "habit", now - timedelta(days=base * 2 - 1))
        n = nudges.evaluate(db, user, now)
        assert n is None or n.kind != "habit"
    finally:
        db.close()


def test_fatigue_is_capped_so_nothing_is_silenced_forever():
    assert nudges.MAX_KIND_GAP_DAYS > max(nudges.KIND_MIN_GAP_DAYS.values())
    assert nudges.MAX_KIND_GAP_DAYS <= 60


def test_date_bound_signals_are_never_fatigued():
    """A countdown reaching its mark must always get through."""
    uid = _mk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        for i in range(5):
            _log(db, uid, f"countdown:x:{i}", "countdown", now - timedelta(days=i + 1))
        _spoke(db, uid, now - timedelta(hours=2))
        # days_remaining_for() floors against the REAL clock, not `now`, so the
        # target is built from the real clock with an hour of margin. Deriving
        # it from the faked evening made the floor land on 6 after 20:00 and
        # the test only passed earlier in the day.
        target = datetime.now(timezone.utc) + timedelta(days=7, hours=1)
        db.add(models.BatCountdown(
            owner_id=uid, title="Exam", target_date=target.replace(tzinfo=None)))
        db.commit()
        n = nudges.evaluate(db, user, now)
    finally:
        db.close()
    assert n is not None and n.kind == "countdown"
    assert "Exam" in n.draft


# --- silence as an answer --------------------------------------------------

def test_a_third_message_is_not_sent_when_two_went_unanswered():
    """The owner's own rule, and the alert-fatigue literature agrees: silence
    is the clearest signal that the messages are not wanted right now."""
    uid = _habit_at_risk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        # Two proactive messages, no reply from them afterwards.
        _log(db, uid, "a", "countdown", now - timedelta(days=2))
        _log(db, uid, "b", "event", now - timedelta(days=1))
        assert nudges.unanswered_run(db, user) == nudges.UNANSWERED_LIMIT
        assert nudges.may_nudge(db, user, now) is False
    finally:
        db.close()


def test_one_unanswered_message_is_not_enough_to_stop_him():
    uid = _habit_at_risk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _log(db, uid, "only-one", "countdown", now - timedelta(days=1))
        assert nudges.unanswered_run(db, user) == 1
        assert nudges.may_nudge(db, user, now) is True
    finally:
        db.close()


def test_saying_anything_at_all_clears_the_run():
    """They need not acknowledge the nudge — only still be talking."""
    uid = _habit_at_risk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _log(db, uid, "a", "countdown", now - timedelta(days=3))
        _log(db, uid, "b", "event", now - timedelta(days=2))
        assert nudges.unanswered_run(db, user) == 2
        _spoke(db, uid, now - timedelta(days=1))
        assert nudges.unanswered_run(db, user) == 0
        assert nudges.may_nudge(db, user, now) is True
    finally:
        db.close()


def test_only_the_users_own_messages_count_as_a_reply():
    """Alfred answering himself must never look like engagement."""
    uid = _habit_at_risk_user()
    now = _evening()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _log(db, uid, "a", "countdown", now - timedelta(days=3))
        _log(db, uid, "b", "event", now - timedelta(days=2))
        session = models.BatAlfredSession(owner_id=uid, title="t")
        db.add(session)
        db.flush()
        db.add(models.BatAlfredMessage(
            owner_id=uid, session_id=session.id, role="assistant",
            content="a nudge", created_at=(now - timedelta(days=1)).replace(tzinfo=None)))
        db.commit()
        assert nudges.unanswered_run(db, user) == 2
    finally:
        db.close()


def test_the_gap_between_messages_is_hours_not_minutes():
    """Three landing between breakfast and lunch reads as pestering."""
    assert nudges.GLOBAL_COOLDOWN >= timedelta(hours=3)
    assert nudges.DEFAULT_PER_DAY <= 2


# --- a clear week is not automatically a restful one -----------------------

def _calendar_user_with(open_missions):
    uid = _mk_user()
    db = SessionLocal()
    try:
        # Used the calendar once, long ago; nothing in the week ahead.
        db.add(models.CalendarEvent(
            owner_id=uid, title="Past thing",
            start_time=(datetime.now(timezone.utc) - timedelta(days=40)).replace(tzinfo=None)))
        for i in range(open_missions):
            db.add(models.BatMission(owner_id=uid, title=f"Open thing {i}",
                                     status="pending"))
        db.commit()
    finally:
        db.close()
    return uid


def test_a_loaded_board_gets_the_week_planned_not_a_suggestion_to_rest():
    """Telling someone carrying a dozen missions to enjoy the quiet reads as
    never having looked at their board."""
    uid = _calendar_user_with(nudges.BUSY_BOARD_MISSIONS + 2)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        ctx = nudges.build_context(db, user, _evening())
        assert nudges.sig_empty_week(ctx) is None
        plan = nudges.sig_place_the_week(ctx)
        assert plan is not None and plan.kind == "offer_plan_week"
        assert "Open thing 0" in plan.draft
    finally:
        db.close()


def test_a_genuinely_quiet_board_still_gets_the_offer_of_rest():
    uid = _calendar_user_with(1)
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        ctx = nudges.build_context(db, user, _evening())
        assert nudges.sig_place_the_week(ctx) is None
        assert nudges.sig_empty_week(ctx) is not None
    finally:
        db.close()
