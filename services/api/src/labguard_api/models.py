"""LabGuard M3 ORM models: users, labs, memberships, devices, sessions, audit.

Devices carry identity/lifecycle fields only. Enrollment tokens (M4),
telemetry, alerts, and incidents arrive in later milestones.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from labguard_api.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role:
    ADMIN = "admin"
    STAFF = "staff"
    VIEWER = "viewer"
    ALL = (ADMIN, STAFF, VIEWER)


RoleEnum = Enum(*Role.ALL, name="role", validate_strings=True)


class User(Base):
    """Staff account. Email stored normalized (lowercased); password never plaintext."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(RoleEnum, nullable=False, default=Role.ADMIN)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    memberships: Mapped[list["LabMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Lab(Base):
    """Monitored computer lab. Memberships scope which users may see it."""

    __tablename__ = "labs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    memberships: Mapped[list["LabMembership"]] = relationship(
        back_populates="lab", cascade="all, delete-orphan", passive_deletes=True
    )
    devices: Mapped[list["Device"]] = relationship(
        back_populates="lab", cascade="all, delete-orphan", passive_deletes=True
    )


class LabMembership(Base):
    """Lab-scoped role assignment. Composite PK prevents duplicate memberships."""

    __tablename__ = "lab_memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    lab_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(RoleEnum, nullable=False, default=Role.VIEWER)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    lab: Mapped[Lab] = relationship(back_populates="memberships")


class Device(Base):
    """Registered computer (M3: identity record + CRUD; no tokens, no telemetry).

    Identity is (lab_id, hostname): hostnames are stored stripped and
    lowercased so identity is case-insensitive. Both fields are immutable
    after registration; only metadata and the active flag change.
    """

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("lab_id", "hostname", name="uq_devices_lab_hostname"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    lab: Mapped[Lab] = relationship(back_populates="devices")


class UserSession(Base):
    """Server-side session. Only the SHA-256 hash of the opaque token is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditLog(Base):
    """Administrative audit event (M3 writers: device lifecycle only).

    Actor is nullable so system actions can be recorded; deleting a user
    keeps their rows (SET NULL). Metadata keys are allow-listed in
    ``audit.record_audit`` and must never contain secrets or raw tokens.
    There is no read endpoint in M3; rows are inspectable via the database
    until a viewer arrives with a later milestone.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    actor: Mapped[User | None] = relationship()
