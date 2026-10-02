"""Bootstrap tests: first admin creation, then permanently closed."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labguard_api.models import Role, User
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_bootstrap_creates_global_admin(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "  Founder@College.Example ",
            "password": "initial-admin-pass-1",
            "display_name": "Founding Admin",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "founder@college.example"  # normalized
    assert body["role"] == Role.ADMIN
    assert "password" not in body and "password_hash" not in body

    stored = db.scalar(select(User).where(User.email == "founder@college.example"))
    assert stored is not None
    assert stored.password_hash != "initial-admin-pass-1"
    assert stored.password_hash.startswith("$2")


def test_bootstrap_closed_once_users_exist(client: TestClient, db: Session) -> None:
    first = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "display_name": "A"},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "second@college.example", "password": ADMIN_PASSWORD, "display_name": "B"},
    )
    assert second.status_code == 403
    assert second.json() == {
        "error": {
            "code": "BOOTSTRAP_CLOSED",
            "message": "Initial setup is already complete. Ask an administrator for access.",
        }
    }
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_bootstrap_rejects_weak_password(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": ADMIN_EMAIL, "password": "short", "display_name": "A"},
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_bootstrap_rejects_bad_email(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "not-an-email", "password": ADMIN_PASSWORD, "display_name": "A"},
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_bootstrap_rejects_blank_display_name(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "display_name": "   "},
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(User)) == 0
