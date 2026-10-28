import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.api.deps import TenantContext
from app.db.models import LeaveBalance, LeaveRequest, LeaveType
from app.services import audit_service

APPROVER_ROLES = {"manager", "hr_admin"}
ACTIVE_STATUSES = ("pending", "approved")


class LeaveError(Exception):
    status_code = 400


class NotFound(LeaveError):
    status_code = 404


class Forbidden(LeaveError):
    status_code = 403


class Conflict(LeaveError):
    status_code = 409


def working_days(start: date, end: date) -> int:
    """Mon-Fri days between start and end, inclusive."""
    days, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def _get_balance(db, user_id, leave_type_id) -> LeaveBalance:
    bal = db.scalar(
        select(LeaveBalance)
        .where(LeaveBalance.user_id == user_id, LeaveBalance.leave_type_id == leave_type_id)
        .with_for_update()  # lock the row so two requests can't both spend it
    )
    if not bal:
        raise NotFound("No leave balance for this leave type")
    return bal


def get_balances(db, ctx: TenantContext) -> list[dict]:
    rows = db.execute(
        select(LeaveType.name, LeaveBalance.remaining_days)
        .join(LeaveType, LeaveType.id == LeaveBalance.leave_type_id)
        .where(LeaveBalance.user_id == ctx.user_id)
    ).all()
    return [{"leave_type": n, "remaining_days": d} for n, d in rows]


def list_requests(db, ctx: TenantContext) -> list[LeaveRequest]:
    q = select(LeaveRequest).order_by(LeaveRequest.created_at.desc())
    if ctx.role not in APPROVER_ROLES:
        q = q.where(LeaveRequest.user_id == ctx.user_id)
    return list(db.scalars(q))


def _validate_submit(db, ctx: TenantContext, leave_type_id, start: date, end: date):
    if end < start:
        raise LeaveError("End date is before start date")
    if start < date.today():
        raise LeaveError("Start date is in the past")
    days = working_days(start, end)
    if days == 0:
        raise LeaveError("Selected dates contain no working days")

    overlap = db.scalar(
        select(LeaveRequest.id).where(
            LeaveRequest.user_id == ctx.user_id,
            LeaveRequest.status.in_(ACTIVE_STATUSES),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
    )
    if overlap:
        raise Conflict("You already have leave overlapping these dates")

    bal = _get_balance(db, ctx.user_id, leave_type_id)
    if bal.remaining_days < days:
        raise Conflict(f"Insufficient balance: {bal.remaining_days} days left, {days} requested")
    return days, bal


def preview_submit(db, ctx: TenantContext, leave_type_id, start: date, end: date) -> dict:
    days, bal = _validate_submit(db, ctx, leave_type_id, start, end)
    return {"days": days, "remaining_after": bal.remaining_days - days}


def submit_request(db, ctx: TenantContext, leave_type_id: uuid.UUID,
                   start: date, end: date, reason: str | None = None) -> LeaveRequest:
    days, bal = _validate_submit(db, ctx, leave_type_id, start, end)
    bal.remaining_days -= days
    req = LeaveRequest(
        tenant_id=ctx.tenant_id, user_id=ctx.user_id, leave_type_id=leave_type_id,
        start_date=start, end_date=end, reason=reason, status="pending",
    )
    db.add(req)
    db.flush()
    audit_service.log(db, ctx, "leave.submit", {"request_id": str(req.id), "days": days})
    return req


def _get_request(db, request_id: uuid.UUID) -> LeaveRequest:
    req = db.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update())
    if not req:  # RLS hides other tenants' rows, so they look like "not found"
        raise NotFound("Leave request not found")
    return req


def _refund(db, req: LeaveRequest) -> None:
    bal = _get_balance(db, req.user_id, req.leave_type_id)
    bal.remaining_days += working_days(req.start_date, req.end_date)


def decide_request(db, ctx: TenantContext, request_id: uuid.UUID, approve: bool) -> LeaveRequest:
    if ctx.role not in APPROVER_ROLES:
        raise Forbidden("Only managers or HR admins can decide leave requests")
    req = _get_request(db, request_id)
    if req.user_id == ctx.user_id:
        raise Forbidden("You cannot decide your own leave request")
    if req.status != "pending":
        raise Conflict(f"Request is already {req.status}")

    req.status = "approved" if approve else "rejected"
    if not approve:
        _refund(db, req)
    audit_service.log(db, ctx, f"leave.{req.status}", {"request_id": str(req.id)})
    return req


def cancel_request(db, ctx: TenantContext, request_id: uuid.UUID) -> LeaveRequest:
    req = _get_request(db, request_id)
    if req.user_id != ctx.user_id:
        raise Forbidden("You can only cancel your own requests")
    if req.status not in ACTIVE_STATUSES:
        raise Conflict(f"Request is already {req.status}")
    if req.status == "approved" and req.start_date <= date.today():
        raise Conflict("Leave that has already started cannot be cancelled")

    req.status = "cancelled"
    _refund(db, req)
    audit_service.log(db, ctx, "leave.cancel", {"request_id": str(req.id)})
    return req


def list_types(db) -> list[LeaveType]:
    return list(db.scalars(select(LeaveType).order_by(LeaveType.name)))