"""Render small PNG visuals of the user's real data, for Telegram delivery.

Pillow only (no browser, no system fonts — uses Pillow's bundled default
font), so it runs on the slim production image. Everything is drawn from the
user's own records in their timezone; nothing is invented.
"""

import io
from datetime import timedelta

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

import models
from services.timezones import day_bounds_utc, local_date, local_today, user_tz

# bat-board palette
BG = (10, 15, 28)
PANEL = (16, 23, 40)
GOLD = (255, 215, 0)
GOLD_DIM = (120, 100, 20)
TEXT = (226, 232, 240)
MUTED = (120, 134, 160)
GRID = (32, 42, 66)
RED = (239, 68, 68)
GREEN = (74, 222, 128)
SS = 2  # supersample factor for crisp text/edges


def _font(size):
    return ImageFont.load_default(size=size * SS)


def _canvas(w, h):
    img = Image.new("RGB", (w * SS, h * SS), BG)
    return img, ImageDraw.Draw(img)


def _finish(img, w, h):
    img = img.resize((w, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _text(d, xy, s, font, fill=TEXT, anchor="la"):
    d.text((xy[0] * SS, xy[1] * SS), s, font=font, fill=fill, anchor=anchor)


def _fmt_minutes(m):
    h, mm = divmod(int(m), 60)
    return f"{h}h {mm}m" if h else f"{mm}m"


# --- focus week chart -------------------------------------------------------

def render_focus_week(db: Session, user: models.BatAccount):
    tz = user_tz(user)
    today = local_today(user)
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    start_utc = day_bounds_utc(days[0], tz)[0]
    end_utc = day_bounds_utc(days[-1], tz)[1]

    sessions = (
        db.query(models.BatFocus)
        .filter(
            models.BatFocus.owner_id == user.id,
            models.BatFocus.end_time.isnot(None),
            models.BatFocus.duration_minutes > 0,
            models.BatFocus.end_time >= start_utc,
            models.BatFocus.end_time < end_utc,
        )
        .all()
    )
    per_day = {d: 0 for d in days}
    for s in sessions:
        d = local_date(s.end_time, tz)
        if d in per_day:
            per_day[d] += s.duration_minutes
    totals = [per_day[d] for d in days]
    total = sum(totals)
    peak = max(totals) or 1
    # current streak of days (ending today) with any focus
    streak = 0
    for d in reversed(days):
        if per_day[d] > 0:
            streak += 1
        else:
            break

    W, H = 720, 400
    img, d = _canvas(W, H)
    f_title, f_big, f_lbl, f_sm = _font(22), _font(34), _font(15), _font(13)
    _text(d, (28, 22), "FOCUS  ·  LAST 7 DAYS", f_title, GOLD)
    _text(d, (W - 28, 26), f"{_fmt_minutes(total)} total", f_lbl, MUTED, anchor="ra")

    # chart area
    cx0, cy0, cx1, cy1 = 40, 90, W - 40, H - 70
    for i in range(5):
        y = cy0 + (cy1 - cy0) * i / 4
        d.line([(cx0 * SS, y * SS), (cx1 * SS, y * SS)], fill=GRID, width=1 * SS)
    n = len(days)
    slot = (cx1 - cx0) / n
    bw = slot * 0.54
    for i, day in enumerate(days):
        v = per_day[day]
        bx = cx0 + slot * i + (slot - bw) / 2
        bh = (cy1 - cy0) * (v / peak)
        top = cy1 - bh
        is_today = day == today
        color = GOLD if v > 0 else GRID
        d.rectangle([bx * SS, top * SS, (bx + bw) * SS, cy1 * SS], fill=color)
        if v > 0:
            _text(d, (bx + bw / 2, top - 6), _fmt_minutes(v), f_sm, TEXT, anchor="mb")
        lbl = day.strftime("%a")
        _text(d, (bx + bw / 2, cy1 + 8), lbl, f_lbl, GOLD if is_today else MUTED, anchor="ma")

    # footer: streak
    _text(d, (28, H - 34), f"Current streak: {streak} day{'s' if streak != 1 else ''}",
          f_lbl, GREEN if streak else MUTED)
    caption = f"Focus, last 7 days — {_fmt_minutes(total)} total, {streak}-day streak."
    return _finish(img, W, H), caption


# --- daily brief card -------------------------------------------------------

def render_daily_brief(db: Session, user: models.BatAccount):
    from datetime import datetime, timezone
    tz = user_tz(user)
    today = local_today(user)
    d_start, d_end = day_bounds_utc(today, tz)  # local-day bounds (events/habits)
    # Due dates are calendar dates stored as UTC midnight — match on the UTC date.
    due_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    due_end = due_start + timedelta(days=1)

    due = (
        db.query(models.BatMission)
        .filter(models.BatMission.owner_id == user.id,
                models.BatMission.due_date >= _naive(due_start),
                models.BatMission.due_date < _naive(due_end))
        .all()
    )
    due_done = sum(1 for m in due if m.status == "completed")
    overdue = (
        db.query(models.BatMission)
        .filter(models.BatMission.owner_id == user.id,
                models.BatMission.status == "pending",
                models.BatMission.due_date.isnot(None),
                models.BatMission.due_date < _naive(due_start))
        .count()
    )

    # habits not yet done today
    habits = db.query(models.BatHabit).filter(models.BatHabit.owner_id == user.id).all()
    habits_left = sum(
        1 for h in habits
        if not (h.last_completed and local_date(h.last_completed, tz) == today)
    )

    # next calendar event today or later
    next_event = (
        db.query(models.CalendarEvent)
        .filter(models.CalendarEvent.owner_id == user.id,
                models.CalendarEvent.start_time >= _naive(d_start))
        .order_by(models.CalendarEvent.start_time.asc())
        .first()
    )
    # nearest upcoming countdown
    next_cd = (
        db.query(models.BatCountdown)
        .filter(models.BatCountdown.owner_id == user.id,
                models.BatCountdown.target_date >= _naive(d_start))
        .order_by(models.BatCountdown.target_date.asc())
        .first()
    )

    W, H = 720, 440
    img, d = _canvas(W, H)
    f_date, f_h, f_row, f_small, f_num = _font(16), _font(20), _font(17), _font(13), _font(30)
    _text(d, (28, 22), today.strftime("%A, %B %-d"), f_h, GOLD)
    _text(d, (W - 28, 26), f"{user.points:,} BP · {user.bat_level}", f_small, MUTED, anchor="ra")

    # two stat tiles
    def tile(x, label, value, sub, color=GOLD):
        d.rounded_rectangle([x * SS, 70 * SS, (x + 318) * SS, 170 * SS], radius=10 * SS, fill=PANEL)
        _text(d, (x + 20, 86), label, f_small, MUTED)
        _text(d, (x + 20, 104), value, f_num, color)
        _text(d, (x + 20, 146), sub, f_small, MUTED)

    tile(28, "MISSIONS DUE TODAY", f"{due_done}/{len(due)}",
         (f"{overdue} overdue" if overdue else "nothing overdue"),
         GREEN if due and due_done == len(due) else GOLD)
    tile(374, "HABITS TO DO", str(habits_left),
         ("all done" if habits_left == 0 and habits else f"of {len(habits)}"),
         GREEN if habits and habits_left == 0 else GOLD)

    # rows: next event, next countdown
    y = 200
    d.rounded_rectangle([28 * SS, y * SS, (W - 28) * SS, (H - 24) * SS], radius=10 * SS, fill=PANEL)
    ry = y + 22

    def row(label, value, vcolor=TEXT):
        nonlocal ry
        _text(d, (48, ry), label, f_small, MUTED)
        _text(d, (W - 48, ry - 2), value, f_row, vcolor, anchor="ra")
        ry += 46

    if next_event:
        et = local_date(next_event.start_time, tz)
        when = "today" if et == today else et.strftime("%a %-d")
        tstr = next_event.start_time.strftime("%H:%M") if next_event.start_time else ""
        row("Next event", f"{next_event.title[:28]} · {when} {tstr}".strip())
    else:
        row("Next event", "nothing scheduled", MUTED)

    if next_cd:
        from services.countdown_service import days_remaining_for
        dleft = days_remaining_for(next_cd.target_date)
        row("Next countdown", f"{next_cd.title[:28]} · {dleft}d", GOLD if dleft <= 7 else TEXT)
    else:
        row("Next countdown", "none", MUTED)

    # today's missions preview (up to 3 pending)
    pending = [m for m in due if m.status != "completed"][:3]
    if pending:
        _text(d, (48, ry), "Due today", f_small, MUTED)
        ry += 26
        for m in pending:
            _text(d, (60, ry), "•  " + m.title[:40], f_small, TEXT)
            ry += 24

    caption = (
        f"Daily brief · {due_done}/{len(due)} missions done"
        + (f", {overdue} overdue" if overdue else "")
        + f" · {habits_left} habit{'s' if habits_left != 1 else ''} left."
    )
    return _finish(img, W, H), caption


def _naive(dt):
    return dt.replace(tzinfo=None)
