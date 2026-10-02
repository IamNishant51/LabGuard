"""Auth routes: bootstrap, login, logout, me.

Sessions are opaque tokens in an HttpOnly SameSite=Lax cookie (browsers)
or an Authorization Bearer header (API clients). Only token hashes rest
in the database. Login is throttled per client IP.
"""

import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from labguard_api.database import get_db
from labguard_api.deps import CurrentSession
from labguard_api.errors import ApiError, unauthenticated
from labguard_api.models import Role, User, UserSession
from labguard_api.schemas import BootstrapIn, LoginIn, UserOut
from labguard_api.security import (
    SESSION_COOKIE,
    hash_password,
    hash_session_token,
    new_session_token,
    session_expiry,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_ATTEMPTS = 20
_attempts: dict[str, deque[float]] = defaultdict(deque)


def _login_allowed(key: str) -> bool:
    now = time.monotonic()
    window = _attempts[key]
    while window and window[0] <= now - LOGIN_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= LOGIN_MAX_ATTEMPTS:
        return False
    window.append(now)
    return True


def reset_login_attempts() -> None:
    """Test hook: clear the in-memory throttle."""
    _attempts.clear()


def _set_cookie(response: Response, raw: str) -> None:
    # Secure flag goes on with HTTPS in M9; the LAN/plain-HTTP pilot needs
    # the cookie transmitted, so it stays off until TLS is enforced.
    response.set_cookie(
        SESSION_COOKIE, raw, httponly=True, samesite="lax", secure=False, path="/"
    )


@router.post("/bootstrap", response_model=UserOut, status_code=201)
def bootstrap(payload: BootstrapIn, db: Session = Depends(get_db)) -> User:
    """Create the initial global admin. Works only when no users exist.

    The count-then-insert check races when two requests arrive together.
    On PostgreSQL a transaction-scoped advisory lock serializes bootstrap
    attempts so exactly one wins; the loser re-checks and gets 403.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('labguard_bootstrap'))")
        )
    existing = db.scalar(select(func.count()).select_from(User))
    if existing:
        raise ApiError(
            "BOOTSTRAP_CLOSED",
            "Initial setup is already complete. Ask an administrator for access.",
            403,
        )
    user = User(
        email=payload.email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role=Role.ADMIN,
    )
    db.add(user)
    db.flush()
    return user


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    key = request.client.host if request.client else "unknown"
    if not _login_allowed(key):
        raise ApiError("RATE_LIMITED", "Too many login attempts. Try again shortly.", 429)
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise unauthenticated()
    if not user.is_active:
        raise unauthenticated()
    raw = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(raw),
            expires_at=session_expiry(),
            ip=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent", "")[:256] or None),
        )
    )
    db.flush()
    _set_cookie(response, raw)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response, current: CurrentSession, db: Session = Depends(get_db)) -> None:
    _user, session = current
    session.revoked_at = datetime.now(timezone.utc)
    db.add(session)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(current: CurrentSession) -> User:
    return current[0]
