from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy import DateTime as _SQLDateTime
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator
from datetime import datetime, timezone
from database import Base


class DateTime(TypeDecorator):
    """Timestamp stored as naive UTC, always returned timezone-aware (UTC).

    Columns are TIMESTAMP WITHOUT TIME ZONE. Without this, values came back
    naive and were serialized without an offset, so browsers parsed UTC
    times as local time (events/countdowns shifted by the user's offset and
    drifted on every edit), and naive-vs-aware arithmetic crashed. Aware
    inputs in any offset are converted to UTC; naive inputs are taken as UTC.
    """

    impl = _SQLDateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value



class BatAccount(Base):
    __tablename__ = "bat_account"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    points = Column(Integer, default=0, nullable=False)
    bat_level = Column(String, default="The Recruit", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # IANA zone name (e.g. "Asia/Tashkent"); day boundaries are computed in it.
    timezone = Column(String, nullable=True)
    # How Alfred addresses this user (e.g. "Master Al-Kokandiy"); None = username.
    alfred_address = Column(String, nullable=True)
    # Proactive check-ins ("nudges"): Alfred reaching out unprompted when
    # something on the board deserves a word. Quiet hours are local HH:MM.
    nudges_enabled = Column(Boolean, default=True, server_default="1", nullable=False)
    nudge_quiet_start = Column(String, nullable=True)   # default 22:00
    nudge_quiet_end = Column(String, nullable=True)     # default 08:00
    nudges_per_day = Column(Integer, nullable=True)     # default 3
    # Embedded in every JWT ("tv"); bumping it revokes all issued tokens.
    token_version = Column(Integer, default=0, server_default="0", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    missions = relationship("BatMission", back_populates="owner", cascade="all, delete-orphan")
    habits = relationship("BatHabit", back_populates="owner", cascade="all, delete-orphan")
    logs = relationship("BatLog", back_populates="owner", cascade="all, delete-orphan")
    focus_sessions = relationship("BatFocus", back_populates="owner", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="owner", cascade="all, delete-orphan")
    notes = relationship("BatNote", back_populates="owner", cascade="all, delete-orphan")
    countdowns = relationship("BatCountdown", back_populates="owner", cascade="all, delete-orphan")
    personal_access_tokens = relationship("BatPersonalAccessToken", back_populates="owner", cascade="all, delete-orphan")
    telegram_link_codes = relationship("BatTelegramLinkCode", back_populates="owner", cascade="all, delete-orphan")
    alfred_messages = relationship("BatAlfredMessage", back_populates="owner", cascade="all, delete-orphan")
    alfred_sessions = relationship("BatAlfredSession", back_populates="owner", cascade="all, delete-orphan",
                                    foreign_keys="[BatAlfredSession.owner_id]")
    pending_alfred_actions = relationship("BatPendingAlfredAction", back_populates="owner", cascade="all, delete-orphan")
    alfred_usage = relationship("BatAlfredUsage", back_populates="owner", cascade="all, delete-orphan")
    ai_provider_config = relationship("BatAIProviderConfig", back_populates="owner", cascade="all, delete-orphan", uselist=False)
    briefings = relationship("BatBriefing", back_populates="owner", cascade="all, delete-orphan")
    reminders = relationship("BatReminder", back_populates="owner", cascade="all, delete-orphan")
    work_tasks = relationship("BatWorkTask", back_populates="owner", cascade="all, delete-orphan")
    work_notes = relationship("BatWorkNote", back_populates="owner", cascade="all, delete-orphan")

    active_alfred_session_id = Column(Integer, ForeignKey("bat_alfred_sessions.id", ondelete="SET NULL"), nullable=True)


class BatMission(Base):
    __tablename__ = "bat_missions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    due_date = Column(DateTime, nullable=True)
    priority = Column(String, default="medium", nullable=False)
    status = Column(String, default="pending", nullable=False)
    tags = Column(String, nullable=True)
    is_pinned = Column(Boolean, default=False, nullable=False)
    is_dismissed = Column(Boolean, default=False, nullable=False)
    location = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    subtasks = Column(String, nullable=True)
    focus_minutes = Column(Integer, default=0, nullable=False)
    completed_focus_sessions = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="missions")
    calendar_events = relationship("CalendarEvent", back_populates="mission")


class BatHabit(Base):
    __tablename__ = "bat_habits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    frequency = Column(String, default="daily", nullable=False)
    streak = Column(Integer, default=0, nullable=False)
    last_completed = Column(DateTime, nullable=True)
    focus_minutes = Column(Integer, default=0, nullable=False)
    target_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="habits")
    completion_logs = relationship("HabitCompletionLog", back_populates="habit", cascade="all, delete-orphan")


