"""Shared SQLAlchemy base for LabGuard models.

M1: declarative base only so Alembic has a metadata target.
No tables are defined yet (schema arrives in M2+).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all LabGuard ORM models."""
