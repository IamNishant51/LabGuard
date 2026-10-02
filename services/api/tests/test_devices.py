"""Device management tests (M3): registration, listing, detail, updates, authz, audit."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labguard_api.models import AuditLog, Device, Lab, LabMembership, Role
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


def _device(client: TestClient, lab_id: str, hostname: str = "lab-pc-01", **extra: object) -> dict:
    payload: dict[str, object] = {"lab_id": lab_id, "hostname": hostname}
    payload.update(extra)
    response = client.post("/api/v1/devices", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_registers_device(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    body = _device(
        client, lab["id"], "LAB-PC-023", display_name="Front row", platform="Windows",
        agent_version="0.1.0",
    )
    assert body["hostname"] == "lab-pc-023"
    assert body["lab_id"] == lab["id"]
    assert body["is_active"] is True
    assert body["last_seen_at"] is None
    assert set(body) == {
        "id", "lab_id", "hostname", "display_name", "platform",
        "agent_version", "is_active", "last_seen_at", "created_at", "updated_at",
    }
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "device.registered")).all()
    assert len(rows) == 1
    assert rows[0].entity_type == "device" and rows[0].entity_id == body["id"]
    assert rows[0].actor_user_id is not None
    assert rows[0].meta is not None and rows[0].meta["hostname"] == "lab-pc-023"
    assert set(rows[0].meta) <= {
        "hostname", "lab_id", "display_name", "platform",
        "agent_version", "is_active", "changed",
    }


def test_register_validation_errors(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    for payload in (
        {"lab_id": lab["id"], "hostname": "   "},
        {"lab_id": lab["id"], "hostname": "bad host!"},
        {"lab_id": lab["id"], "hostname": "x" * 256},
        {"lab_id": lab["id"], "hostname": "ok-01", "display_name": "  "},
        {"lab_id": lab["id"], "hostname": "ok-01", "platform": "x" * 33},
        {"lab_id": "not-a-uuid", "hostname": "ok-01"},
        {"hostname": "ok-01"},
    ):
        response = client.post("/api/v1/devices", json=payload)
        assert response.status_code == 422, (payload, response.text)


def test_register_unknown_or_inactive_lab_is_404(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    assert client.post(
        "/api/v1/devices", json={"lab_id": str(uuid.uuid4()), "hostname": "pc-01"}
    ).status_code == 404
    db.get(Lab, uuid.UUID(lab["id"])).is_active = False  # type: ignore[union-attr]
    db.flush()
    response = client.post("/api/v1/devices", json={"lab_id": lab["id"], "hostname": "pc-01"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LAB_NOT_FOUND"


def test_duplicate_hostname_conflicts_per_lab(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab_a = _lab(client, "Lab A")
    lab_b = _lab(client, "Lab B")
    _device(client, lab_a["id"], "shared-01")
    # Same hostname in a different lab is a different identity.
    assert _device(client, lab_b["id"], "shared-01")["hostname"] == "shared-01"
    # Duplicate check runs last: the failed flush poisons the shared test
    # session for further writes (production rolls each request back).
    response = client.post(
        "/api/v1/devices", json={"lab_id": lab_a["id"], "hostname": "SHARED-01"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DEVICE_EXISTS"


def test_concurrent_registration_race_is_409(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    # Simulate the loser of a concurrent-registration race: the identity
    # row already exists when the request flushes.
    db.add(Device(lab_id=uuid.UUID(lab["id"]), hostname="raced-pc"))
    db.flush()
    response = client.post("/api/v1/devices", json={"lab_id": lab["id"], "hostname": "RACED-PC"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DEVICE_EXISTS"


def test_unauthenticated_device_access_is_401(client: TestClient) -> None:
    device_id = uuid.uuid4()
    assert client.post("/api/v1/devices", json={}).status_code in (401, 422)
    assert client.get("/api/v1/devices").status_code == 401
    assert client.get(f"/api/v1/devices/{device_id}").status_code == 401
    assert client.patch(f"/api/v1/devices/{device_id}", json={}).status_code == 401


def test_device_write_roles(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client, "Lab A")
    viewer = make_user(db, email="viewer@college.example", role=Role.VIEWER)
    manager = make_user(db, email="manager@college.example", role=Role.STAFF)
    outsider = make_user(db, email="outsider@college.example", role=Role.STAFF)
    db.add_all(
        [
            LabMembership(user_id=viewer.id, lab_id=uuid.UUID(lab["id"]), role=Role.VIEWER),
            LabMembership(user_id=manager.id, lab_id=uuid.UUID(lab["id"]), role=Role.ADMIN),
        ]
    )
    db.flush()

    viewer_client = _other_client(client, viewer.email, "password-1234-abcdef")
    response = viewer_client.post(
        "/api/v1/devices", json={"lab_id": lab["id"], "hostname": "pc-01"}
    )
    assert response.status_code == 403

    outsider_client = _other_client(client, outsider.email, "password-1234-abcdef")
    response = outsider_client.post(
        "/api/v1/devices", json={"lab_id": lab["id"], "hostname": "pc-01"}
    )
    assert response.status_code == 404

    manager_client = _other_client(client, manager.email, "password-1234-abcdef")
    device = _device(manager_client, lab["id"], "pc-01")
    assert viewer_client.get(f"/api/v1/devices/{device['id']}").status_code == 200
    assert viewer_client.patch(
        f"/api/v1/devices/{device['id']}", json={"display_name": "Nope"}
    ).status_code == 403
    patched = manager_client.patch(
        f"/api/v1/devices/{device['id']}", json={"display_name": "Row 1"}
    )
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Row 1"


def test_cross_lab_device_is_hidden_404(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab_a = _lab(client, "Lab A")
    lab_b = _lab(client, "Lab B")
    member = make_user(db, email="member@college.example", role=Role.VIEWER)
    db.add(LabMembership(user_id=member.id, lab_id=uuid.UUID(lab_a["id"]), role=Role.VIEWER))
    db.flush()
    device_b = _device(client, lab_b["id"], "secret-pc")
    member_client = _other_client(client, member.email, "password-1234-abcdef")
    assert member_client.get(f"/api/v1/devices/{device_b['id']}").status_code == 404
    assert member_client.get("/api/v1/devices").json()["total"] == 0
    assert member_client.get("/api/v1/devices", params={"lab_id": lab_b["id"]}).status_code == 404


def test_list_pagination_search_and_filters(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab_a = _lab(client, "Lab A")
    lab_b = _lab(client, "Lab B")
    _device(client, lab_a["id"], "alpha-01")
    _device(client, lab_a["id"], "alpha-02")
    _device(client, lab_b["id"], "beta-01")
    client.patch(
        f"/api/v1/devices/{_device(client, lab_a['id'], 'alpha-03')['id']}",
        json={"is_active": False},
    )

    page1 = client.get("/api/v1/devices", params={"page_size": 2}).json()
    assert (page1["total"], page1["page"], page1["page_size"]) == (4, 1, 2)
    assert [d["hostname"] for d in page1["items"]] == ["alpha-01", "alpha-02"]
    page2 = client.get("/api/v1/devices", params={"page_size": 2, "page": 2}).json()
    assert [d["hostname"] for d in page2["items"]] == ["alpha-03", "beta-01"]
    clamped = client.get("/api/v1/devices", params={"page_size": 2, "page": 99}).json()
    assert clamped["page"] == 2 and clamped["total"] == 4

    assert client.get("/api/v1/devices", params={"q": "ALPHA"}).json()["total"] == 3
    assert client.get("/api/v1/devices", params={"lab_id": lab_b["id"]}).json()["total"] == 1
    assert client.get("/api/v1/devices", params={"is_active": False}).json()["total"] == 1
    assert client.get("/api/v1/devices", params={"is_active": True}).json()["total"] == 3
    assert client.get("/api/v1/devices", params={"page_size": 0}).status_code == 422


def test_deactivated_device_detail_stays_visible(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"], "old-pc")
    client.patch(f"/api/v1/devices/{device['id']}", json={"is_active": False})
    body = client.get(f"/api/v1/devices/{device['id']}").json()
    assert body["is_active"] is False and body["hostname"] == "old-pc"
    rows = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == device["id"]).order_by(AuditLog.id)
    ).all()
    assert [r.action for r in rows] == ["device.registered", "device.deactivated"]
    assert rows[1].meta is not None and rows[1].meta["changed"] == ["is_active"]


def test_patch_metadata_and_reactivate(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"], "pc-09", platform="Windows")
    response = client.patch(
        f"/api/v1/devices/{device['id']}",
        json={"display_name": "Teacher PC", "platform": "Ubuntu", "agent_version": "0.2.0"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["display_name"], body["platform"], body["agent_version"]) == (
        "Teacher PC", "Ubuntu", "0.2.0",
    )
    # Identity fields are immutable: unknown extras are ignored, never applied.
    response = client.patch(
        f"/api/v1/devices/{device['id']}",
        json={"hostname": "renamed", "lab_id": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["hostname"] == "pc-09"
    # A no-op patch succeeds without writing an audit row.
    audits_before = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == device["id"]).order_by(AuditLog.id)
    ).all()
    response = client.patch(f"/api/v1/devices/{device['id']}", json={})
    assert response.status_code == 200
    audits_after = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == device["id"]).order_by(AuditLog.id)
    ).all()
    assert len(audits_after) == len(audits_before)
    updated = audits_after
    assert [r.action for r in updated] == ["device.registered", "device.updated"]
    assert updated[1].meta is not None
    assert sorted(updated[1].meta["changed"]) == ["agent_version", "display_name", "platform"]


def test_patch_validation_and_missing_device(client: TestClient, db: Session) -> None:
    _admin(client, db)
    lab = _lab(client)
    device = _device(client, lab["id"], "pc-10")
    assert client.patch(
        f"/api/v1/devices/{device['id']}", json={"display_name": "   "}
    ).status_code == 422
    missing = client.patch(f"/api/v1/devices/{uuid.uuid4()}", json={"is_active": False})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DEVICE_NOT_FOUND"
    assert client.get(f"/api/v1/devices/{uuid.uuid4()}").status_code == 404
