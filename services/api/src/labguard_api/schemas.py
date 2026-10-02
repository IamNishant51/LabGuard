"""Pydantic request/response schemas for M2 auth/labs and M3 devices."""

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from labguard_api.models import Role
from labguard_api.security import BCRYPT_MAX_BYTES

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,253}[a-z0-9])?$")
MIN_PASSWORD_LEN = 12
MAX_HOSTNAME_LEN = 255


def normalize_hostname(value: str) -> str:
    """Strip and lowercase; device identity is case-insensitive (M3).

    M4 enrollment must apply the same normalization before binding a
    credential, or `LAB-PC-01` at registration will not match the agent's
    report. Only alphanumerics plus `.`, `_`, `-` are accepted.
    """
    name = value.strip().lower()
    if not name:
        raise ValueError("Hostname must not be blank.")
    if len(name) > MAX_HOSTNAME_LEN:
        raise ValueError(f"Hostname must be at most {MAX_HOSTNAME_LEN} characters.")
    if not _HOSTNAME_RE.match(name):
        raise ValueError(
            "Hostname may only contain letters, digits, dots, underscores, and hyphens."
        )
    return name


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    return email


def check_password_length(value: str) -> str:
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes.")
    return value


def strip_non_empty(value: str, label: str, max_length: int) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} must not be blank.")
    if len(value) > max_length:
        raise ValueError(f"{label} must be at most {max_length} characters.")
    return value


class LoginIn(BaseModel):
    email: str
    password: str

    _norm = field_validator("email")(normalize_email)


class BootstrapIn(BaseModel):
    email: str
    password: str = Field(min_length=MIN_PASSWORD_LEN)
    display_name: str = Field(min_length=1, max_length=100)

    _norm = field_validator("email")(normalize_email)
    _pw = field_validator("password")(check_password_length)

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str) -> str:
        return strip_non_empty(value, "Display name", 100)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class LabIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return strip_non_empty(value, "Lab name", 100)


class LabOut(BaseModel):
    id: uuid.UUID
    name: str
    location: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberIn(BaseModel):
    user_id: uuid.UUID
    role: str = Field(default=Role.VIEWER)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in Role.ALL:
            raise ValueError(f"Role must be one of {', '.join(Role.ALL)}.")
        return value


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str


class DeviceIn(BaseModel):
    lab_id: uuid.UUID
    hostname: str = Field(min_length=1, max_length=MAX_HOSTNAME_LEN)
    display_name: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, max_length=32)
    agent_version: str | None = Field(default=None, max_length=32)

    _hostname = field_validator("hostname")(normalize_hostname)

    @field_validator("display_name", "platform", "agent_version")
    @classmethod
    def _optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        label = str(info.field_name).replace("_", " ").capitalize()
        limit = 255 if info.field_name == "display_name" else 32
        return strip_non_empty(value, label, limit)


class DevicePatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, max_length=32)
    agent_version: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None

    @field_validator("display_name", "platform", "agent_version")
    @classmethod
    def _optional_patch_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        label = str(info.field_name).replace("_", " ").capitalize()
        limit = 255 if info.field_name == "display_name" else 32
        return strip_non_empty(value, label, limit)


class DeviceOut(BaseModel):
    id: uuid.UUID
    lab_id: uuid.UUID
    hostname: str
    display_name: str | None
    platform: str | None
    agent_version: str | None
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Page(BaseModel):
    items: list[Any]
    page: int
    page_size: int
    total: int


def paginate(query_total: int, page: int, page_size: int, items: list[Any]) -> Page:
    return Page(items=items, page=page, page_size=page_size, total=query_total)
