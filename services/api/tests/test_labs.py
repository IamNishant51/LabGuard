"""Lab authorization tests: roles, scoping, and cross-lab isolation."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from labguard_api.models import Lab, LabMembership, Role
from tests.conftest import login, make_user


def _lab(client: TestClient, name: str = "Physics Lab") -> dict:
    response = client.post("/api/v1/labs", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _other_client(app_client: TestClient, email: str, password: str) -> TestClient:
    client = TestClient(app_client.app)
    login(client, email, password)
    return client


def test_admin_creates_and_reads_lab(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    login(client, admin.email, "password-1234-abcdef")
    lab = _lab(client)
    assert client.get(f"/api/v1/labs/{lab['id']}").status_code == 200


def test_duplicate_lab_name_conflicts(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    login(client, admin.email, "password-1234-abcdef")
    assert _lab(client, "Chem Lab")["name"] == "Chem Lab"
    response = client.post("/api/v1/labs", json={"name": "Chem Lab"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LAB_EXISTS"


def test_non_admin_cannot_create_lab(client: TestClient, db: Session) -> None:
    staff = make_user(db, email="staff@college.example", role=Role.STAFF)
    login(client, staff.email, "password-1234-abcdef")
    response = client.post("/api/v1/labs", json={"name": "Physics Lab"})
    assert response.status_code == 403


def test_unauthenticated_lab_access_is_401(client: TestClient) -> None:
    assert client.get("/api/v1/labs").status_code == 401
    assert client.post("/api/v1/labs", json={"name": "X"}).status_code == 401
    assert client.get(f"/api/v1/labs/{uuid.uuid4()}").status_code == 401


def test_list_scoped_to_memberships(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    viewer = make_user(db, email="viewer@college.example", role=Role.VIEWER)
    outsider = make_user(db, email="outsider@college.example", role=Role.VIEWER)
    login(client, admin.email, "password-1234-abcdef")
    lab_a = _lab(client, "Lab A")
    _lab(client, "Lab B")
    db.add(LabMembership(user_id=viewer.id, lab_id=uuid.UUID(lab_a["id"]), role=Role.VIEWER))
    db.flush()

    admin_list = client.get("/api/v1/labs")
    assert admin_list.json()["total"] == 2

    viewer_client = _other_client(client, viewer.email, "password-1234-abcdef")
    seen = viewer_client.get("/api/v1/labs").json()
    assert seen["total"] == 1 and seen["items"][0]["name"] == "Lab A"

    outsider_client = _other_client(client, outsider.email, "password-1234-abcdef")
    assert outsider_client.get("/api/v1/labs").json()["total"] == 0


def test_cross_lab_access_is_hidden_404(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    member = make_user(db, email="member@college.example", role=Role.VIEWER)
    login(client, admin.email, "password-1234-abcdef")
    lab_a = _lab(client, "Lab A")
    lab_b = _lab(client, "Lab B")
    db.add(LabMembership(user_id=member.id, lab_id=uuid.UUID(lab_a["id"]), role=Role.VIEWER))
    db.flush()

    member_client = _other_client(client, member.email, "password-1234-abcdef")
    assert member_client.get(f"/api/v1/labs/{lab_a['id']}").status_code == 200
    forbidden_lab = member_client.get(f"/api/v1/labs/{lab_b['id']}")
    assert forbidden_lab.status_code == 404
    assert forbidden_lab.json()["error"]["code"] == "LAB_NOT_FOUND"
    assert member_client.get(f"/api/v1/labs/{uuid.uuid4()}").status_code == 404


def test_only_managers_change_membership(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    manager = make_user(db, email="manager@college.example", role=Role.STAFF)
    plain = make_user(db, email="plain@college.example", role=Role.STAFF)
    newcomer = make_user(db, email="new@college.example", role=Role.VIEWER)
    login(client, admin.email, "password-1234-abcdef")
    lab = _lab(client, "Managed Lab")
    db.add_all(
        [
            LabMembership(user_id=manager.id, lab_id=uuid.UUID(lab["id"]), role=Role.ADMIN),
            LabMembership(user_id=plain.id, lab_id=uuid.UUID(lab["id"]), role=Role.STAFF),
        ]
    )
    db.flush()

    manager_client = _other_client(client, manager.email, "password-1234-abcdef")
    added = manager_client.post(
        f"/api/v1/labs/{lab['id']}/members",
        json={"user_id": str(newcomer.id), "role": Role.VIEWER},
    )
    assert added.status_code == 201, added.text

    plain_client = _other_client(client, plain.email, "password-1234-abcdef")
    denied = plain_client.post(
        f"/api/v1/labs/{lab['id']}/members",
        json={"user_id": str(newcomer.id), "role": Role.VIEWER},
    )
    assert denied.status_code == 403


def test_manager_endpoints_hide_lab_from_non_members(
    client: TestClient, db: Session
) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    outsider = make_user(db, email="outsider@college.example", role=Role.STAFF)
    target = make_user(db, email="target@college.example", role=Role.VIEWER)
    login(client, admin.email, "password-1234-abcdef")
    lab = _lab(client, "Hidden Lab")

    outsider_client = _other_client(client, outsider.email, "password-1234-abcdef")
    add = outsider_client.post(
        f"/api/v1/labs/{lab['id']}/members",
        json={"user_id": str(target.id), "role": Role.VIEWER},
    )
    assert add.status_code == 404
    assert add.json()["error"]["code"] == "LAB_NOT_FOUND"
    remove = outsider_client.delete(
        f"/api/v1/labs/{lab['id']}/members/{target.id}"
    )
    assert remove.status_code == 404


def test_blank_lab_name_rejected(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    login(client, admin.email, "password-1234-abcdef")
    response = client.post("/api/v1/labs", json={"name": "   "})
    assert response.status_code == 422


def test_member_add_and_remove_roundtrip(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    target = make_user(db, email="target@college.example", role=Role.VIEWER)
    login(client, admin.email, "password-1234-abcdef")
    lab = _lab(client, "Roundtrip Lab")

    added = client.post(
        f"/api/v1/labs/{lab['id']}/members",
        json={"user_id": str(target.id), "role": Role.STAFF},
    )
    assert added.status_code == 201
    assert added.json()["role"] == Role.STAFF

    removed = client.delete(f"/api/v1/labs/{lab['id']}/members/{target.id}")
    assert removed.status_code == 204

    target_client = _other_client(client, target.email, "password-1234-abcdef")
    assert target_client.get(f"/api/v1/labs/{lab['id']}").status_code == 404


def test_pagination_bounds_enforced(client: TestClient, db: Session) -> None:
    admin = make_user(db, email="admin@college.example", role=Role.ADMIN)
    login(client, admin.email, "password-1234-abcdef")
    _lab(client, "Paged Lab")
    assert client.get("/api/v1/labs?page_size=0").status_code == 422
    assert client.get("/api/v1/labs?page_size=101").status_code == 422
    body = client.get("/api/v1/labs?page=1&page_size=1").json()
    assert body["page"] == 1 and body["page_size"] == 1 and body["total"] == 1
    assert set(body) == {"items", "page", "page_size", "total"}


def test_lab_membership_model_links(db: Session) -> None:
    lab = Lab(name="Model Lab")
    user = make_user(db)
    db.add(lab)
    db.flush()
    db.add(LabMembership(user_id=user.id, lab_id=lab.id, role=Role.ADMIN))
    db.flush()
    assert lab.memberships[0].role == Role.ADMIN
