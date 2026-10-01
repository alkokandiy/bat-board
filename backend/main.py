import json
import logging
import os
import sys
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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from pydantic import BaseModel, Field, ConfigDict, field_validator

import models
from database import engine, get_db, create_db_tables
from config import get_settings
from auth import (
    get_current_active_user, authenticate_user, create_access_token,
    create_refresh_token, decode_refresh_token, get_password_hash,
    get_user_for_token, revoke_all_tokens, token_claims, validate_alfred_address,
    validate_new_password, validate_username,
    verify_password, UserCreate, UserResponse, Token,
)
from dependencies import limiter
from routers.countdown import router as countdown_router
from routers.notes import router as notes_router
from routers.telegram import router as telegram_router
from routers.alfred import router as alfred_router
from services import (
    calendar_service,
    focus_service,
    habit_service,
    logs_service,
    mission_service,
    profile_service,
    stats_service,
)
from services.common import auto_log_event, calculate_bat_level
from services.timezones import (
    day_bounds_utc, local_date, local_today, user_tz, validate_timezone,
)
from services.stats_service import _completed_sessions_query, _compute_focus_stats

settings = get_settings()

# --- Structured Logging ---
# structlog renders; stdlib routes. LOG_LEVEL must be applied to the stdlib
# root logger — it never was, so filter_by_level dropped every info log
# (requests, logins, Telegram links) at Python's default WARNING level.
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(message)s",
    stream=sys.stdout,
)
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
# Shared instance from dependencies.py — routers use this same object so
# slowapi enforcement via app.state.limiter actually applies to them.

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
# The SPA is served from this same origin, so production needs no CORS
# entries; CORS_ORIGINS is for the Vite dev server or a separate frontend.
# A "*" wildcard is never combined with credentials: Starlette would then
# echo back any requesting origin as allowed-with-credentials.
_allow_any_origin = "*" in settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=not _allow_any_origin,
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

# --- Layered routers (new structure; existing inline routes below stay as-is) ---
app.include_router(notes_router)
app.include_router(countdown_router)
app.include_router(telegram_router)
app.include_router(alfred_router)

# NOTE: calculate_bat_level / auto_log_event now live in services/common.py
# (imported above) so services can use them without a circular import.
# All existing call sites in this file keep working unchanged.

# --- Pydantic Schemas ---
class BatAccountSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    points: int
    bat_level: str
    timezone: Optional[str] = None
    alfred_address: Optional[str] = None
    created_at: datetime

class BatAccountUpdate(BaseModel):
    # Points are earned only through missions, habits and focus sessions;
    # the old client-supplied points_delta let any user mint points.
    username: Optional[str] = None
    timezone: Optional[str] = None
    # "" clears it (Alfred falls back to the username).
    alfred_address: Optional[str] = None

    @field_validator("alfred_address")
    @classmethod
    def _validate_alfred_address(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else (validate_alfred_address(v) or "")

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: Optional[str]) -> Optional[str]:
        return validate_username(v) if v is not None else v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        return validate_timezone(v) if v is not None else v

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
        timezone=user_data.timezone,
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

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    access_token = create_access_token(data=token_claims(user))
    refresh_token = create_refresh_token(data=token_claims(user))

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

    user = get_user_for_token(db, token_data)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    access_token = create_access_token(data=token_claims(user))
    new_refresh_token = create_refresh_token(data=token_claims(user))

    return Token(access_token=access_token, refresh_token=new_refresh_token)

