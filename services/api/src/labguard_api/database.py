"""Database engine and session wiring.

The URL comes from DATABASE_URL (PostgreSQL via psycopg in dev/prod).
Tests override the ``get_db`` dependency with SQLite and never touch this.
"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url or "://" not in url:
        raise RuntimeError(
            "DATABASE_URL is not set to a valid SQLAlchemy URL "
            "(e.g. postgresql+psycopg://labguard:labguard@localhost:5432/labguard)."
        )
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_connection() -> None:
    """Readiness probe helper: fails fast when the database is unreachable."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
