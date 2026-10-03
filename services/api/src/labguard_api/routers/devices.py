"""Device endpoints (M3 surface + M4 enrollment and revocation).

Reads follow lab visibility; writes require lab managers. Anything the
caller may not see is 404 so device IDs cannot probe lab membership.
Raw device tokens appear exactly once, in the enrollment-token response;
heartbeats live in routers/agent.py.
"""

import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from labguard_api import audit
from labguard_api.database import get_db
from labguard_api.deps import (
    CurrentUser,
    get_visible_device,
    get_visible_lab,
    require_lab_manager,
)
from labguard_api.errors import ApiError
from labguard_api.models import AgentCredential, Device, Lab, LabMembership, Role, User
from labguard_api.schemas import (
    DeviceIn,
    DeviceOut,
    DevicePatch,
    EnrollmentTokenOut,
    Page,
    RevokeAgentOut,
)
from labguard_api.security import hash_device_token, new_device_token

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

MAX_PAGE_SIZE = 100
MAX_QUERY_LEN = 100


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _scoped_devices(user: User) -> Select[tuple[Device]]:
    """Devices in active labs the caller may see."""
    base = select(Device).join(Lab, Lab.id == Device.lab_id).where(Lab.is_active.is_(True))
    if user.role != Role.ADMIN:
        base = base.join(LabMembership, LabMembership.lab_id == Lab.id).where(
            LabMembership.user_id == user.id
        )
    return base


@router.post("", response_model=DeviceOut, status_code=201)
def register_device(
    payload: DeviceIn,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> Device:
    lab = require_lab_manager(db, user, payload.lab_id)
    device = Device(
        lab_id=lab.id,
        hostname=payload.hostname,
        display_name=payload.display_name,
        platform=payload.platform,
        agent_version=payload.agent_version,
    )
    db.add(device)
    try:
        db.flush()
    except IntegrityError:
        # Lost a concurrent-registration race for the same
        # (lab, hostname): the identity now exists, so report a
        # conflict instead of failing or creating a duplicate.
        raise ApiError(
            "DEVICE_EXISTS",
            "A device with this hostname is already registered in this lab.",
            409,
        )
    audit.record_audit(
        db,
        actor=user,
        action=audit.DEVICE_REGISTERED,
        entity_type="device",
        entity_id=device.id,
        metadata={
            "hostname": device.hostname,
            "lab_id": str(lab.id),
            "display_name": device.display_name,
            "platform": device.platform,
            "agent_version": device.agent_version,
        },
    )
    return device


@router.get("", response_model=Page)
def list_devices(
    user: CurrentUser,
    db: Session = Depends(get_db),
    lab_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=MAX_QUERY_LEN),
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE),
) -> Page:
    base = _scoped_devices(user)
    if lab_id is not None:
        # A filter pointing at an invisible lab reads as a missing lab,
        # never as an empty list, so lab membership cannot be probed.
        get_visible_lab(db, user, lab_id)
        base = base.where(Device.lab_id == lab_id)
    if q is not None and q.strip():
        needle = _escape_like(q.strip().lower())
        base = base.where(func.lower(Device.hostname).like(f"%{needle}%", escape="\\"))
    if is_active is not None:
        base = base.where(Device.is_active.is_(is_active))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    pages = max(math.ceil(total / page_size), 1)
    page = min(page, pages)
    devices = list(
        db.scalars(base.order_by(Device.hostname, Device.id).offset((page - 1) * page_size).limit(page_size))
    )
    return Page(
        items=[DeviceOut.model_validate(d).model_dump(mode="json") for d in devices],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)
) -> Device:
    return get_visible_device(db, user, device_id)


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: uuid.UUID,
    payload: DevicePatch,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> Device:
    device = get_visible_device(db, user, device_id)
    require_lab_manager(db, user, device.lab_id)
    changed: list[str] = []
    if payload.display_name is not None and payload.display_name != device.display_name:
        device.display_name = payload.display_name
        changed.append("display_name")
    if payload.platform is not None and payload.platform != device.platform:
        device.platform = payload.platform
        changed.append("platform")
    if payload.agent_version is not None and payload.agent_version != device.agent_version:
        device.agent_version = payload.agent_version
        changed.append("agent_version")
    if payload.is_active is not None and payload.is_active != device.is_active:
        device.is_active = payload.is_active
        changed.append("is_active")
    if not changed:
        return device
    db.flush()
    if "is_active" in changed:
        action = audit.DEVICE_REACTIVATED if device.is_active else audit.DEVICE_DEACTIVATED
    else:
        action = audit.DEVICE_UPDATED
    audit.record_audit(
        db,
        actor=user,
        action=action,
        entity_type="device",
        entity_id=device.id,
        metadata={
            "hostname": device.hostname,
            "lab_id": str(device.lab_id),
            "is_active": device.is_active,
            "changed": changed,
        },
    )
    return device


@router.post("/{device_id}/enrollment-token", response_model=EnrollmentTokenOut, status_code=201)
def issue_enrollment_token(
    device_id: uuid.UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> EnrollmentTokenOut:
    """Issue a per-device bearer token, shown raw exactly once (M4).

    Lab managers only, under the same visibility rules as PATCH: unknown
    or invisible devices read as 404. Only the hash is stored; rotation
    is revoke-then-issue via ``revoke-agent``.
    """
    device = get_visible_device(db, user, device_id)
    require_lab_manager(db, user, device.lab_id)
    raw = new_device_token()
    credential = AgentCredential(
        device_id=device.id, token_hash=hash_device_token(raw)
    )
    db.add(credential)
    try:
        db.flush()
    except IntegrityError:
        # Astronomically unlikely token-hash collision: fail transiently
        # rather than storing a duplicate or returning a 500 trace.
        raise ApiError(
            "TOKEN_COLLISION",
            "Could not issue a credential. Please try again.",
            503,
        )
    audit.record_audit(
        db,
        actor=user,
        action=audit.DEVICE_ENROLLMENT_ISSUED,
        entity_type="device",
        entity_id=device.id,
        metadata={
            "hostname": device.hostname,
            "lab_id": str(device.lab_id),
            "credential_id": str(credential.id),
        },
    )
    return EnrollmentTokenOut(
        device_id=device.id,
        credential_id=credential.id,
        token=raw,
        issued_at=credential.created_at,
        expires_at=credential.expires_at,
    )


@router.post("/{device_id}/revoke-agent", response_model=RevokeAgentOut)
def revoke_agent(
    device_id: uuid.UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> RevokeAgentOut:
    """Revoke every active credential for a device (M4).

    Lab managers only, same visibility rules as PATCH. Idempotent: when
    nothing is active the call succeeds with ``revoked: 0`` and writes
    no audit row (mirroring the M3 no-op-patch rule).
    """
    device = get_visible_device(db, user, device_id)
    require_lab_manager(db, user, device.lab_id)
    now = datetime.now(timezone.utc)
    active = list(        db.scalars(
            select(AgentCredential).where(
                AgentCredential.device_id == device.id,
                AgentCredential.revoked_at.is_(None),
            )
        )
    )
    for credential in active:
        credential.revoked_at = now
        db.flush()
        audit.record_audit(
            db,
            actor=user,
            action=audit.DEVICE_CREDENTIAL_REVOKED,
            entity_type="device",
            entity_id=device.id,
            metadata={
                "hostname": device.hostname,
                "lab_id": str(device.lab_id),
                "credential_id": str(credential.id),
            },
        )
    return RevokeAgentOut(device_id=device.id, revoked=len(active))
