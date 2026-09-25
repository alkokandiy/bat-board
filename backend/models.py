from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class BatAccount(Base):
    __tablename__ = "bat_account"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    points = Column(Integer, default=0, nullable=False)
    bat_level = Column(String, default="The Orphan", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
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
    soundtrack_metadata = Column(String, nullable=True)

    mission_id = Column(Integer, ForeignKey("bat_missions.id", ondelete="SET NULL"), nullable=True)
    mission = relationship("BatMission")
    habit_id = Column(Integer, ForeignKey("bat_habits.id", ondelete="SET NULL"), nullable=True)
    habit = relationship("BatHabit")

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


class BatAlfredUsage(Base):
    """Per-user daily message counter (quota guard)."""

    __tablename__ = "bat_alfred_usage"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(String, nullable=False)  # YYYY-MM-DD (UTC)
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
