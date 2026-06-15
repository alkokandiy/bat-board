from sqlalchemy import create_engine, inspect
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
