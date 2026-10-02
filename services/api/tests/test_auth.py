"""Auth/session tests: login, cookies, bearer, expiry, logout, throttling."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labguard_api.models import Role, User, UserSession
from labguard_api.security import SESSION_COOKIE, hash_session_token
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login, make_user


def test_login_sets_cookie_and_me(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    response = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert SESSION_COOKIE in response.cookies
    assert "password" not in response.json()

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL


def test_login_case_insensitive_email(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "  ADMIN@college.example ", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def test_wrong_password_and_unknown_user_share_response(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    bad_password = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password-1"}
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@college.example", "password": "wrong-password-1"},
    )
    assert bad_password.status_code == 401
    assert unknown.status_code == 401
    assert bad_password.json() == unknown.json() == {
        "error": {"code": "UNAUTHENTICATED", "message": "Authentication is required."}
    }


def test_inactive_user_cannot_login(client: TestClient, db: Session) -> None:
    user = make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    user.is_active = False
    db.flush()
    response = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 401


def test_me_without_session_is_401(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_bearer_token_authenticates(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    raw = client.cookies.get(SESSION_COOKIE)
    assert raw

    bare = TestClient(client.app)
    bare.headers.update({"Authorization": f"Bearer {raw}"})
    assert bare.get("/api/v1/auth/me").status_code == 200


def test_raw_session_token_never_stored(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    raw = client.cookies.get(SESSION_COOKIE)
    assert raw
    stored = db.scalar(select(UserSession))
    assert stored is not None
    assert stored.token_hash != raw
    assert stored.token_hash == hash_session_token(raw)


def test_expired_session_rejected(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    session = db.scalar(select(UserSession))
    assert session is not None
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_session(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    raw = client.cookies.get(SESSION_COOKIE)
    assert raw

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401

    stored = db.scalar(select(UserSession).where(UserSession.token_hash == hash_session_token(raw)))
    assert stored is not None and stored.revoked_at is not None


def test_login_throttled_after_burst(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    statuses = {
        client.post(
            "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password-1"}
        ).status_code
        for _ in range(25)
    }
    assert 429 in statuses


def test_deactivated_user_session_rejected(client: TestClient, db: Session) -> None:
    user = make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    user.is_active = False
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_user_serialization_exposes_no_secrets(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.STAFF)
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    body = client.get("/api/v1/auth/me").json()
    assert set(body) == {"id", "email", "display_name", "role", "is_active"}


def test_second_user_model_defaults(db: Session) -> None:
    user: User = make_user(db)
    assert user.role == Role.VIEWER
    assert user.is_active is True


def test_garbage_session_token_is_401_not_500(client: TestClient, db: Session) -> None:
    make_user(db, email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=Role.ADMIN)
    for bad in ("not-a-real-token", "%ff%00", "a" * 5000):
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"}
        )
        assert response.status_code == 401, bad
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    # Non-ascii input must hash (never raise) so it resolves to "unknown
    # session" instead of a 500; httpx cannot transmit such headers, so this
    # exercises the hashing layer directly.
    assert hash_session_token("héllo-wörld") != hash_session_token("other")
