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
    bat_level = Column(String, default="Gotham Recruit", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    missions = relationship("BatMission", back_populates="owner", cascade="all, delete-orphan")
    habits = relationship("BatHabit", back_populates="owner", cascade="all, delete-orphan")
    logs = relationship("BatLog", back_populates="owner", cascade="all, delete-orphan")
    focus_sessions = relationship("BatFocus", back_populates="owner", cascade="all, delete-orphan")


class BatMission(Base):
    __tablename__ = "bat_missions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    due_date = Column(DateTime, nullable=True)
    priority = Column(String, default="medium", nullable=False)
    status = Column(String, default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="missions")


class BatHabit(Base):
    __tablename__ = "bat_habits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    frequency = Column(String, default="daily", nullable=False)
    streak = Column(Integer, default=0, nullable=False)
    last_completed = Column(DateTime, nullable=True)
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

    owner_id = Column(Integer, ForeignKey("bat_account.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("BatAccount", back_populates="focus_sessions")