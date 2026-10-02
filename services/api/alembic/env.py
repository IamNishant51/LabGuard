"""Alembic environment (M2: models registered on Base.metadata).

Database URL is taken from the DATABASE_URL environment variable at
migration time.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from labguard_api.db import Base
import labguard_api.models  # noqa: F401 -- register table metadata on Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url(fallback: str | None) -> str:
    """Return DATABASE_URL or fail fast with an actionable message."""
    url = os.environ.get("DATABASE_URL", fallback)
    if not url or "://" not in url or url.startswith("driver://"):
        raise RuntimeError(
            "DATABASE_URL is not set to a valid SQLAlchemy URL "
            "(e.g. postgresql+psycopg://labguard:labguard@localhost:5432/labguard). "
            "Refusing to run migrations against the alembic.ini placeholder."
        )
    return url


def run_migrations_offline() -> None:
    url = _database_url(config.get_main_option("sqlalchemy.url"))
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url(configuration.get("sqlalchemy.url"))
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