@app.get("/api/auth/me", response_model=UserResponse)
def get_me(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return profile_service.get_profile(db, current_user)

# --- Account Endpoints ---
@app.get("/api/account", response_model=BatAccountSchema)
def get_account(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return profile_service.get_profile(db, current_user)

@app.put("/api/account", response_model=BatAccountSchema)
@limiter.limit("30/minute")
def update_account(
    request: Request,
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

    if payload.alfred_address is not None:
        current_user.alfred_address = payload.alfred_address or None

    if payload.timezone is not None and payload.timezone != current_user.timezone:
        auto_log_event(db, current_user.id, "account_update", {
            "field": "timezone", "old": current_user.timezone, "new": payload.timezone,
        })
        current_user.timezone = payload.timezone

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken")
    db.refresh(current_user)
    return current_user

class ChangePassword(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, v: str) -> str:
        return validate_new_password(v)

class PasswordChangedResponse(BaseModel):
    detail: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@app.put("/api/account/password", response_model=PasswordChangedResponse)
@limiter.limit("30/minute")
def change_password(
    request: Request,
    payload: ChangePassword,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = get_password_hash(payload.new_password)
    # Sign out every other session; this device continues with fresh tokens.
    revoke_all_tokens(current_user)
    auto_log_event(db, current_user.id, "password_changed", {"message": "Password changed"})
    db.commit()
    db.refresh(current_user)
    return {
        "detail": "Password updated successfully",
        "access_token": create_access_token(data=token_claims(current_user)),
        "refresh_token": create_refresh_token(data=token_claims(current_user)),
    }

@app.post("/api/account/reset-points", response_model=BatAccountSchema)
@limiter.limit("30/minute")
def reset_points(
    request: Request,
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
    return mission_service.list_missions(db, current_user)

@app.post("/api/missions", response_model=BatMissionSchema, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_mission(
    request: Request,
    mission_data: BatMissionCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return mission_service.create_mission(
        db,
        current_user,
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
    )

_NON_NULLABLE_MISSION_FIELDS = {"title", "priority", "is_pinned", "is_dismissed"}


@app.put("/api/missions/{mission_id}", response_model=BatMissionSchema)
@limiter.limit("30/minute")
def update_mission(
    request: Request,
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

    for field in payload.model_fields_set:
        if field == 'status':
            continue
        value = getattr(payload, field)
        if value is None and field in _NON_NULLABLE_MISSION_FIELDS:
            continue  # explicit null on a NOT NULL column used to 500
        setattr(mission, field, value)

    if 'status' in payload.model_fields_set and payload.status is not None:
        if payload.status == "completed" and old_status != "completed":
            mission = mission_service.complete_mission(db, current_user, mission_id)
        elif payload.status != "completed" and old_status == "completed":
            mission_service.reopen_mission(db, current_user, mission, payload.status)
        else:
            mission.status = payload.status

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
@limiter.limit("30/minute")
def delete_mission(
    request: Request,
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
    return calendar_service.list_upcoming_events(db, current_user)

@app.post("/api/calendar/events", response_model=CalendarEventSchema, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_calendar_event(
    request: Request,
    event_data: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    event = calendar_service.create_event(
        db,
        current_user,
        title=event_data.title,
        start_time=event_data.start_time,
        description=event_data.description,
        end_time=event_data.end_time,
        color=event_data.color,
        mission_id=event_data.mission_id,
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return event

@app.put("/api/calendar/events/{event_id}", response_model=CalendarEventSchema)
@limiter.limit("30/minute")
def update_calendar_event(
    request: Request,
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
@limiter.limit("30/minute")
def delete_calendar_event(
    request: Request,
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
    return habit_service.list_habits(db, current_user)

@app.post("/api/habits", response_model=BatHabitSchema, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_habit(
    request: Request,
    habit_data: BatHabitCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return habit_service.create_habit(
        db,
        current_user,
        name=habit_data.name,
        description=habit_data.description,
        frequency=habit_data.frequency,
    )

@app.put("/api/habits/{habit_id}", response_model=BatHabitSchema)
@limiter.limit("30/minute")
def update_habit(
    request: Request,
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
        value = getattr(payload, field)
        if value is None and field in ("name", "frequency", "streak"):
            continue  # explicit null on a NOT NULL column used to 500
        setattr(habit, field, value)

    db.flush()
    db.refresh(habit)

    auto_log_event(db, current_user.id, "habit_updated", {
        "habit_id": habit.id,
        "name": habit.name
    })
    db.commit()

    return habit

@app.delete("/api/habits/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def delete_habit(
    request: Request,
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
@limiter.limit("30/minute")
def check_in_habit(
    request: Request,
    habit_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    habit = habit_service.check_in_habit(db, current_user, habit_id)
    if habit is None:
        raise HTTPException(status_code=404, detail="Habit not found")
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
    return logs_service.list_recent_logs(
        db, current_user, limit=limit, start_date=start_date, end_date=end_date
    )

@app.post("/api/logs", response_model=BatLogSchema, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_log(
    request: Request,
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
@limiter.limit("30/minute")
def start_focus_session(
    request: Request,
    payload: Optional[BatFocusCreate] = Body(None),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        return focus_service.start_focus_session(
            db,
            current_user,
            mission_id=payload.mission_id if payload else None,
            habit_id=payload.habit_id if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.put("/api/focus/sessions/{session_id}", response_model=BatFocusSchema)
@limiter.limit("30/minute")
def end_focus_session(
    request: Request,
    session_id: int,
    payload: BatFocusCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    session = focus_service.end_focus_session(
        db,
        current_user,
        session_id,
        **{field: getattr(payload, field) for field in payload.model_fields_set},
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Focus session not found")
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
# _completed_sessions_query / _compute_focus_stats now live in
# services/stats_service.py (imported above); focus_session_log and
# focus_trend below keep working unchanged via those imports.

@app.get("/api/stats/focus", response_model=FocusStatsResponse)
def focus_stats(
    period: str = Query("week", pattern="^(day|week|month|year|all)$"),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return stats_service.get_focus_stats(db, current_user, period)

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


def _trend_buckets(granularity: str, today: date) -> list:
    """Return oldest→newest buckets as {date, label, start, end}."""
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
    tz = user_tz(current_user)
    buckets = _trend_buckets(granularity, local_today(current_user))
    points = [
        {"label": b["label"], "date": b["date"], "minutes": 0, "sessions": 0}
        for b in buckets
    ]

    sessions = _completed_sessions_query(db, current_user).all()
    for s in sessions:
        d = local_date(s.end_time, tz)
        for i, b in enumerate(buckets):
            if b["start"] <= d < b["end"]:
                points[i]["minutes"] += s.duration_minutes
                points[i]["sessions"] += 1
                break

    return {"granularity": granularity, "points": points}


def _habit_scheduled_day(habit: models.BatHabit, day: date, tz) -> bool:
    """Decide whether a habit is 'due' on a given local day, from its frequency field."""
    if local_date(habit.created_at, tz) > day:
        return False
    anchor = habit.last_completed or habit.created_at
    anchor_date = local_date(anchor, tz)
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
    tz = user_tz(current_user)
    today = local_today(current_user)
    selected = day or today
    # Completions (completed_at, HabitCompletionLog) are instants: bucket them
    # by the user's local day. Due dates are calendar dates stored as UTC
    # midnight, so they are matched on their UTC date.
    day_start, day_end = day_bounds_utc(selected, tz)
    due_start = datetime(selected.year, selected.month, selected.day, tzinfo=timezone.utc)
    due_end = due_start + timedelta(days=1)

    due_missions = db.query(models.BatMission).filter(
        models.BatMission.owner_id == current_user.id,
        models.BatMission.due_date >= due_start,
        models.BatMission.due_date < due_end,
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
        due = local_date(m.due_date, timezone.utc)
        completed = m.status == "completed" and m.completed_at is not None
        completed_on_time = completed and local_date(m.completed_at, tz) <= due
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
        scheduled_habit_ids = {h.id for h in habits if _habit_scheduled_day(h, selected, tz)}
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

    _spa_static_dir = os.path.realpath(static_dir)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        # The path param arrives percent-decoded, so "..%2f" becomes "../".
        # Resolve and require the result to stay inside the dist directory,
        # otherwise any file on disk (e.g. /proc/self/environ) is servable.
        file_path = os.path.realpath(os.path.join(_spa_static_dir, full_path))
        if (
            file_path.startswith(_spa_static_dir + os.sep)
            and os.path.isfile(file_path)
        ):
            return FileResponse(file_path)
        index_path = os.path.join(_spa_static_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path, media_type="text/html")
        raise HTTPException(status_code=404, detail="Not found")
else:
    logger.warning("static_dir_not_found", message="Frontend dist not found — SPA routes will 404")
