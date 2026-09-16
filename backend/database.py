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

    inspector = inspect(engine)
    has_version_table = inspector.has_table("alembic_version")

    # Postgres advisory lock prevents multiple gunicorn workers from racing
    # through migrations simultaneously. Only the lock-holder runs alembic
    # upgrade; others skip it and fall back to create_all (safe to run
    # concurrently). For SQLite (tests), skip the lock — single-threaded.
    is_postgres = settings.database_url.startswith("postgresql")
    lock_acquired = False
    if is_postgres:
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT pg_try_advisory_lock(8529461)"))
                lock_acquired = result.scalar()
        except Exception:
            pass  # If lock acquisition fails, proceed without it (best effort)

    if lock_acquired:
        # This worker holds the lock — run the migration, then release.
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
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT pg_advisory_unlock(8529461)"))
                    conn.commit()
            except Exception:
                pass
    else:
        # Another worker holds the lock and is running the migration.
        # Skip alembic upgrade entirely — create_all is safe to run
        # concurrently and keeps the runtime schema usable while we wait.
        Base.metadata.create_all(bind=engine)

    _ensure_columns()
