"""Enrollment and heartbeat tests (M4): issuance, auth, lifecycle, audit, secrecy."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from labguard_api.models import AgentCredential, AuditLog, Device, LabMembership, Metric, Role
from labguard_api.security import hash_device_token
from tests.conftest import login, make_user


def _other_client(app_client: TestClient, email: str, password: str) -> TestClient:
    client = TestClient(app_client.app)
    login(client, email, password)
    return client


def _admin(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    login(client, admin.email, "password-1234-abcdef")


def _lab(client: TestClient, name: str = "Physics Lab") -> dict:
    response = client.post("/api/v1/labs", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _device(client: TestClient, lab_id: str, hostname: str = "lab-pc-01") -> dict:
    response = client.post("/api/v1/devices", json={"lab_id": lab_id, "hostname": hostname})
    assert response.status_code == 201, response.text
    return response.json()


def _issue(client: TestClient, device_id: str) -> dict:
    response = client.post(f"/api/v1/devices/{device_id}/enrollment-token")
    assert response.status_code == 201, response.text
    return response.json()


def _heartbeat_payload(**extra: object) -> dict:
    body: dict[str, object] = {
        "platform": "Windows",
        "agent_version": "0.4.0",
        "metrics": {
            "cpu_percent": 24.8,
            "memory_percent": 68.2,
            "memory_used_bytes": 7300000000,
            "memory_total_bytes": 16000000000,
            "volumes": [
                {
                    "label": "C:",
                    "disk_percent": 71.4,
                    "used_bytes": 250000000000,
                    "total_bytes": 350000000000,
                }
            ],
        },
    }
    body.update(extra)
    return body


def _beat(token: str, payload: dict | None = None) -> dict:
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "json": _heartbeat_payload() if payload is None else payload,
    }


def test_issue_stores_hash_and_shows_token_once(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    body = _issue(client, device["id"])
    assert body["device_id"] == device["id"]
    assert body["expires_at"] is None
    raw = body["token"]
    assert isinstance(raw, str) and len(raw) >= 32

    credential = db.scalar(
        select(AgentCredential).where(AgentCredential.id == uuid.UUID(body["credential_id"]))
    )
    assert credential is not None
    assert credential.token_hash != raw
    assert credential.token_hash == hash_device_token(raw)
    assert credential.revoked_at is None

    # The raw token appears nowhere else: device reads carry no secrets.
    for response in (
        client.get(f"/api/v1/devices/{device['id']}"),
        client.get("/api/v1/devices"),
        client.patch(f"/api/v1/devices/{device['id']}", json={"display_name": "Row 1"}),
    ):
        assert response.status_code == 200, response.text
        assert raw not in response.text


def test_heartbeat_accepts_and_stamps_server_time(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    raw = _issue(client, device["id"])["token"]
    before = datetime.now(timezone.utc)

    response = client.post("/api/v1/agent/heartbeat", **_beat(raw))
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True

    metric = db.scalars(select(Metric)).one()
    assert metric.device_id == uuid.UUID(device["id"])
    # SQLite returns naive datetimes; normalize before comparing (PG is tz-aware).
    recorded = metric.recorded_at
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    assert before <= recorded <= datetime.now(timezone.utc)
    assert metric.cpu_percent == pytest.approx(24.8)
    assert metric.memory_percent == pytest.approx(68.2)
    assert len(metric.volumes) == 1
    assert metric.volumes[0].label == "C:"

    stored = db.get(Device, uuid.UUID(device["id"]))
    assert stored is not None and stored.last_seen_at == metric.recorded_at
    assert (stored.platform, stored.agent_version) == ("Windows", "0.4.0")
    credential = db.scalars(select(AgentCredential)).one()
    assert credential.last_used_at == metric.recorded_at


def test_heartbeat_ignores_body_identity(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    raw = _issue(client, device["id"])["token"]
    payload = _heartbeat_payload(hostname="someone-elses-pc")
    response = client.post("/api/v1/agent/heartbeat", **_beat(raw, payload))
    assert response.status_code == 200, response.text
    assert db.scalars(select(Metric)).one().device_id == uuid.UUID(device["id"])


def test_heartbeat_rejects_bad_tokens_uniformly(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    raw = _issue(client, device["id"])["token"]

    assert client.post("/api/v1/agent/heartbeat", json=_heartbeat_payload()).status_code == 401
    for bad in ("not-a-real-token", raw + "x", ""):
        response = client.post(
            "/api/v1/agent/heartbeat",
            headers={"Authorization": f"Bearer {bad}"},
            json=_heartbeat_payload(),
        )
        assert response.status_code == 401, bad
        assert response.json()["error"] == {
            "code": "UNAUTHENTICATED",
            "message": "Invalid or revoked device credential.",
        }


def test_revoked_token_cannot_authenticate(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    raw = _issue(client, device["id"])["token"]
    assert client.post("/api/v1/agent/heartbeat", **_beat(raw)).status_code == 200

    revoked = client.post(f"/api/v1/devices/{device['id']}/revoke-agent")
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"device_id": device["id"], "revoked": 1}
    assert client.post("/api/v1/agent/heartbeat", **_beat(raw)).status_code == 401

    # Idempotent: revoking again succeeds with zero and writes no audit row.
    audits_before = db.scalars(select(AuditLog)).all()
    again = client.post(f"/api/v1/devices/{device['id']}/revoke-agent")
    assert again.status_code == 200 and again.json()["revoked"] == 0
    assert len(db.scalars(select(AuditLog)).all()) == len(audits_before)


def test_expired_token_cannot_authenticate(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    body = _issue(client, device["id"])
    credential = db.scalar(
        select(AgentCredential).where(AgentCredential.id == uuid.UUID(body["credential_id"]))
    )
    assert credential is not None
    credential.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    assert client.post("/api/v1/agent/heartbeat", **_beat(body["token"])).status_code == 401


def test_disabled_device_or_lab_rejects_heartbeat(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client, "Lab A")
    lab_b = _lab(client, "Lab B")
    device = _device(client, lab["id"])
    device_b = _device(client, lab_b["id"])
    raw = _issue(client, device["id"])["token"]
    raw_b = _issue(client, device_b["id"])["token"]

    client.patch(f"/api/v1/devices/{device['id']}", json={"is_active": False})
    assert client.post("/api/v1/agent/heartbeat", **_beat(raw)).status_code == 401
    client.patch(f"/api/v1/devices/{device['id']}", json={"is_active": True})
    assert client.post("/api/v1/agent/heartbeat", **_beat(raw)).status_code == 200
    assert client.post("/api/v1/agent/heartbeat", **_beat(raw_b)).status_code == 200


def test_rotation_revoke_then_issue(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    old = _issue(client, device["id"])["token"]
    assert client.post(f"/api/v1/devices/{device['id']}/revoke-agent").json()["revoked"] == 1
    new = _issue(client, device["id"])["token"]
    assert new != old
    assert client.post("/api/v1/agent/heartbeat", **_beat(old)).status_code == 401
    assert client.post("/api/v1/agent/heartbeat", **_beat(new)).status_code == 200


def test_multiple_active_credentials_all_revoke_together(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    first = _issue(client, device["id"])["token"]
    second = _issue(client, device["id"])["token"]
    assert client.post("/api/v1/agent/heartbeat", **_beat(first)).status_code == 200
    assert client.post("/api/v1/agent/heartbeat", **_beat(second)).status_code == 200
    assert client.post(f"/api/v1/devices/{device['id']}/revoke-agent").json()["revoked"] == 2
    assert client.post("/api/v1/agent/heartbeat", **_beat(first)).status_code == 401
    assert client.post("/api/v1/agent/heartbeat", **_beat(second)).status_code == 401


def test_enrollment_authorization(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab_a = _lab(client, "Lab A")
    lab_b = _lab(client, "Lab B")
    device_b = _device(client, lab_b["id"])
    viewer = make_user(db, email="viewer@college.example", role=Role.VIEWER)
    manager = make_user(db, email="manager@college.example", role=Role.STAFF)
    outsider = make_user(db, email="outsider@college.example", role=Role.STAFF)
    db.add_all(
        [
            LabMembership(
                user_id=viewer.id, lab_id=uuid.UUID(lab_a["id"]), role=Role.VIEWER
            ),
            LabMembership(
                user_id=manager.id, lab_id=uuid.UUID(lab_a["id"]), role=Role.ADMIN
            ),
        ]
    )
    db.flush()

    viewer_client = _other_client(client, viewer.email, "password-1234-abcdef")
    outsider_client = _other_client(client, outsider.email, "password-1234-abcdef")
    manager_client = _other_client(client, manager.email, "password-1234-abcdef")

    # Unauthenticated callers get 401 on both endpoints.
    bare = TestClient(client.app)
    assert bare.post(f"/api/v1/devices/{device_b['id']}/enrollment-token").status_code == 401
    assert bare.post(f"/api/v1/devices/{device_b['id']}/revoke-agent").status_code == 401

    # Lab members without the manager role get 403; outsiders get 404.
    device_a = _device(manager_client, lab_a["id"])
    assert (
        viewer_client.post(f"/api/v1/devices/{device_a['id']}/enrollment-token").status_code
        == 403
    )
    assert (
        viewer_client.post(f"/api/v1/devices/{device_a['id']}/revoke-agent").status_code
        == 403
    )
    assert (
        outsider_client.post(f"/api/v1/devices/{device_a['id']}/enrollment-token").status_code
        == 404
    )
    # Cross-lab enrollment reads as a missing device, never a lab problem.
    assert (
        manager_client.post(
            f"/api/v1/devices/{device_b['id']}/enrollment-token"
        ).status_code
        == 404
    )
    missing = manager_client.post(f"/api/v1/devices/{uuid.uuid4()}/enrollment-token")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DEVICE_NOT_FOUND"
    assert (
        manager_client.post(f"/api/v1/devices/{device_a['id']}/enrollment-token").status_code
        == 201
    )


def test_heartbeat_payload_validation(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    raw = _issue(client, device["id"])["token"]

    def metrics(**over: object) -> dict:
        base: dict[str, object] = {"cpu_percent": 10.0, "memory_percent": 20.0}
        base.update(over)
        return base

    bad_payloads = [
        {},
        {"metrics": metrics(cpu_percent=101)},
        {"metrics": metrics(cpu_percent=-1)},
        {"metrics": metrics(memory_percent=100.1)},
        {"metrics": metrics(memory_used_bytes=-1)},
        {"metrics": metrics(volumes=[{
            "label": "C:", "disk_percent": 0, "used_bytes": 0, "total_bytes": 1,
        }] * 33)},
        {"metrics": metrics(volumes=[{
            "label": "  ", "disk_percent": 0, "used_bytes": 0, "total_bytes": 1,
        }])},
        {"metrics": metrics(volumes=[{
            "label": "C:", "disk_percent": 100.5, "used_bytes": 0, "total_bytes": 1,
        }])},
        {"platform": "x" * 33, "metrics": metrics()},
    ]
    for payload in bad_payloads:
        response = client.post("/api/v1/agent/heartbeat", **_beat(raw, payload))
        assert response.status_code == 422, payload
    assert db.scalars(select(Metric)).all() == []


def test_audit_rows_for_lifecycle_and_no_row_for_heartbeat(
    client: TestClient, db: Session
) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"])
    body = _issue(client, device["id"])
    assert client.post("/api/v1/agent/heartbeat", **_beat(body["token"])).status_code == 200
    client.post(f"/api/v1/devices/{device['id']}/revoke-agent")

    rows = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == device["id"]).order_by(AuditLog.id)
    ).all()
    assert [r.action for r in rows] == [
        "device.registered",
        "device.enrollment_issued",
        "device.credential_revoked",
    ]
    assert all(r.actor_user_id is not None and r.entity_type == "device" for r in rows)
    assert rows[1].meta is not None and rows[1].meta["credential_id"] == body["credential_id"]
    assert rows[2].meta is not None and rows[2].meta["credential_id"] == body["credential_id"]

    # No secret material anywhere in the audit trail.
    for row in db.scalars(select(AuditLog)).all():
        assert set(row.meta or {}) <= {
            "hostname", "lab_id", "display_name", "platform",
            "agent_version", "is_active", "changed", "credential_id",
        }
        assert body["token"] not in str(row.meta)
        assert hash_device_token(body["token"]) not in str(row.meta)


def test_duplicate_token_hash_rejected_by_constraint(db: Session) -> None:
    credential = AgentCredential(
        device_id=uuid.uuid4(), token_hash="0" * 64
    )
    db.add(credential)
    db.flush()
    db.add(AgentCredential(device_id=uuid.uuid4(), token_hash="0" * 64))
    with pytest.raises(IntegrityError):
        db.flush()
