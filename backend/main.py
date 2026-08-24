import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional, Literal

import structlog
from fastapi import FastAPI, Depends, HTTPException, status, Request, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from pydantic import BaseModel, Field, ConfigDict

import models
from database import engine, get_db, create_db_tables
from config import get_settings
from auth import (
    get_current_active_user, authenticate_user, create_access_token,
    create_refresh_token, decode_refresh_token, get_password_hash,
    UserCreate, UserResponse, Token,
)

settings = get_settings()

# --- Structured Logging ---
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if settings.log_format == "json" else structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

# --- Rate Limiting ---
limiter = Limiter(key_func=get_remote_address)

# --- Database Initialization ---
try:
    create_db_tables()
    logger.info("database_tables_ready")
except Exception as e:
    logger.error("database_init_failed", error=str(e))
    raise

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url="/api/redoc" if settings.environment != "production" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Logging Middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    return response

# --- Global Exception Handlers ---
@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error("database_error", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "A database error occurred."},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_error", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred."},
    )

# --- Tier Calculation Helper ---
def calculate_bat_level(points: int) -> str:
    if points < 2000:
        return "The Orphan"
    elif points < 5000:
        return "The Vigilante"
    elif points < 10000:
        return "The Detective"
    elif points < 20000:
        return "Son of Gotham"
    elif points < 35000:
        return "The Caped Crusader"
    elif points < 55000:
        return "Heir of the Demon"
    elif points < 80000:
        return "The Dark Knight"
    elif points < 120000:
        return "Faris al-Khorasan"
    elif points < 180000:
        return "Sword of the Ummah"
    else:
        return "Dark Knight of Khorasan"

# --- Auto Log Helper ---
def auto_log_event(db: Session, owner_id: int, event_type: str, details_dict: dict):
    log_entry = models.BatLog(
        owner_id=owner_id,
        event_type=event_type,
        details=json.dumps(details_dict)
    )
    db.add(log_entry)
    db.flush()

# --- Pydantic Schemas ---
class BatAccountSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    points: int
    bat_level: str
    created_at: datetime

class BatAccountUpdate(BaseModel):
    username: Optional[str] = None
    points_delta: Optional[int] = None

class BatMissionBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    due_date: Optional[datetime] = None
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["pending", "completed", "dismissed"] = "pending"
    tags: Optional[str] = None
    is_pinned: bool = False
    is_dismissed: bool = False
    location: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    subtasks: Optional[str] = None

class BatMissionCreate(BatMissionBase):
    pass

class BatMissionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    due_date: Optional[datetime] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    status: Optional[Literal["pending", "completed", "dismissed"]] = None
    tags: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_dismissed: Optional[bool] = None
    location: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    subtasks: Optional[str] = None

