import json
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

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

from pydantic import BaseModel, Field

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
    if points < 200:
        return "The Orphan"
    elif points < 500:
        return "The Vigilante"
    elif points < 1000:
        return "The Detective"
    elif points < 2000:
        return "Son of Gotham"
    elif points < 3500:
        return "The Caped Crusader"
    elif points < 5500:
        return "Heir of the Demon"
    elif points < 8000:
        return "The Dark Knight"
    elif points < 12000:
        return "Faris al-Khorasan"
    elif points < 18000:
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
    id: int
    username: str
    points: int
    bat_level: str
    created_at: datetime

    class Config:
        from_attributes = True

class BatAccountUpdate(BaseModel):
    username: Optional[str] = None
    points_delta: Optional[int] = None

class BatMissionBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    due_date: Optional[datetime] = None
    priority: str = "medium"
    status: str = "pending"
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
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_dismissed: Optional[bool] = None
    location: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    subtasks: Optional[str] = None

class BatMissionSchema(BatMissionBase):
    id: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    owner_id: int
    focus_minutes: int = 0
    completed_focus_sessions: int = 0

    class Config:
        from_attributes = True

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
    id: int
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    color: Optional[str] = None
    mission_id: Optional[int] = None
    created_at: datetime
    owner_id: int

    class Config:
        from_attributes = True

class BatHabitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    frequency: str = "daily"

class BatHabitCreate(BatHabitBase):
    pass

class BatHabitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    frequency: Optional[str] = None
    streak: Optional[int] = None

class BatHabitSchema(BatHabitBase):
    id: int
    streak: int
    last_completed: Optional[datetime] = None
    created_at: datetime
    owner_id: int

    class Config:
        from_attributes = True

class BatLogBase(BaseModel):
    event_type: str
    details: str

class BatLogCreate(BatLogBase):
    pass

class BatLogSchema(BatLogBase):
    id: int
    timestamp: datetime
    owner_id: int

    class Config:
        from_attributes = True

class BatFocusCreate(BaseModel):
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    soundtrack_metadata: Optional[str] = None
    mission_id: Optional[int] = None

class BatFocusSchema(BaseModel):
    id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    soundtrack_metadata: Optional[str] = None
    owner_id: int

    class Config:
        from_attributes = True

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

    for field in payload.model_fields_set:
        if field == 'status':
            continue
        setattr(mission, field, getattr(payload, field))

    if 'status' in payload.model_fields_set:
        mission.status = payload.status
        if payload.status == "completed" and old_status != "completed":
            mission.completed_at = datetime.utcnow()
            reward = 100
            if mission.priority == "high":
                reward = 200
            elif mission.priority == "critical":
                reward = 500
            elif mission.priority == "low":
                reward = 50

            current_user.points += reward
            current_user.bat_level = calculate_bat_level(current_user.points)

            auto_log_event(db, current_user.id, "points_modified", {
                "reason": f"Completed mission '{mission.title}'",
                "points_delta": reward,
                "old_points": old_points,
                "new_points": current_user.points,
                "old_level": current_user.bat_level,
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

    now = datetime.utcnow()

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

        streak_bonus = min(habit.streak * 10, 100)
        reward = 50 + streak_bonus

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
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return db.query(models.BatLog).filter(
        models.BatLog.owner_id == current_user.id
    ).order_by(models.BatLog.timestamp.desc()).limit(limit).all()

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
    if payload and payload.mission_id:
        mission = db.query(models.BatMission).filter(
            models.BatMission.id == payload.mission_id,
            models.BatMission.owner_id == current_user.id
        ).first()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

    session = models.BatFocus(
        start_time=datetime.utcnow(),
        owner_id=current_user.id,
        mission_id=payload.mission_id if payload else None,
    )
    db.add(session)
    db.flush()
    db.refresh(session)

    auto_log_event(db, current_user.id, "focus_session_started", {
        "session_id": session.id,
        "start_time": session.start_time.isoformat(),
        "mission_id": session.mission_id,
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
        session.end_time = datetime.utcnow()
    for field in payload.model_fields_set:
        if field == 'end_time':
            continue
        setattr(session, field, getattr(payload, field))

    if session.duration_minutes is None and session.end_time:
        delta = session.end_time - session.start_time
        session.duration_minutes = int(delta.total_seconds() / 60)

    if session.mission_id and session.duration_minutes:
        mission = db.query(models.BatMission).filter(
            models.BatMission.id == session.mission_id,
            models.BatMission.owner_id == current_user.id
        ).first()
        if mission:
            mission.focus_minutes = (mission.focus_minutes or 0) + session.duration_minutes
            mission.completed_focus_sessions = (mission.completed_focus_sessions or 0) + 1

    reward = session.duration_minutes * 2 if session.duration_minutes else 0
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