"""Pydantic request/response schemas for M2 auth and labs."""

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from labguard_api.models import Role
from labguard_api.security import BCRYPT_MAX_BYTES

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 12


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


class Page(BaseModel):
    items: list[Any]
    page: int
    page_size: int
    total: int


def paginate(query_total: int, page: int, page_size: int, items: list[Any]) -> Page:
    return Page(items=items, page=page, page_size=page_size, total=query_total)
