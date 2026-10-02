"""Device endpoints (M3 surface): register/list/get/patch devices.

Reads follow lab visibility; writes require lab managers. Anything the
caller may not see is 404 so device IDs cannot probe lab membership.
Enrollment tokens, credential revocation, and heartbeats arrive in M4:
this router never issues, accepts, or returns device secrets.
"""

import math
import uuid

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
from labguard_api.models import Device, Lab, LabMembership, Role, User
from labguard_api.schemas import DeviceIn, DeviceOut, DevicePatch, Page

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
