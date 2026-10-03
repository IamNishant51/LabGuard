"""Password hashing and opaque token helpers.

Passwords: bcrypt (cost 12). Bcrypt accepts at most 72 bytes; longer
input is rejected at the schema layer with a clear 422, never truncated.
Session tokens: 256-bit secrets; only the SHA-256 hex digest is stored.
Device credentials (M4) use the same construction as sessions: 256-bit
opaque tokens with SHA-256 hashes at rest, shown once at issuance.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

BCRYPT_ROUNDS = 12
BCRYPT_MAX_BYTES = 72
SESSION_TTL = timedelta(hours=12)
SESSION_COOKIE = "labguard_session"


def session_expiry(now: datetime | None = None) -> datetime:
    base = now or datetime.now(timezone.utc)
    return base + SESSION_TTL


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    """High-entropy opaque token shown to the client only via the session cookie."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    # utf-8 (not ascii): untrusted cookie/header values must never raise
    # UnicodeEncodeError here; garbage in means "no such session" (401).
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_device_token() -> str:
    """High-entropy per-device bearer token, shown once at issuance (M4)."""
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    """SHA-256 hex digest for storage; raw device tokens are never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
