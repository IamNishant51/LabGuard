"""Authentication and authorization dependencies (server-side enforcement).

Session resolution accepts the HttpOnly session cookie (browsers) or an
Authorization Bearer token (API clients) carrying the same opaque value.
Lab visibility returns 404 for anything the caller may not see so that
membership cannot be probed.
"""

from datetime import datetime, timezone
from typing import Annotated, TypeAlias

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from labguard_api.database import get_db
from labguard_api.errors import forbidden, lab_not_found, unauthenticated
from labguard_api.models import Lab, LabMembership, Role, User, UserSession
from labguard_api.security import SESSION_COOKIE, hash_session_token

Db: TypeAlias = Annotated[Session, Depends(get_db)]


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _active_session(db: Session, raw_token: str) -> UserSession | None:
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(raw_token))
    )
    if session is None or session.revoked_at is not None:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    return session


async def get_current_session(
    db: Db,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> tuple[User, UserSession]:
    raw = session_cookie or _bearer_token(authorization)
    if not raw:
        raise unauthenticated()
    session = _active_session(db, raw)
    if session is None:
        raise unauthenticated()
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise unauthenticated()
    return user, session


async def get_current_user(
    session: Annotated[tuple[User, UserSession], Depends(get_current_session)],
) -> User:
    return session[0]


CurrentUser: TypeAlias = Annotated[User, Depends(get_current_user)]
CurrentSession: TypeAlias = Annotated[tuple[User, UserSession], Depends(get_current_session)]


def require_global_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise forbidden("Only administrators may perform this action.")
    return user


GlobalAdmin = Annotated[User, Depends(require_global_admin)]


def membership_role(db: Session, user_id: object, lab_id: object) -> str | None:
    return db.scalar(
        select(LabMembership.role).where(
            LabMembership.user_id == user_id, LabMembership.lab_id == lab_id
        )
    )


def get_visible_lab(db: Db, user: CurrentUser, lab_id: object) -> Lab:
    """Return the lab iff the caller may see it; otherwise 404."""
    lab = db.get(Lab, lab_id)
    if lab is None or not lab.is_active:
        raise lab_not_found()
    if user.role == Role.ADMIN:
        return lab
    if membership_role(db, user.id, lab.id) is None:
        raise lab_not_found()
    return lab


def require_lab_manager(db: Db, user: CurrentUser, lab_id: object) -> Lab:
    """Global admins and lab members with the admin role may manage a lab.

    Callers without any membership get the same 404 as for a missing lab
    so membership cannot be probed via manager-only endpoints.
    """
    lab = db.get(Lab, lab_id)
    if lab is None or not lab.is_active:
        raise lab_not_found()
    if user.role == Role.ADMIN:
        return lab
    role = membership_role(db, user.id, lab.id)
    if role is None:
        raise lab_not_found()
    if role != Role.ADMIN:
        raise forbidden("Only lab managers may perform this action.")
    return lab


def client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host
