import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models import Base
from config import get_settings

config = context.config

# The CLI (`alembic upgrade`, Railway's preDeployCommand) configures logging
# from alembic.ini. When the app runs migrations at startup it passes
# configure_logger=False: alembic.ini's root level (WARN) would otherwise
# override the app's LOG_LEVEL and drop all of its info logs.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    # disable_existing_loggers=False: don't silence loggers that already exist.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()