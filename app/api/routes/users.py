from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantContext, get_db, require_role
from app.core.security import hash_password
from app.db.models import LeaveBalance, LeaveType, User
from app.services import audit_service

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["employee", "manager", "hr_admin"] = "employee"


@router.post("", status_code=201)
def create_user(
    body: UserCreate,
    ctx: TenantContext = Depends(require_role("hr_admin")),
    db=Depends(get_db),
):
    user = User(
        tenant_id=ctx.tenant_id,  # always the admin's own company
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(409, "Email already registered")

    for lt in db.scalars(select(LeaveType)):
        db.add(LeaveBalance(tenant_id=ctx.tenant_id, user_id=user.id,
                            leave_type_id=lt.id, remaining_days=lt.days_per_year))

    audit_service.log(db, ctx, "user.create", {"user_id": str(user.id), "role": body.role})
    db.commit()
    return {"id": str(user.id), "email": user.email, "role": user.role}