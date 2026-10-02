"""Lab endpoints (M2 surface): create/list/get labs, manage memberships.

Device CRUD, search, and audit events live in routers/devices.py (M3).
Every route is server-side authorized: global admins see everything,
other users only labs they belong to, and anything else is 404.
"""

import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from labguard_api.database import get_db
from labguard_api.deps import CurrentUser, GlobalAdmin, get_visible_lab, require_lab_manager
from labguard_api.errors import ApiError, lab_not_found
from labguard_api.models import Lab, LabMembership, Role, User
from labguard_api.schemas import LabIn, LabOut, MemberIn, MemberOut, Page

router = APIRouter(prefix="/api/v1/labs", tags=["labs"])

MAX_PAGE_SIZE = 100


@router.post("", response_model=LabOut, status_code=201)
def create_lab(
    payload: LabIn, _admin: GlobalAdmin, db: Session = Depends(get_db)
) -> Lab:
    lab = Lab(name=payload.name.strip(), location=payload.location)
    db.add(lab)
    try:
        db.flush()
    except IntegrityError:
        raise ApiError("LAB_EXISTS", "A lab with this name already exists.", 409)
    return lab


@router.get("", response_model=Page)
def list_labs(
    user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE),
) -> Page:
    base = select(Lab).where(Lab.is_active.is_(True))
    if user.role != Role.ADMIN:
        base = base.join(LabMembership, LabMembership.lab_id == Lab.id).where(
            LabMembership.user_id == user.id
        )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    pages = max(math.ceil(total / page_size), 1)
    page = min(page, pages)
    labs = list(
        db.scalars(base.order_by(Lab.name).offset((page - 1) * page_size).limit(page_size))
    )
    return Page(
        items=[
            LabOut.model_validate(lab).model_dump(mode="json") for lab in labs
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{lab_id}", response_model=LabOut)
def get_lab(lab_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)) -> Lab:
    return get_visible_lab(db, user, lab_id)


@router.post("/{lab_id}/members", response_model=MemberOut, status_code=201)
def add_member(
    lab_id: uuid.UUID,
    payload: MemberIn,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> MemberOut:
    lab = require_lab_manager(db, user, lab_id)
    member = db.get(User, payload.user_id)
    if member is None or not member.is_active:
        raise ApiError("USER_NOT_FOUND", "The requested user was not found.", 404)
    existing = db.get(LabMembership, (payload.user_id, lab.id))
    if existing is not None:
        existing.role = payload.role
        db.flush()
        return MemberOut(
            user_id=member.id, email=member.email, display_name=member.display_name,
            role=existing.role,
        )
    db.add(LabMembership(user_id=member.id, lab_id=lab.id, role=payload.role))
    try:
        db.flush()
    except IntegrityError:
        # Lost a concurrent-insert race for the same membership: the row
        # now exists, so fall back to updating it instead of failing.
        db.rollback()
        existing = db.get(LabMembership, (payload.user_id, lab.id))
        if existing is None:
            raise
        existing.role = payload.role
        db.flush()
        return MemberOut(
            user_id=member.id, email=member.email, display_name=member.display_name,
            role=existing.role,
        )
    return MemberOut(
        user_id=member.id, email=member.email, display_name=member.display_name,
        role=payload.role,
    )


@router.delete("/{lab_id}/members/{user_id}", status_code=204)
def remove_member(
    lab_id: uuid.UUID,
    user_id: uuid.UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    lab = require_lab_manager(db, user, lab_id)
    existing = db.get(LabMembership, (user_id, lab.id))
    if existing is None:
        raise lab_not_found()
    db.delete(existing)
    db.flush()
