"""Alfred's OFFER signals: the proactive check-ins that suggest something
rather than chase something. Each fires on real board state and stays quiet on
the nearest state that should not provoke it."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import models
from database import SessionLocal
from services import nudges

_n = [500000]


def _mk_user(linked=True, **kw):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"nf{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne", **kw)
        db.add(u)
        db.commit()
        db.refresh(u)
        if linked:
            db.add(models.BatPersonalAccessToken(
                owner_id=u.id, token_hash=f"h{_n[0]}", telegram_chat_id=str(7000 + _n[0])))
            db.commit()
        return u.id
    finally:
        db.close()


def _noon(day_offset=0):
    return datetime.now(ZoneInfo("UTC")).replace(hour=16, minute=0, second=0, microsecond=0) \
        + timedelta(days=day_offset)


def _at(hour, day_offset=0):
    return datetime.now(ZoneInfo("UTC")).replace(hour=hour, minute=0, second=0, microsecond=0) \
        + timedelta(days=day_offset)


def _focus_at(db, uid, hour, count, ref):
    """Record `count` focus sessions all starting at the given local hour."""
    start = (ref - timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    for _ in range(count):
        db.add(models.BatFocus(owner_id=uid, start_time=start,
                               end_time=start + timedelta(minutes=30),
                               duration_minutes=30))


def _morning(db, uid, news_topics=None):
    db.add(models.BatBriefing(owner_id=uid, kind="morning", enabled=True,
                              send_time="08:00", news_topics=news_topics))


# --- sig_news_topic_offer ---------------------------------------------------

def test_news_topic_offer_fires_on_recurring_labelled_theme():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        for i in range(3):
            db.add(models.BatMission(owner_id=uid, title=f"Garden {i}",
                                     status="pending", tags="gardening"))
        _morning(db, uid)
        db.commit()
        ctx = nudges.build_context(db, user, _noon())
        n = nudges.sig_news_topic_offer(ctx)
        assert n is not None and n.kind == "offer_news"
        assert "gardening" in n.draft and "3" in n.draft
    finally:
        db.close()


def test_news_topic_offer_silent_when_topic_already_followed():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        for i in range(3):
            db.add(models.BatMission(owner_id=uid, title=f"Garden {i}",
                                     status="pending", tags="gardening"))
        _morning(db, uid, news_topics="gardening")
        db.commit()
        ctx = nudges.build_context(db, user, _noon())
        assert nudges.sig_news_topic_offer(ctx) is None
    finally:
        db.close()


def test_news_topic_offer_silent_without_any_briefing():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        for i in range(3):
            db.add(models.BatMission(owner_id=uid, title=f"Garden {i}",
                                     status="pending", tags="gardening"))
        db.commit()
        ctx = nudges.build_context(db, user, _noon())
        assert nudges.sig_news_topic_offer(ctx) is None
    finally:
        db.close()


# --- sig_night_briefing_offer -----------------------------------------------

def test_night_briefing_offer_fires_for_established_morning_user():
    now = _noon()
    uid = _mk_user(created_at=now - timedelta(days=30))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _morning(db, uid)
        db.commit()
        ctx = nudges.build_context(db, user, now)
        n = nudges.sig_night_briefing_offer(ctx)
        assert n is not None and n.kind == "offer_briefing"
        assert "morning" in n.draft
    finally:
        db.close()


def test_night_briefing_offer_silent_when_night_already_enabled():
    now = _noon()
    uid = _mk_user(created_at=now - timedelta(days=30))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _morning(db, uid)
        db.add(models.BatBriefing(owner_id=uid, kind="night", enabled=True,
                                  send_time="21:00"))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_night_briefing_offer(ctx) is None
    finally:
        db.close()


def test_night_briefing_offer_silent_for_young_account():
    now = _noon()
    uid = _mk_user(created_at=now - timedelta(days=2))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _morning(db, uid)
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_night_briefing_offer(ctx) is None
    finally:
        db.close()


# --- sig_first_briefing_offer -----------------------------------------------

def test_first_briefing_offer_fires_for_settled_user_with_a_board():
    now = _noon()
    uid = _mk_user(created_at=now - timedelta(days=10))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Plan the trip", status="pending"))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        n = nudges.sig_first_briefing_offer(ctx)
        assert n is not None and n.kind == "offer_briefing"
        assert "Master Wayne" in n.draft and "morning" in n.draft
    finally:
        db.close()


def test_first_briefing_offer_silent_when_any_briefing_exists():
    now = _noon()
    uid = _mk_user(created_at=now - timedelta(days=10))
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Plan the trip", status="pending"))
        _morning(db, uid)
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_first_briefing_offer(ctx) is None
    finally:
        db.close()


# --- sig_empty_week ---------------------------------------------------------

def test_empty_week_fires_for_calendar_user_with_a_clear_week():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        old = now - timedelta(days=30)
        db.add(models.CalendarEvent(owner_id=uid, title="Old thing",
                                    start_time=old, end_time=old + timedelta(hours=1)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        n = nudges.sig_empty_week(ctx)
        assert n is not None and n.kind == "offer_rest"
        assert "seven days" in n.draft and "Master Wayne" in n.draft
    finally:
        db.close()


def test_empty_week_silent_when_calendar_never_used():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_empty_week(ctx) is None
    finally:
        db.close()


def test_empty_week_silent_when_event_due_within_the_week():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        soon = now + timedelta(days=2)
        db.add(models.CalendarEvent(owner_id=uid, title="Soon thing",
                                    start_time=soon, end_time=soon + timedelta(hours=1)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_empty_week(ctx) is None
    finally:
        db.close()


# --- sig_note_followup ------------------------------------------------------

def test_note_followup_fires_on_an_untouched_note():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatNote(owner_id=uid, title="Books to read",
                              updated_at=now - timedelta(days=35)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        n = nudges.sig_note_followup(ctx)
        assert n is not None and n.kind == "offer_note"
        assert "Books to read" in n.draft and "5 weeks" in n.draft
    finally:
        db.close()


def test_note_followup_silent_for_pinned_note():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatNote(owner_id=uid, title="Books to read", is_pinned=True,
                              updated_at=now - timedelta(days=35)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_note_followup(ctx) is None
    finally:
        db.close()


def test_note_followup_silent_for_recently_updated_note():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatNote(owner_id=uid, title="Books to read",
                              updated_at=now - timedelta(days=2)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_note_followup(ctx) is None
    finally:
        db.close()


# --- sig_capture_prompt -----------------------------------------------------

def test_capture_prompt_fires_after_a_quiet_stretch():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Older capture", status="pending",
                                 created_at=now - timedelta(days=10)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        n = nudges.sig_capture_prompt(ctx)
        assert n is not None and n.kind == "offer_capture"
        assert "10 days" in n.draft
    finally:
        db.close()


def test_capture_prompt_silent_when_something_captured_recently():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Fresh capture", status="pending",
                                 created_at=now - timedelta(days=2)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_capture_prompt(ctx) is None
    finally:
        db.close()


# --- sig_focus_rhythm -------------------------------------------------------

def test_focus_rhythm_fires_ahead_of_the_peak_hour():
    now = _at(8)
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _focus_at(db, uid, hour=9, count=12, ref=now)
        db.commit()
        ctx = nudges.build_context(db, user, now)
        n = nudges.sig_focus_rhythm(ctx)
        assert n is not None and n.kind == "offer_rhythm"
        assert "09:00" in n.draft
    finally:
        db.close()


def test_focus_rhythm_silent_with_too_few_sessions():
    now = _at(8)
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _focus_at(db, uid, hour=9, count=5, ref=now)
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_focus_rhythm(ctx) is None
    finally:
        db.close()


def test_focus_rhythm_silent_once_past_the_peak_hour():
    now = _at(10)
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _focus_at(db, uid, hour=9, count=12, ref=now)
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_focus_rhythm(ctx) is None
    finally:
        db.close()


# --- sig_long_open_mission --------------------------------------------------

def test_long_open_mission_fires_on_a_forgotten_mission():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        created = now - timedelta(days=90)
        db.add(models.BatMission(owner_id=uid, title="Learn piano", status="pending",
                                 focus_minutes=0, created_at=created))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        n = nudges.sig_long_open_mission(ctx)
        assert n is not None and n.kind == "offer_prune"
        assert "Learn piano" in n.draft
        assert created.strftime("%B") in n.draft
    finally:
        db.close()


def test_long_open_mission_silent_when_it_has_focus_minutes():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Learn piano", status="pending",
                                 focus_minutes=45,
                                 created_at=now - timedelta(days=90)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_long_open_mission(ctx) is None
    finally:
        db.close()


def test_long_open_mission_silent_when_recently_created():
    now = _noon()
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Learn piano", status="pending",
                                 focus_minutes=0,
                                 created_at=now - timedelta(days=10)))
        db.commit()
        ctx = nudges.build_context(db, user, now)
        assert nudges.sig_long_open_mission(ctx) is None
    finally:
        db.close()


# --- _theme_labels ----------------------------------------------------------

def test_theme_labels_counts_tags_and_categories_excluding_alfred_memory():
    missions = [SimpleNamespace(tags="gardening", category=None, title="")
                for _ in range(nudges.MIN_THEME_COUNT)]
    notes = [
        SimpleNamespace(tags="gardening", category="", title=""),
        SimpleNamespace(tags="alfred-memory", category="", title=""),
        SimpleNamespace(tags="", category="fitness", title=""),
        SimpleNamespace(tags="", category="fitness", title=""),
        SimpleNamespace(tags="", category="fitness", title=""),
    ]
    labels = dict(nudges._theme_labels(missions, notes))
    assert labels["gardening"] == nudges.MIN_THEME_COUNT + 1
    assert labels["fitness"] == nudges.MIN_THEME_COUNT
    assert "alfred-memory" not in labels


def test_theme_labels_drops_labels_below_threshold():
    missions = [SimpleNamespace(tags="gardening", category=None, title="")
                for _ in range(nudges.MIN_THEME_COUNT - 1)]
    result = nudges._theme_labels(missions, [])
    assert all(count >= nudges.MIN_THEME_COUNT for _, count in result)
    assert "gardening" not in [label for label, _ in result]


def test_theme_labels_falls_back_to_title_words_and_respects_threshold():
    enough = [SimpleNamespace(tags="", category=None, title="Gardening plan")
              for _ in range(nudges.MIN_THEME_COUNT)]
    assert dict(nudges._theme_labels(enough, [])).get("gardening") == nudges.MIN_THEME_COUNT

    few = [SimpleNamespace(tags="", category=None, title="Astronomy night")
           for _ in range(nudges.MIN_THEME_COUNT - 1)]
    assert dict(nudges._theme_labels(few, [])).get("astronomy") is None
