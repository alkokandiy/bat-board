from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

from config import get_settings

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
    mission_columns = {c["name"] for c in inspector.get_columns("bat_missions")}
    expected_mission = {"tags", "is_pinned", "is_dismissed", "location", "notes", "subtasks"}
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
        if missing_mission:
            conn.commit()

    if inspector.has_table("bat_calendar_events"):
        ce_columns = {c["name"] for c in inspector.get_columns("bat_calendar_events")}
        if "updated_at" not in ce_columns:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE bat_calendar_events ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ))
                conn.commit()


def create_db_tables():
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    inspector = inspect(engine)
    has_version_table = inspector.has_table("alembic_version")

    if not has_version_table:
        try:
            command.upgrade(alembic_cfg, "head")
        except Exception:
            Base.metadata.create_all(bind=engine)
            try:
                command.stamp(alembic_cfg, "head")
            except Exception:
                pass
    else:
        command.upgrade(alembic_cfg, "head")
        Base.metadata.create_all(bind=engine)

    _ensure_columns()
