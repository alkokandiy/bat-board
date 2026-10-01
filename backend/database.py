import structlog
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

from config import get_settings

logger = structlog.get_logger()

settings = get_settings()

def create_engine_from_url(database_url: str):
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=300)

engine = create_engine_from_url(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_columns():
    inspector = inspect(engine)

    # BatAccount columns (011; the alembic migration also backfills timezone)
    account_columns = {c["name"] for c in inspector.get_columns("bat_account")}
    with engine.connect() as conn:
        if "timezone" not in account_columns:
            conn.execute(text("ALTER TABLE bat_account ADD COLUMN timezone VARCHAR"))
        if "token_version" not in account_columns:
            conn.execute(text(
                "ALTER TABLE bat_account ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
            ))
        if not {"timezone", "token_version"} <= account_columns:
            conn.commit()

    # BatMission columns
    mission_columns = {c["name"] for c in inspector.get_columns("bat_missions")}
    expected_mission = {"tags", "is_pinned", "is_dismissed", "location", "notes", "subtasks", "focus_minutes", "completed_focus_sessions"}
    missing_mission = expected_mission - mission_columns

    with engine.connect() as conn:
        for col in missing_mission:
            if col in ("is_pinned", "is_dismissed"):
                conn.execute(text(
                    f"ALTER TABLE bat_missions ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT FALSE"
                ))
            elif col in ("tags", "location", "notes", "subtasks"):
                conn.execute(text(
                    f"ALTER TABLE bat_missions ADD COLUMN {col} VARCHAR"
                ))
            elif col in ("focus_minutes", "completed_focus_sessions"):
                conn.execute(text(
                    f"ALTER TABLE bat_missions ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
                ))
        if missing_mission:
            conn.commit()

    # BatCalendarEvent columns
    if inspector.has_table("bat_calendar_events"):
        ce_columns = {c["name"] for c in inspector.get_columns("bat_calendar_events")}
        if "updated_at" not in ce_columns:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE bat_calendar_events ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ))
                conn.commit()

    # BatHabit columns
    if inspector.has_table("bat_habits"):
        habit_columns = {c["name"] for c in inspector.get_columns("bat_habits")}
        with engine.connect() as conn:
            if "focus_minutes" not in habit_columns:
                conn.execute(text(
                    "ALTER TABLE bat_habits ADD COLUMN focus_minutes INTEGER NOT NULL DEFAULT 0"
                ))
            if "target_date" not in habit_columns:
                conn.execute(text(
                    "ALTER TABLE bat_habits ADD COLUMN target_date TIMESTAMP"
                ))
            if "focus_minutes" not in habit_columns or "target_date" not in habit_columns:
                conn.commit()

    # BatFocus columns
    if inspector.has_table("bat_focus"):
        focus_columns = {c["name"] for c in inspector.get_columns("bat_focus")}
        with engine.connect() as conn:
            if "mission_id" not in focus_columns:
                conn.execute(text(
                    "ALTER TABLE bat_focus ADD COLUMN mission_id INTEGER REFERENCES bat_missions(id) ON DELETE SET NULL"
                ))
            if "habit_id" not in focus_columns:
                conn.execute(text(
                    "ALTER TABLE bat_focus ADD COLUMN habit_id INTEGER REFERENCES bat_habits(id) ON DELETE SET NULL"
                ))
            if "mission_id" not in focus_columns or "habit_id" not in focus_columns:
                conn.commit()


def create_db_tables():
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_cfg.attributes["configure_logger"] = False  # keep the app's logging

    inspector = inspect(engine)
    has_version_table = inspector.has_table("alembic_version")

    if not settings.database_url.startswith("postgresql"):
        # SQLite (tests / local dev): single process, schema from models.
        Base.metadata.create_all(bind=engine)
        _ensure_columns()
        return

    # Serialize migrations across gunicorn workers with a session-level
    # advisory lock held on ONE dedicated connection for the whole upgrade.
    # (Previously the lock was taken on a pooled connection that went straight
    # back to the pool and was "released" from a different one, so it could
    # stay held forever, and workers that lost the race ran create_all
    # concurrently with the migration.) Later workers block until the first
    # finishes, then their upgrade is a no-op.
    with engine.connect() as lock_conn:
        lock_conn.execute(text("SELECT pg_advisory_lock(8529461)"))
        lock_conn.commit()
        try:
            command.upgrade(alembic_cfg, "head")
        except Exception as exc:
            logger.error(
                "alembic_upgrade_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                hint="Alembic migration failed; falling back to create_all + column ensure. Fix the migration.",
            )
            Base.metadata.create_all(bind=engine)
            if not has_version_table:
                try:
                    command.stamp(alembic_cfg, "head")
                except Exception as exc2:
                    logger.warning("alembic_stamp_failed", error=str(exc2))
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(8529461)"))
            lock_conn.commit()

    _ensure_columns()