class HabitCompletionLog(Base):
    __tablename__ = "habit_completion_logs"

    id = Column(Integer, primary_key=True, index=True)
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    habit_id = Column(Integer, ForeignKey("bat_habits.id", ondelete="CASCADE"), nullable=False)
    habit = relationship("BatHabit", back_populates="completion_logs")


class BatLog(Base):
    __tablename__ = "bat_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    event_type = Column(String, nullable=False)
    details = Column(String, nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="logs")


class BatFocus(Base):
    __tablename__ = "bat_focus"

    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    # Set for a timed (Telegram) session: the cron tick auto-ends it this many
    # minutes after start and pings the user. NULL = untimed (web stopwatch).
    planned_minutes = Column(Integer, nullable=True)
    soundtrack_metadata = Column(String, nullable=True)
    # Timer visual mode when the session started (see FOCUS_MODES); NULL for
    # sessions recorded before this column existed.
    mode = Column(String, nullable=True)

    mission_id = Column(Integer, ForeignKey("bat_missions.id", ondelete="SET NULL"), nullable=True)
    mission = relationship("BatMission")
    habit_id = Column(Integer, ForeignKey("bat_habits.id", ondelete="SET NULL"), nullable=True)
    habit = relationship("BatHabit")
    # Work-track link. A session on a work task logs time but awards NO points.
    work_task_id = Column(Integer, ForeignKey("bat_work_tasks.id", ondelete="SET NULL"), nullable=True)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="focus_sessions")


class CalendarEvent(Base):
    __tablename__ = "bat_calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    color = Column(String, nullable=True)
    mission_id = Column(Integer, ForeignKey("bat_missions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="calendar_events")
    mission = relationship("BatMission", back_populates="calendar_events")


class BatNote(Base):
    __tablename__ = "bat_notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="", nullable=False)
    body = Column(String, nullable=True)
    category = Column(String, nullable=True)
    # Comma-separated string, matching BatMission.tags convention (see
    # main.py which splits m.tags on ","). Single free-text `category`
    # remains the primary grouping field from the original frontend.
    tags = Column(String, nullable=True)
    is_pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="notes")


class BatCountdown(Base):
    __tablename__ = "bat_countdowns"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    target_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="countdowns")


class BatPersonalAccessToken(Base):
    __tablename__ = "bat_pats"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Telegram — Alfred", nullable=False)
    # SHA-256 hex of the raw token. The raw value is shown once at creation
    # (or never, in the Telegram flow) and never stored in plaintext.
    token_hash = Column(String, nullable=False)
    telegram_chat_id = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False, nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="personal_access_tokens")


class BatTelegramLinkCode(Base):
    """Short-lived linking codes. Table-backed (not in-memory) so codes work
    across gunicorn workers — the generate endpoint and the webhook may run
    on different processes."""

    __tablename__ = "bat_telegram_link_codes"

    id = Column(Integer, primary_key=True, index=True)
    # SHA-256 hex of the 6-digit code; the plain code is only ever returned
    # once to the browser that requested it.
    code_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="telegram_link_codes")


