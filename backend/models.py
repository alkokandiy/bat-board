from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class BatAccount(Base):
    __tablename__ = "bat_account"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    points = Column(Integer, default=0, nullable=False)
    bat_level = Column(String, default="The Orphan", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    missions = relationship("BatMission", back_populates="owner", cascade="all, delete-orphan")
    habits = relationship("BatHabit", back_populates="owner", cascade="all, delete-orphan")
    logs = relationship("BatLog", back_populates="owner", cascade="all, delete-orphan")
    focus_sessions = relationship("BatFocus", back_populates="owner", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="owner", cascade="all, delete-orphan")


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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="habits")
    completion_logs = relationship("HabitCompletionLog", back_populates="habit", cascade="all, delete-orphan")


class HabitCompletionLog(Base):
    __tablename__ = "habit_completion_logs"

    id = Column(Integer, primary_key=True, index=True)
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    habit_id = Column(Integer, ForeignKey("bat_habits.id", ondelete="CASCADE"), nullable=False)
    habit = relationship("BatHabit", back_populates="completion_logs")


class BatLog(Base):
    __tablename__ = "bat_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    event_type = Column(String, nullable=False)
    details = Column(String, nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="logs")


class BatFocus(Base):
    __tablename__ = "bat_focus"

    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="calendar_events")
    mission = relationship("BatMission", back_populates="calendar_events")
