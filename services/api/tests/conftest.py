"""M2 test wiring: isolated SQLite database per test, TestClient with get_db override."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from labguard_api.database import get_db
from labguard_api.db import Base
from labguard_api.main import app
from labguard_api.models import Role, User
from labguard_api.routers.auth import reset_login_attempts
from labguard_api.security import hash_password

ADMIN_EMAIL = "admin@college.example"
ADMIN_PASSWORD = "correct-horse-battery-staple-1"


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override
    reset_login_attempts()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(
    db: Session,
    email: str = "user@college.example",
    password: str = "password-1234-abcdef",
    role: str = Role.VIEWER,
    display_name: str = "Test User",
) -> User:
    user = User(
        email=email.strip().lower(),
        display_name=display_name,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