class BatAlfredSession(Base):
    """A distinct conversation thread, shared across Telegram and web UI."""

    __tablename__ = "bat_alfred_sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="alfred_sessions", foreign_keys=[owner_id])
    messages = relationship("BatAlfredMessage", back_populates="session", cascade="all, delete-orphan",
                            foreign_keys="[BatAlfredMessage.session_id]")


class BatAlfredMessage(Base):
    """Conversation memory: only human-readable turns are stored, never
    intermediate tool-call/tool-result exchanges."""

    __tablename__ = "bat_alfred_messages"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="alfred_messages")
    session_id = Column(Integer, ForeignKey("bat_alfred_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    session = relationship("BatAlfredSession", back_populates="messages")


class BatPendingAlfredAction(Base):
    """Deterministic confirmation gate for destructive actions.
    One pending action per user max (owner_id unique)."""

    __tablename__ = "bat_pending_alfred_actions"

    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, nullable=False)
    action_args = Column(String, nullable=False)  # JSON-encoded dict
    confirmation_message = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    owner = relationship("BatAccount", back_populates="pending_alfred_actions")


class BatTelegramSeenUpdate(Base):
    """Dedupe for Telegram deliveries: update_id primary key, so the
    DB-level unique constraint (not app logic) makes this race-safe
    across gunicorn workers."""

    __tablename__ = "bat_telegram_seen_updates"

    update_id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class BatTelegramLinkAttempt(Base):
    """Failed link-code attempts per Telegram chat (brute-force guard).

    Table-backed so the limit holds across gunicorn workers."""

    __tablename__ = "bat_telegram_link_attempts"

    chat_id = Column(String, primary_key=True)
    failures = Column(Integer, default=0, nullable=False)
    window_started_at = Column(DateTime, nullable=False)


class BatAlfredUsage(Base):
    """Per-user daily message counter (quota guard). One row per (user, day)."""

    __tablename__ = "bat_alfred_usage"
    __table_args__ = (UniqueConstraint("owner_id", "day", name="uq_bat_alfred_usage_owner_day"),)

    id = Column(Integer, primary_key=True, index=True)
    day = Column(String, nullable=False)  # YYYY-MM-DD in the user's timezone
    count = Column(Integer, default=0, nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="alfred_usage")


class BatAIProviderConfig(Base):
    """Per-user LLM provider config (BYOK). One row per user, key encrypted."""

    __tablename__ = "bat_ai_provider_configs"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False)  # gemini|anthropic|openai|deepseek|kimi
    model_name = Column(String, nullable=False)  # user-supplied, never hardcoded
    api_key_encrypted = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    owner = relationship("BatAccount", back_populates="ai_provider_config")


# --- Phase F: proactive briefings & reminders -------------------------------
# Alfred pushes these to the user over Telegram on a schedule. A protected
# cron endpoint (POST /api/internal/cron/tick) fires anything due in the
# user's own timezone; the *_log tables make firing exactly-once so repeated
# or overlapping ticks are harmless (insert-first, skip on conflict).

BRIEFING_KINDS = ("morning", "night")
REMINDER_RECURRENCES = ("once", "daily", "weekly", "monthly")


class BatBriefing(Base):
    """A user's morning or night briefing config. One row per (owner, kind)."""

    __tablename__ = "bat_briefings"
    __table_args__ = (UniqueConstraint("owner_id", "kind", name="uq_bat_briefings_owner_kind"),)

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False)  # "morning" | "night"
    enabled = Column(Boolean, default=True, nullable=False)
    send_time = Column(String, nullable=False)  # "HH:MM" in the owner's timezone

    # Content sections (all default on except news, which needs topics chosen).
    include_missions = Column(Boolean, default=True, nullable=False)
    include_habits = Column(Boolean, default=True, nullable=False)
    include_events = Column(Boolean, default=True, nullable=False)
    include_focus = Column(Boolean, default=True, nullable=False)
    include_news = Column(Boolean, default=False, nullable=False)
    news_topics = Column(String, nullable=True)  # comma-separated, e.g. "AI, cybersecurity"

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="briefings")