class BatMissionSchema(BatMissionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    owner_id: int
    focus_minutes: int = 0
    completed_focus_sessions: int = 0

class CalendarEventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    start_time: datetime
    end_time: Optional[datetime] = None
    color: Optional[str] = None
    mission_id: Optional[int] = None

class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    color: Optional[str] = None
    mission_id: Optional[int] = None

class CalendarEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    color: Optional[str] = None
    mission_id: Optional[int] = None
    created_at: datetime
    owner_id: int

class BatHabitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    frequency: Literal["daily", "weekly", "monthly"] = "daily"

class BatHabitCreate(BatHabitBase):
    pass

class BatHabitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    frequency: Optional[Literal["daily", "weekly", "monthly"]] = None
    streak: Optional[int] = None
    target_date: Optional[datetime] = None

class BatHabitSchema(BatHabitBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    streak: int
    last_completed: Optional[datetime] = None
    focus_minutes: int = 0
    target_date: Optional[datetime] = None
    created_at: datetime
    owner_id: int

class BatLogBase(BaseModel):
    event_type: str
    details: str

class BatLogCreate(BatLogBase):
    pass

class BatLogSchema(BatLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    owner_id: int

class BatFocusCreate(BaseModel):
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    soundtrack_metadata: Optional[str] = None
    mission_id: Optional[int] = None
    habit_id: Optional[int] = None

class BatFocusSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    soundtrack_metadata: Optional[str] = None
    mission_id: Optional[int] = None
    habit_id: Optional[int] = None
    owner_id: int

class StatsBreakdownItem(BaseModel):
    type: str
    id: Optional[int] = None
    name: str
    minutes: int
    sessions: int
    percent: float

class StatsHeatmapCell(BaseModel):
    date: str
    minutes: int

class FocusStatsResponse(BaseModel):
    period: str
    range_start: Optional[str] = None
    range_end: Optional[str] = None
    total_minutes: int
    total_sessions: int
    current_streak_days: int
    breakdown: List[StatsBreakdownItem]
    daily_heatmap: List[StatsHeatmapCell]

class FocusSessionLogItem(BaseModel):
    id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    mission_id: Optional[int] = None
    mission_name: Optional[str] = None
    habit_id: Optional[int] = None
    habit_name: Optional[str] = None

class FocusSessionLogResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[FocusSessionLogItem]

class FocusTrendPoint(BaseModel):
    label: str
    date: str
    minutes: int
    sessions: int

class FocusTrendResponse(BaseModel):
    granularity: str
    points: List[FocusTrendPoint]

class DayStatusDistribution(BaseModel):
    on_time: int
    overdue: int
    uncompleted: int

class DayTypeDistributionItem(BaseModel):
    type: str
    count: int

class DayTagDistributionItem(BaseModel):
    tag: str
    count: int

class DayStatsResponse(BaseModel):
    date: str
    completed_count: int
    total_count: int
    completion_rate: float
    completed_not_due_today: int = 0
    status_distribution: DayStatusDistribution
    type_distribution: List[DayTypeDistributionItem]
    tag_distribution: List[DayTagDistributionItem]

# --- Health Check ---
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# --- Auth Endpoints ---
@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.BatAccount).filter(
        models.BatAccount.username == user_data.username
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    hashed = get_password_hash(user_data.password)
    account = models.BatAccount(
        username=user_data.username,
        hashed_password=hashed,
        points=0,
        bat_level="The Orphan",
    )
    db.add(account)
    try:
        db.flush()
        db.refresh(account)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken")

    auto_log_event(db, account.id, "account_created", {
        "message": f"Bat-Board initiated for {user_data.username}"
    })
    db.commit()

    logger.info("user_registered", username=user_data.username)
    return account

@app.post("/api/auth/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    auto_log_event(db, user.id, "login", {"message": "User logged in"})
    db.commit()
    logger.info("user_login", username=user.username)

    return Token(access_token=access_token, refresh_token=refresh_token)

@app.post("/api/auth/refresh", response_model=Token)
@limiter.limit("10/minute")
def refresh_token(request: Request, refresh_token: str = Body(...), db: Session = Depends(get_db)):
    token_data = decode_refresh_token(refresh_token)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = db.query(models.BatAccount).filter(models.BatAccount.username == token_data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(data={"sub": user.username})
    new_refresh_token = create_refresh_token(data={"sub": user.username})

    return Token(access_token=access_token, refresh_token=new_refresh_token)

@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: models.BatAccount = Depends(get_current_active_user)):
    current_user.bat_level = calculate_bat_level(current_user.points)
    return current_user

# --- Account Endpoints ---
@app.get("/api/account", response_model=BatAccountSchema)
def get_account(current_user: models.BatAccount = Depends(get_current_active_user)):
    current_user.bat_level = calculate_bat_level(current_user.points)
    return current_user

@app.put("/api/account", response_model=BatAccountSchema)
def update_account(
    payload: BatAccountUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if payload.username is not None:
        existing = db.query(models.BatAccount).filter(
            models.BatAccount.username == payload.username,
            models.BatAccount.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")
        old_username = current_user.username
        current_user.username = payload.username
        auto_log_event(db, current_user.id, "account_update", {"field": "username", "old": old_username, "new": payload.username})

    if payload.points_delta is not None:
        old_points = current_user.points
        current_user.points += payload.points_delta
        if current_user.points < 0:
            current_user.points = 0

        old_level = current_user.bat_level
        current_user.bat_level = calculate_bat_level(current_user.points)

        auto_log_event(db, current_user.id, "points_modified", {
            "points_delta": payload.points_delta,
            "old_points": old_points,
            "new_points": current_user.points,
            "old_level": old_level,
            "new_level": current_user.bat_level
        })

    db.commit()
    db.refresh(current_user)
    return current_user

class ChangePassword(BaseModel):
    current_password: str
    new_password: str

@app.put("/api/account/password", response_model=dict)
def change_password(
    payload: ChangePassword,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    from auth import verify_password, get_password_hash
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = get_password_hash(payload.new_password)
    auto_log_event(db, current_user.id, "password_changed", {"message": "Password changed"})
    db.commit()
    return {"detail": "Password updated successfully"}

@app.post("/api/account/reset-points", response_model=BatAccountSchema)
def reset_points(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    old_points = current_user.points
    old_level = current_user.bat_level
    current_user.points = 0
    current_user.bat_level = calculate_bat_level(0)
    auto_log_event(db, current_user.id, "points_reset", {
        "old_points": old_points,
        "new_points": 0,
        "old_level": old_level,
        "new_level": current_user.bat_level
    })
    db.commit()
    db.refresh(current_user)
    return current_user

# --- Mission Endpoints ---
@app.get("/api/missions", response_model=List[BatMissionSchema])
def list_missions(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return db.query(models.BatMission).filter(models.BatMission.owner_id == current_user.id).all()

@app.post("/api/missions", response_model=BatMissionSchema, status_code=status.HTTP_201_CREATED)
def create_mission(
    mission_data: BatMissionCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    mission = models.BatMission(
        title=mission_data.title,
        description=mission_data.description,
        due_date=mission_data.due_date,
        priority=mission_data.priority,
        status=mission_data.status,
        tags=mission_data.tags,
        is_pinned=mission_data.is_pinned,
        is_dismissed=mission_data.is_dismissed,
        location=mission_data.location,
        notes=mission_data.notes,
        subtasks=mission_data.subtasks,
        owner_id=current_user.id
    )
    db.add(mission)
    db.flush()
    db.refresh(mission)

    auto_log_event(db, current_user.id, "mission_created", {
        "mission_id": mission.id,
        "title": mission.title,
        "priority": mission.priority
    })
    db.commit()

    return mission

@app.put("/api/missions/{mission_id}", response_model=BatMissionSchema)
def update_mission(
    mission_id: int,
    payload: BatMissionUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    mission = db.query(models.BatMission).filter(
        models.BatMission.id == mission_id,
        models.BatMission.owner_id == current_user.id
    ).first()

    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    old_status = mission.status
    old_points = current_user.points
    old_level = current_user.bat_level

    for field in payload.model_fields_set:
        if field == 'status':
            continue
        setattr(mission, field, getattr(payload, field))

    if 'status' in payload.model_fields_set:
        mission.status = payload.status
        if payload.status == "completed" and old_status != "completed":
            mission.completed_at = datetime.now(timezone.utc)
            reward = 10
            if mission.priority == "high":
                reward = 20
            elif mission.priority == "critical":
                reward = 50
            elif mission.priority == "low":
                reward = 5

            current_user.points += reward
            current_user.bat_level = calculate_bat_level(current_user.points)

            auto_log_event(db, current_user.id, "points_modified", {
                "reason": f"Completed mission '{mission.title}'",
                "points_delta": reward,
                "old_points": old_points,
                "new_points": current_user.points,
                "old_level": old_level,
                "new_level": current_user.bat_level
            })
        elif payload.status != "completed" and old_status == "completed":
            mission.completed_at = None
            current_user.points = old_points
            current_user.bat_level = calculate_bat_level(current_user.points)

    db.flush()
    db.refresh(mission)
    db.refresh(current_user)

    auto_log_event(db, current_user.id, "mission_updated", {
        "mission_id": mission.id,
        "title": mission.title,
        "old_status": old_status,
        "new_status": mission.status
    })
    db.commit()

    return mission

@app.delete("/api/missions/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    mission = db.query(models.BatMission).filter(
        models.BatMission.id == mission_id,
        models.BatMission.owner_id == current_user.id
    ).first()

    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    auto_log_event(db, current_user.id, "mission_deleted", {
        "mission_id": mission.id,
        "title": mission.title
    })

    db.delete(mission)
    db.commit()
    return None

# --- Calendar Event Endpoints ---
@app.get("/api/calendar/events", response_model=List[CalendarEventSchema])
def list_calendar_events(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return db.query(models.CalendarEvent).filter(
        models.CalendarEvent.owner_id == current_user.id
    ).order_by(models.CalendarEvent.start_time).all()

@app.post("/api/calendar/events", response_model=CalendarEventSchema, status_code=status.HTTP_201_CREATED)
def create_calendar_event(
    event_data: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if event_data.mission_id:
        mission = db.query(models.BatMission).filter(
            models.BatMission.id == event_data.mission_id,
            models.BatMission.owner_id == current_user.id
        ).first()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

    event = models.CalendarEvent(
        title=event_data.title,
        description=event_data.description,
        start_time=event_data.start_time,
        end_time=event_data.end_time,
        color=event_data.color,
        mission_id=event_data.mission_id,
        owner_id=current_user.id
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event

@app.put("/api/calendar/events/{event_id}", response_model=CalendarEventSchema)
def update_calendar_event(
    event_id: int,
    event_data: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    event = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.id == event_id,
        models.CalendarEvent.owner_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    for field in event_data.model_fields_set:
        if field == 'mission_id':
            if event_data.mission_id is not None:
                mission = db.query(models.BatMission).filter(
                    models.BatMission.id == event_data.mission_id,
                    models.BatMission.owner_id == current_user.id
                ).first()
                if not mission:
                    raise HTTPException(status_code=404, detail="Mission not found")
            event.mission_id = event_data.mission_id
        else:
            setattr(event, field, getattr(event_data, field))

    db.commit()
    db.refresh(event)
    return event

@app.delete("/api/calendar/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    event = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.id == event_id,
        models.CalendarEvent.owner_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()
    return None

# --- Habit Endpoints ---
@app.get("/api/habits", response_model=List[BatHabitSchema])
def list_habits(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return db.query(models.BatHabit).filter(models.BatHabit.owner_id == current_user.id).all()

@app.post("/api/habits", response_model=BatHabitSchema, status_code=status.HTTP_201_CREATED)
def create_habit(
    habit_data: BatHabitCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    habit = models.BatHabit(
        name=habit_data.name,
        description=habit_data.description,
        frequency=habit_data.frequency,
        streak=0,
        owner_id=current_user.id
    )
    db.add(habit)
    db.flush()
    db.refresh(habit)

    auto_log_event(db, current_user.id, "habit_created", {
        "habit_id": habit.id,
        "name": habit.name,
        "frequency": habit.frequency
    })
    db.commit()

    return habit

@app.put("/api/habits/{habit_id}", response_model=BatHabitSchema)
def update_habit(
    habit_id: int,
    payload: BatHabitUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    habit = db.query(models.BatHabit).filter(
        models.BatHabit.id == habit_id,
        models.BatHabit.owner_id == current_user.id
    ).first()

    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    for field in payload.model_fields_set:
        setattr(habit, field, getattr(payload, field))

    db.flush()
    db.refresh(habit)

    auto_log_event(db, current_user.id, "habit_updated", {
        "habit_id": habit.id,
        "name": habit.name
    })
    db.commit()

    return habit

@app.delete("/api/habits/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(
    habit_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    habit = db.query(models.BatHabit).filter(
        models.BatHabit.id == habit_id,
        models.BatHabit.owner_id == current_user.id
    ).first()

    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    auto_log_event(db, current_user.id, "habit_deleted", {
        "habit_id": habit.id,
        "name": habit.name
    })

    db.delete(habit)
    db.commit()
    return None

# --- Habit Check-In ---
@app.post("/api/habits/{habit_id}/check-in", response_model=BatHabitSchema)
def check_in_habit(
    habit_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    habit = db.query(models.BatHabit).filter(
        models.BatHabit.id == habit_id,
        models.BatHabit.owner_id == current_user.id
    ).first()

    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    now = datetime.now(timezone.utc)

    is_new_completion = True
    if habit.last_completed:
        if habit.last_completed.date() == now.date():
            is_new_completion = False

    completion = models.HabitCompletionLog(habit_id=habit.id, completed_at=now)
    db.add(completion)

    if is_new_completion:
        if habit.last_completed:
            delta = now.date() - habit.last_completed.date()
            if delta.days <= 1:
                habit.streak += 1
            else:
                habit.streak = 1
        else:
            habit.streak = 1

        habit.last_completed = now

        streak_bonus = min(habit.streak, 10)
        reward = 5 + streak_bonus

        current_user.points += reward
        old_level = current_user.bat_level
        current_user.bat_level = calculate_bat_level(current_user.points)

        auto_log_event(db, current_user.id, "points_modified", {
            "reason": f"Completed habit '{habit.name}' (Streak: {habit.streak})",
            "points_delta": reward,
            "old_points": current_user.points - reward,
            "new_points": current_user.points,
            "old_level": old_level,
            "new_level": current_user.bat_level
        })

        auto_log_event(db, current_user.id, "habit_checkin", {
            "habit_id": habit.id,
            "name": habit.name,
            "streak": habit.streak,
            "points_awarded": reward
        })
    else:
        auto_log_event(db, current_user.id, "habit_completion_history_logged", {
            "habit_id": habit.id,
            "name": habit.name,
            "note": "Logged completion but streak/reward not re-applied for today"
        })

    db.commit()
    db.refresh(habit)
    db.refresh(current_user)
    return habit

# --- Logs Endpoints ---
@app.get("/api/logs", response_model=List[BatLogSchema])
def list_logs(
    limit: int = Query(50, ge=1, le=200),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    q = db.query(models.BatLog).filter(models.BatLog.owner_id == current_user.id)
    if start_date:
        q = q.filter(models.BatLog.timestamp >= start_date)
    if end_date:
        q = q.filter(models.BatLog.timestamp <= end_date)
    return q.order_by(models.BatLog.timestamp.desc()).limit(limit).all()

@app.post("/api/logs", response_model=BatLogSchema, status_code=status.HTTP_201_CREATED)
def create_log(
    log_data: BatLogCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    log = models.BatLog(
        owner_id=current_user.id,
        event_type=log_data.event_type,
        details=log_data.details
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

# --- Focus Endpoints ---
@app.post("/api/focus/sessions", response_model=BatFocusSchema, status_code=status.HTTP_201_CREATED)
def start_focus_session(
    payload: Optional[BatFocusCreate] = Body(None),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if payload:
        if payload.mission_id:
            mission = db.query(models.BatMission).filter(
                models.BatMission.id == payload.mission_id,
                models.BatMission.owner_id == current_user.id
            ).first()
            if not mission:
                raise HTTPException(status_code=404, detail="Mission not found")
        if payload.habit_id:
            habit = db.query(models.BatHabit).filter(
                models.BatHabit.id == payload.habit_id,
                models.BatHabit.owner_id == current_user.id
            ).first()
            if not habit:
                raise HTTPException(status_code=404, detail="Habit not found")

    session = models.BatFocus(
        start_time=datetime.now(timezone.utc),
        owner_id=current_user.id,
        mission_id=payload.mission_id if payload else None,
        habit_id=payload.habit_id if payload else None,
    )
    db.add(session)
    db.flush()
    db.refresh(session)

    auto_log_event(db, current_user.id, "focus_session_started", {
        "session_id": session.id,
        "start_time": session.start_time.isoformat(),
        "mission_id": session.mission_id,
        "habit_id": session.habit_id,
    })
    db.commit()

    return session

@app.put("/api/focus/sessions/{session_id}", response_model=BatFocusSchema)
def end_focus_session(
    session_id: int,
    payload: BatFocusCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    session = db.query(models.BatFocus).filter(
        models.BatFocus.id == session_id,
        models.BatFocus.owner_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Focus session not found")

    if 'end_time' in payload.model_fields_set:
        session.end_time = payload.end_time.replace(tzinfo=None) if payload.end_time else None
    elif not session.end_time:
        session.end_time = datetime.now(timezone.utc)
    for field in payload.model_fields_set:
        if field == 'end_time':
            continue
        setattr(session, field, getattr(payload, field))

    if session.duration_minutes is None and session.end_time:
        delta = session.end_time - session.start_time
        session.duration_minutes = int(delta.total_seconds() / 60)

    if session.duration_minutes:
        if session.mission_id:
            mission = db.query(models.BatMission).filter(
                models.BatMission.id == session.mission_id,
                models.BatMission.owner_id == current_user.id
            ).first()
            if mission:
                mission.focus_minutes = (mission.focus_minutes or 0) + session.duration_minutes
                mission.completed_focus_sessions = (mission.completed_focus_sessions or 0) + 1
        if session.habit_id:
            habit = db.query(models.BatHabit).filter(
                models.BatHabit.id == session.habit_id,
                models.BatHabit.owner_id == current_user.id
            ).first()
            if habit:
                habit.focus_minutes = (habit.focus_minutes or 0) + session.duration_minutes

    reward = session.duration_minutes if session.duration_minutes else 0
    current_user.points += reward
    old_level = current_user.bat_level
    current_user.bat_level = calculate_bat_level(current_user.points)

    db.flush()
    db.refresh(session)
    db.refresh(current_user)

    auto_log_event(db, current_user.id, "focus_session_ended", {
        "session_id": session.id,
        "duration_minutes": session.duration_minutes,
        "mission_id": session.mission_id,
        "habit_id": session.habit_id,
        "points_awarded": reward,
        "old_level": old_level,
        "new_level": current_user.bat_level
    })
    db.commit()

    return session

@app.get("/api/focus/sessions", response_model=List[BatFocusSchema])
def list_focus_sessions(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return db.query(models.BatFocus).filter(
        models.BatFocus.owner_id == current_user.id
    ).order_by(models.BatFocus.start_time.desc()).limit(limit).all()


# --- Focus Stats Endpoints ---
def _completed_sessions_query(db: Session, current_user: models.BatAccount):
    return db.query(models.BatFocus).filter(
        models.BatFocus.owner_id == current_user.id,
        models.BatFocus.end_time.isnot(None),
        models.BatFocus.duration_minutes > 0,
    )

def _compute_focus_stats(db: Session, current_user: models.BatAccount, period: str) -> dict:
    today = datetime.now(timezone.utc).date()

    if period == "day":
        range_start = today
        range_end = today
    elif period == "week":
        range_start = today - timedelta(days=today.weekday())
        range_end = range_start + timedelta(days=6)
    elif period == "month":
        range_start = today.replace(day=1)
        range_end = (range_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    elif period == "year":
        range_start = today.replace(month=1, day=1)
        range_end = today.replace(month=12, day=31)
    else:  # all
        range_start = None
        range_end = None

    q = _completed_sessions_query(db, current_user)
    if range_start:
        q = q.filter(models.BatFocus.end_time >= datetime(range_start.year, range_start.month, range_start.day))
    if range_end:
        q = q.filter(
            models.BatFocus.end_time
            < datetime(range_end.year, range_end.month, range_end.day) + timedelta(days=1)
        )
    sessions = q.all()

    total_minutes = 0
    total_sessions = len(sessions)
    mission_agg = defaultdict(lambda: {"minutes": 0, "sessions": 0})
    habit_agg = defaultdict(lambda: {"minutes": 0, "sessions": 0})
    unassigned = {"minutes": 0, "sessions": 0}
    heatmap = defaultdict(int)
    days_with_sessions = set()

    for s in sessions:
        total_minutes += s.duration_minutes
        d = s.end_time.date()
        heatmap[d] += s.duration_minutes
        days_with_sessions.add(d)
        if s.mission_id is not None:
            mission_agg[s.mission_id]["minutes"] += s.duration_minutes
            mission_agg[s.mission_id]["sessions"] += 1
        elif s.habit_id is not None:
            habit_agg[s.habit_id]["minutes"] += s.duration_minutes
            habit_agg[s.habit_id]["sessions"] += 1
        else:
            unassigned["minutes"] += s.duration_minutes
            unassigned["sessions"] += 1

    breakdown = []
    if mission_agg:
        mission_rows = db.query(models.BatMission).filter(
            models.BatMission.id.in_(list(mission_agg.keys())),
            models.BatMission.owner_id == current_user.id,
        ).all()
        mission_names = {m.id: m.title for m in mission_rows}
        for mid, agg in mission_agg.items():
            breakdown.append({
                "type": "mission",
                "id": mid,
                "name": mission_names.get(mid, f"Mission #{mid}"),
                "minutes": agg["minutes"],
                "sessions": agg["sessions"],
                "percent": round(agg["minutes"] / total_minutes * 100, 1) if total_minutes else 0.0,
            })
    if habit_agg:
        habit_rows = db.query(models.BatHabit).filter(
            models.BatHabit.id.in_(list(habit_agg.keys())),
            models.BatHabit.owner_id == current_user.id,
        ).all()
        habit_names = {h.id: h.name for h in habit_rows}
        for hid, agg in habit_agg.items():
            breakdown.append({
                "type": "habit",
                "id": hid,
                "name": habit_names.get(hid, f"Habit #{hid}"),
                "minutes": agg["minutes"],
                "sessions": agg["sessions"],
                "percent": round(agg["minutes"] / total_minutes * 100, 1) if total_minutes else 0.0,
            })
    if unassigned["sessions"] > 0:
        breakdown.append({
            "type": "none",
            "id": None,
            "name": "Unassigned",
            "minutes": unassigned["minutes"],
            "sessions": unassigned["sessions"],
            "percent": round(unassigned["minutes"] / total_minutes * 100, 1) if total_minutes else 0.0,
        })
    breakdown.sort(key=lambda b: b["minutes"], reverse=True)

    streak = 0
    d = today
    while d in days_with_sessions:
        streak += 1
        d -= timedelta(days=1)

    daily_heatmap = [
        {"date": (today - timedelta(days=i)).isoformat(), "minutes": heatmap.get(today - timedelta(days=i), 0)}
        for i in range(34, -1, -1)
    ]

    return {
        "period": period,
        "range_start": range_start.isoformat() if range_start else None,
        "range_end": range_end.isoformat() if range_end else None,
        "total_minutes": total_minutes,
        "total_sessions": total_sessions,
        "current_streak_days": streak,
        "breakdown": breakdown,
        "daily_heatmap": daily_heatmap,
    }

@app.get("/api/stats/focus", response_model=FocusStatsResponse)
def focus_stats(
    period: str = Query("week", pattern="^(day|week|month|year|all)$"),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return _compute_focus_stats(db, current_user, period)

@app.get("/api/stats/focus/sessions", response_model=FocusSessionLogResponse)
def focus_session_log(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    base = _completed_sessions_query(db, current_user)
    total = base.count()
    sessions = (
        base.order_by(models.BatFocus.start_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    mission_ids = {s.mission_id for s in sessions if s.mission_id}
    habit_ids = {s.habit_id for s in sessions if s.habit_id}
    mission_names = {}
    if mission_ids:
        mission_names = {
            m.id: m.title
            for m in db.query(models.BatMission).filter(
                models.BatMission.id.in_(mission_ids),
                models.BatMission.owner_id == current_user.id,
            ).all()
        }
    habit_names = {}
    if habit_ids:
        habit_names = {
            h.id: h.name
            for h in db.query(models.BatHabit).filter(
                models.BatHabit.id.in_(habit_ids),
                models.BatHabit.owner_id == current_user.id,
            ).all()
        }

    items = []
    for s in sessions:
        items.append({
            "id": s.id,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "duration_minutes": s.duration_minutes,
            "mission_id": s.mission_id,
            "mission_name": mission_names.get(s.mission_id) if s.mission_id else None,
            "habit_id": s.habit_id,
            "habit_name": habit_names.get(s.habit_id) if s.habit_id else None,
        })

    return {"total": total, "limit": limit, "offset": offset, "items": items}


def _trend_buckets(granularity: str) -> list:
    """Return oldest→newest buckets as {date, label, start, end}."""
    today = datetime.now(timezone.utc).date()
    buckets = []

    if granularity == "day":
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            buckets.append({
                "date": d.isoformat(),
                "label": d.strftime("%a"),
                "start": d,
                "end": d + timedelta(days=1),
            })
    elif granularity == "week":
        monday = today - timedelta(days=today.weekday())
        for i in range(7, -1, -1):
            ws = monday - timedelta(weeks=i)
            buckets.append({
                "date": ws.isoformat(),
                "label": f"{ws.month}/{ws.day}",
                "start": ws,
                "end": ws + timedelta(days=7),
            })
    else:  # month
        for i in range(5, -1, -1):
            total = today.year * 12 + (today.month - 1) - i
            yy, mm = divmod(total, 12)
            ms = date(yy, mm + 1, 1)
            ntotal = yy * 12 + mm + 1
            ny, nm = divmod(ntotal, 12)
            me = date(ny, nm + 1, 1)
            buckets.append({
                "date": ms.isoformat(),
                "label": ms.strftime("%b"),
                "start": ms,
                "end": me,
            })

    return buckets


@app.get("/api/stats/focus/trend", response_model=FocusTrendResponse)
def focus_trend(
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    buckets = _trend_buckets(granularity)
    points = [
        {"label": b["label"], "date": b["date"], "minutes": 0, "sessions": 0}
        for b in buckets
    ]

    sessions = _completed_sessions_query(db, current_user).all()
    for s in sessions:
        d = s.end_time.date()
        for i, b in enumerate(buckets):
            if b["start"] <= d < b["end"]:
                points[i]["minutes"] += s.duration_minutes
                points[i]["sessions"] += 1
                break

    return {"granularity": granularity, "points": points}


def _habit_scheduled_day(habit: models.BatHabit, day: date) -> bool:
    """Decide whether a habit is 'due' on a given day, from its frequency field."""
    if habit.created_at.date() > day:
        return False
    anchor = habit.last_completed or habit.created_at
    anchor_date = anchor.date()
    if habit.frequency == "daily":
        return True
    if habit.frequency == "weekly":
        return anchor_date.weekday() == day.weekday()
    if habit.frequency == "monthly":
        return anchor_date.day == day.day
    return True


@app.get("/api/stats/day", response_model=DayStatsResponse)
def day_stats(
    day: Optional[date] = Query(None, description="YYYY-MM-DD; defaults to today"),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    selected = day or datetime.now(timezone.utc).date()
    day_start = datetime(selected.year, selected.month, selected.day)
    day_end = day_start + timedelta(days=1)
    today = datetime.now(timezone.utc).date()

    due_missions = db.query(models.BatMission).filter(
        models.BatMission.owner_id == current_user.id,
        models.BatMission.due_date >= day_start,
        models.BatMission.due_date < day_end,
    ).all()

    completed_missions = db.query(models.BatMission).filter(
        models.BatMission.owner_id == current_user.id,
        models.BatMission.status == "completed",
        models.BatMission.completed_at >= day_start,
        models.BatMission.completed_at < day_end,
    ).all()

    on_time = 0
    overdue = 0
    uncompleted = 0
    for m in due_missions:
        due = m.due_date.date()
        completed = m.status == "completed" and m.completed_at is not None
        completed_on_time = completed and m.completed_at.date() <= due
        if completed_on_time:
            on_time += 1
        elif completed:
            # Completed but after its due date — not on time.
            if due < today:
                overdue += 1
            else:
                uncompleted += 1
        elif due < today:
            overdue += 1
        else:
            uncompleted += 1

    user_habit_ids = {
        h.id for h in db.query(models.BatHabit.id).filter(
            models.BatHabit.owner_id == current_user.id
        ).all()
    }

    completed_habit_ids = set()
    if user_habit_ids:
        logs = db.query(models.HabitCompletionLog.habit_id).filter(
            models.HabitCompletionLog.habit_id.in_(user_habit_ids),
            models.HabitCompletionLog.completed_at >= day_start,
            models.HabitCompletionLog.completed_at < day_end,
        ).all()
        completed_habit_ids = {lid for (lid,) in logs}

    scheduled_habit_ids = set()
    if user_habit_ids:
        habits = db.query(models.BatHabit).filter(
            models.BatHabit.id.in_(user_habit_ids)
        ).all()
        scheduled_habit_ids = {h.id for h in habits if _habit_scheduled_day(h, selected)}
    total_count = len(due_missions) + len(scheduled_habit_ids)

    # completed_count is a strict subset of total_count: only items that are
    # BOTH due that day AND completed that day. Missions completed on a day
    # they weren't due on are surfaced separately and never inflate the rate.
    due_ids = {m.id for m in due_missions}
    completed_due_missions = [m for m in completed_missions if m.id in due_ids]
    completed_due_habits = len(completed_habit_ids & scheduled_habit_ids)

    completed_count = len(completed_due_missions) + completed_due_habits
    completed_not_due_today = (
        len(completed_missions) - len(completed_due_missions)
    ) + (len(completed_habit_ids) - completed_due_habits)
    completion_rate = round(completed_count / total_count * 100, 2) if total_count else 0.0

    type_distribution = []
    if completed_due_missions:
        type_distribution.append({"type": "mission", "count": len(completed_due_missions)})
    if completed_due_habits:
        type_distribution.append({"type": "habit", "count": completed_due_habits})

    tag_counts = defaultdict(int)
    for m in completed_due_missions:
        tags = [t.strip() for t in (m.tags or "").split(",") if t.strip()]
        if tags:
            for t in tags:
                tag_counts[t] += 1
        else:
            tag_counts["untagged"] += 1
    tag_distribution = [{"tag": t, "count": c} for t, c in tag_counts.items()]
    tag_distribution.sort(key=lambda item: (-item["count"], item["tag"] == "untagged"))
    if tag_distribution and tag_distribution[-1]["tag"] == "untagged":
        untagged = tag_distribution.pop(-1)
        tag_distribution.append(untagged)

    return {
        "date": selected.isoformat(),
        "completed_count": completed_count,
        "total_count": total_count,
        "completion_rate": completion_rate,
        "completed_not_due_today": completed_not_due_today,
        "status_distribution": {"on_time": on_time, "overdue": overdue, "uncompleted": uncompleted},
        "type_distribution": type_distribution,
        "tag_distribution": tag_distribution,
    }


# --- Static Files (SPA) ---

_possible_static_dirs = [
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"),
    "/app/static",
]

static_dir = None
for d in _possible_static_dirs:
    if os.path.isdir(os.path.join(d, "assets")):
        static_dir = d
        break

if static_dir:
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    index_path = os.path.join(static_dir, "index.html")

    if os.path.isfile(index_path):
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = os.path.join(static_dir, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(index_path, media_type="text/html")
else:
    logger.warning("static_dir_not_found", message="Frontend dist not found — SPA routes will 404")