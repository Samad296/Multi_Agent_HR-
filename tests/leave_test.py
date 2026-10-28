import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import TenantContext
from app.db.models import LeaveBalance, LeaveType, Tenant, User
from app.db.session import SessionLocal, admin_engine
from app.services import leave_service as svc


def run(ctx, fn):
    """One request = one transaction, scoped to the tenant, committed once."""
    db = SessionLocal()
    try:
        db.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant_id)})
        result = fn(db)
        db.commit()
        return result
    finally:
        db.close()


def next_monday(weeks_ahead=1):
    d = date.today() + timedelta(weeks=weeks_ahead)
    return d - timedelta(days=d.weekday())


@pytest.fixture
def org():
    with Session(admin_engine) as db:
        t = Tenant(name=f"LeaveTest {uuid.uuid4().hex[:8]}")
        db.add(t)
        db.flush()
        emp = User(tenant_id=t.id, email=f"{uuid.uuid4().hex[:8]}@lt.test", password_hash="x", role="employee")
        mgr = User(tenant_id=t.id, email=f"{uuid.uuid4().hex[:8]}@lt.test", password_hash="x", role="manager")
        db.add_all([emp, mgr])
        db.flush()
        ids = (t.id, emp.id, mgr.id)
        db.commit()

    emp_ctx = TenantContext(ids[0], ids[1], "employee")
    mgr_ctx = TenantContext(ids[0], ids[2], "manager")

    def setup(db):
        lt = LeaveType(tenant_id=emp_ctx.tenant_id, name="Annual", days_per_year=10)
        db.add(lt)
        db.flush()
        db.add(LeaveBalance(tenant_id=emp_ctx.tenant_id, user_id=emp_ctx.user_id,
                            leave_type_id=lt.id, remaining_days=10))
        return lt.id

    return emp_ctx, mgr_ctx, run(emp_ctx, setup)


def balance(ctx):
    return run(ctx, lambda db: db.scalar(select(LeaveBalance.remaining_days)))


def test_working_days_skips_weekends():
    mon = next_monday()
    assert svc.working_days(mon, mon + timedelta(days=6)) == 5          # Mon..Sun
    assert svc.working_days(mon + timedelta(days=4), mon + timedelta(days=7)) == 2  # Fri..Mon


def test_submit_deducts_balance(org):
    emp, _, lt = org
    mon = next_monday()
    run(emp, lambda db: svc.submit_request(db, emp, lt, mon, mon + timedelta(days=2)))
    assert balance(emp) == 7


def test_insufficient_balance_rejected(org):
    emp, _, lt = org
    mon = next_monday()
    with pytest.raises(svc.Conflict):  # 11 working days vs 10 available
        run(emp, lambda db: svc.submit_request(db, emp, lt, mon, mon + timedelta(days=14)))
    assert balance(emp) == 10


def test_overlap_rejected(org):
    emp, _, lt = org
    mon = next_monday()
    run(emp, lambda db: svc.submit_request(db, emp, lt, mon, mon + timedelta(days=2)))
    with pytest.raises(svc.Conflict):
        run(emp, lambda db: svc.submit_request(db, emp, lt, mon + timedelta(days=1), mon + timedelta(days=3)))


def test_cancel_refunds(org):
    emp, _, lt = org
    mon = next_monday()
    req = run(emp, lambda db: svc.submit_request(db, emp, lt, mon, mon + timedelta(days=2)))
    run(emp, lambda db: svc.cancel_request(db, emp, req.id))
    assert balance(emp) == 10


def test_employee_cannot_approve(org):
    emp, _, lt = org
    mon = next_monday()
    req = run(emp, lambda db: svc.submit_request(db, emp, lt, mon, mon))
    with pytest.raises(svc.Forbidden):
        run(emp, lambda db: svc.decide_request(db, emp, req.id, approve=True))


def test_manager_approves_and_reject_refunds(org):
    emp, mgr, lt = org
    mon = next_monday()
    r1 = run(emp, lambda db: svc.submit_request(db, emp, lt, mon, mon))
    r2 = run(emp, lambda db: svc.submit_request(db, emp, lt, mon + timedelta(days=1), mon + timedelta(days=1)))
    assert run(mgr, lambda db: svc.decide_request(db, mgr, r1.id, True)).status == "approved"
    run(mgr, lambda db: svc.decide_request(db, mgr, r2.id, False))
    assert balance(emp) == 9  # one approved day spent, rejected day refunded