class BatBriefingLog(Base):
    """One row per briefing actually sent, keyed by local date for exactly-once."""

    __tablename__ = "bat_briefing_log"
    __table_args__ = (UniqueConstraint("owner_id", "kind", "local_date", name="uq_bat_briefing_log_owner_kind_date"),)

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False)
    local_date = Column(String, nullable=False)  # YYYY-MM-DD in the owner's timezone
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)


class BatReminder(Base):
    """A user-defined reminder Alfred pushes on a schedule (take medicine, etc.)."""

    __tablename__ = "bat_reminders"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)

    recurrence = Column(String, nullable=False)  # once | daily | weekly | monthly
    send_time = Column(String, nullable=False)   # "HH:MM" in the owner's timezone
    weekdays = Column(String, nullable=True)     # weekly: CSV of 0-6 (Mon=0)
    day_of_month = Column(Integer, nullable=True)  # monthly: 1-31 (clamped to month end)
    run_date = Column(String, nullable=True)     # once: "YYYY-MM-DD" local
    # Optional last day, inclusive ("for one month", "until 1 Dec"). NULL means
    # it runs indefinitely. Past this date the reminder stops and disables itself.
    ends_on = Column(String, nullable=True)      # "YYYY-MM-DD" local

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="reminders")


class BatReminderLog(Base):
    """One row per reminder occurrence actually sent, for exactly-once firing."""

    __tablename__ = "bat_reminder_log"
    __table_args__ = (UniqueConstraint("reminder_id", "local_date", name="uq_bat_reminder_log_reminder_date"),)

    id = Column(Integer, primary_key=True, index=True)
    local_date = Column(String, nullable=False)  # YYYY-MM-DD in the owner's timezone
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    reminder_id = Column(Integer, ForeignKey("bat_reminders.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)


class BatNudgeLog(Base):
    """One row per proactive check-in sent. `nudge_key` encodes the specific
    occasion (e.g. "countdown:12:7d", "drift:2026-10-08"), so the UNIQUE
    constraint makes each occasion fire exactly once and doubles as the
    cooldown record."""

    __tablename__ = "bat_nudge_log"
    __table_args__ = (UniqueConstraint("owner_id", "nudge_key", name="uq_bat_nudge_log_owner_key"),)

    id = Column(Integer, primary_key=True, index=True)
    nudge_key = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    local_date = Column(String, nullable=False)   # YYYY-MM-DD in the owner's zone
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)


# --- Corporate / work track -------------------------------------------------
# Deliberately a SEPARATE domain from missions, not a flag on them. Work must
# never leak into personal lists, counts, briefings, nudges, stats or Bat
# Points — keeping it in its own tables makes that true by construction rather
# than by remembering to filter in a dozen queries. Bat Points are a measure of
# the person, not of the job, so nothing here ever awards them.

WORK_STATUSES = ("todo", "doing", "blocked", "done")
WORK_NOTE_KINDS = ("note", "learning", "reflection")


class BatWorkTask(Base):
    __tablename__ = "bat_work_tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    status = Column(String, default="todo", nullable=False)   # see WORK_STATUSES
    project = Column(String, nullable=True)                   # free-text grouping
    due_date = Column(DateTime, nullable=True)
    # Minutes of focus logged against this task. No points are awarded for it.
    focus_minutes = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="work_tasks")


class BatWorkNote(Base):
    """The work journal: plain notes, things learned, and end-of-period
    reflections. Kept apart from the user's personal notes and from Alfred's
    private memory so corporate context never colours personal context."""

    __tablename__ = "bat_work_notes"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, default="note", nullable=False)     # see WORK_NOTE_KINDS
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    work_task_id = Column(Integer, ForeignKey("bat_work_tasks.id", ondelete="SET NULL"), nullable=True)
    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("BatAccount", back_populates="work_notes")
