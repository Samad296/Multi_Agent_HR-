import uuid
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import func, or_, select

from app.db.models import LeaveBalance, LeaveRequest, LeaveType, User
from app.services import audit_service

APPROVER_ROLES = {"manager", "hr_admin"}
ACTIVE_STATUSES = ("pending", "approved")


# ---------- errors (messages are written by us and safe to show to users) ----------

class LeaveError(Exception):
    pass


class NotFound(LeaveError):
    pass


class Forbidden(LeaveError):
    pass


class Conflict(LeaveError):
    pass


# ---------- helpers ----------

def working_days(start: date, end: date) -> int:
    """Number of Mon-Fri days between start and end, inclusive."""
    if end < start:
        return 0
    days = (end - start).days + 1
    return sum(1 for i in range(days) if (start + timedelta(days=i)).weekday() < 5)


def _get_request(db, request_id, for_update: bool = False) -> LeaveRequest:
    q = select(LeaveRequest).where(LeaveRequest.id == request_id)
    if for_update:
        q = q.with_for_update()          # two simultaneous decisions cannot both pass
    req = db.scalar(q)
    if req is None:                      # RLS also lands here for other tenants
        raise NotFound("Leave request not found")
    return req


def _get_balance(db, user_id, leave_type_id, for_update: bool = False) -> LeaveBalance:
    q = select(LeaveBalance).where(
        LeaveBalance.user_id == user_id, LeaveBalance.leave_type_id == leave_type_id
    )
    if for_update:
        q = q.with_for_update()
    bal = db.scalar(q)
    if bal is None:
        raise NotFound("No leave balance is set up for this leave type")
    return bal


def _refund(db, req: LeaveRequest) -> None:
    bal = _get_balance(db, req.user_id, req.leave_type_id, for_update=True)
    bal.remaining_days += working_days(req.start_date, req.end_date)


# ---------- reads ----------

def list_types(db) -> list[LeaveType]:
    return list(db.scalars(select(LeaveType).order_by(LeaveType.name)))


def get_balances(db, ctx) -> list[dict]:
    rows = db.execute(
        select(LeaveType.name, LeaveBalance.remaining_days, LeaveBalance.leave_type_id)
        .join(LeaveType, LeaveType.id == LeaveBalance.leave_type_id)
        .where(LeaveBalance.user_id == ctx.user_id)
        .order_by(LeaveType.name)
    )
    return [
        {"leave_type": name, "remaining_days": days, "leave_type_id": str(lt_id)}
        for name, days, lt_id in rows
    ]


def list_requests(db, ctx) -> list[LeaveRequest]:
    """Employees see their own; managers their own and their team's; HR admins everything."""
    q = select(LeaveRequest).order_by(LeaveRequest.start_date.desc())
    if ctx.role == "hr_admin":
        pass
    elif ctx.role == "manager":
        team = select(User.id).where(User.manager_id == ctx.user_id)
        q = q.where(or_(LeaveRequest.user_id == ctx.user_id, LeaveRequest.user_id.in_(team)))
    else:
        q = q.where(LeaveRequest.user_id == ctx.user_id)
    return list(db.scalars(q))


# ---------- employee actions ----------

def preview_submit(db, ctx, leave_type_id, start: date, end: date, lock: bool = False) -> dict:
    """Validate a request and return what would happen. Writes nothing."""
    if end < start:
        raise LeaveError("The end date is before the start date")
    days = working_days(start, end)
    if days == 0:
        raise LeaveError("Those dates contain no working days")

    bal = _get_balance(db, ctx.user_id, leave_type_id, for_update=lock)
    if days > bal.remaining_days:
        raise Conflict(f"Not enough balance: you need {days} days but have {bal.remaining_days}")

    overlap = db.scalar(
        select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.user_id == ctx.user_id,
            LeaveRequest.status.in_(ACTIVE_STATUSES),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
    )
    if overlap:
        raise Conflict("You already have a leave request overlapping those dates")

    return {"days": days, "remaining_after": bal.remaining_days - days}


def submit_request(db, ctx, leave_type_id, start: date, end: date, reason: str | None = None) -> LeaveRequest:
    preview_submit(db, ctx, leave_type_id, start, end, lock=True)   # re-checked under a row lock
    days = working_days(start, end)
    bal = _get_balance(db, ctx.user_id, leave_type_id, for_update=True)
    bal.remaining_days -= days                                      # days are reserved at submit

    req = LeaveRequest(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        leave_type_id=leave_type_id,
        start_date=start,
        end_date=end,
        status="pending",
        reason=reason,
    )
    db.add(req)
    db.flush()
    audit_service.log(db, ctx, "leave.submitted", {"request_id": str(req.id), "days": days})
    return req


def cancel_request(db, ctx, request_id) -> LeaveRequest:
    req = _get_request(db, request_id, for_update=True)
    if req.user_id != ctx.user_id:
        raise Forbidden("You can only cancel your own leave requests")
    if req.status not in ACTIVE_STATUSES:
        raise Conflict(f"Request is already {req.status}")
    req.status = "cancelled"
    _refund(db, req)
    audit_service.log(db, ctx, "leave.cancelled", {"request_id": str(req.id)})
    return req


# ---------- approver actions ----------

class PendingRow(NamedTuple):
    id: uuid.UUID
    employee_name: str
    start_date: date
    end_date: date
    reason: str | None


def list_pending_for_approver(db, ctx) -> list[PendingRow]:
    """Pending requests this approver may decide: never their own; managers see only their team."""
    name = func.coalesce(User.full_name, User.email)
    q = (
        select(LeaveRequest, name)
        .join(User, User.id == LeaveRequest.user_id)
        .where(LeaveRequest.status == "pending", LeaveRequest.user_id != ctx.user_id)
        .order_by(LeaveRequest.start_date)
    )
    if ctx.role != "hr_admin":
        q = q.where(User.manager_id == ctx.user_id)
    return [PendingRow(r.id, n, r.start_date, r.end_date, r.reason) for r, n in db.execute(q)]


def decide_request(
    db, ctx, request_id, approve: bool, reason: str | None = None, via: str = "api"
) -> LeaveRequest:
    if ctx.role not in APPROVER_ROLES:
        raise Forbidden("Only managers or HR admins can decide leave requests")
    req = _get_request(db, request_id, for_update=True)
    if req.user_id == ctx.user_id:
        raise Forbidden("You cannot decide your own leave request")
    if ctx.role != "hr_admin":
        owner_manager = db.scalar(select(User.manager_id).where(User.id == req.user_id))
        if owner_manager != ctx.user_id:
            raise Forbidden("You can only decide requests from your own team")
    if req.status != "pending":
        raise Conflict(f"Request is already {req.status}")
    if not approve and not (reason and reason.strip()):
        raise LeaveError("A reason is required when declining")

    req.status = "approved" if approve else "rejected"
    req.decision_reason = reason.strip() if reason else None
    req.decided_at = datetime.now(timezone.utc)
    if not approve:
        _refund(db, req)
    audit_service.log(db, ctx, f"leave.{req.status}", {"request_id": str(req.id), "via": via})
    return req