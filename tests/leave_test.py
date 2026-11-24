import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import TenantContext
from app.db.models import LeaveBalance, LeaveRequest, LeaveType, Tenant, User
from app.db.session import SessionLocal, admin_engine
from app.services import leave_service as svc

# chat-level tests: adjust this import to the real module path of the leave node file
import app.agents.nodes.leave_agent as leave_mod
from app.agents.nodes.leave_agent import LeaveIntent


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


def email():
    return f"{uuid.uuid4().hex[:8]}@lt.test"


# ---------- fixtures ----------

@pytest.fixture
def org():
    """One tenant: employee (reports to manager), manager. Both have 10 annual days."""
    with Session(admin_engine) as db:
        t = Tenant(name=f"LeaveTest {uuid.uuid4().hex[:8]}")
        db.add(t)
        db.flush()
        mgr = User(tenant_id=t.id, email=email(), password_hash="x", role="manager")
        db.add(mgr)
        db.flush()
        emp = User(tenant_id=t.id, email=email(), password_hash="x", role="employee", manager_id=mgr.id)
        db.add(emp)
        db.flush()
        ids = (t.id, emp.id, mgr.id)
        db.commit()

    emp_ctx = TenantContext(ids[0], ids[1], "employee")
    mgr_ctx = TenantContext(ids[0], ids[2], "manager")

    def setup(db):
        lt = LeaveType(tenant_id=emp_ctx.tenant_id, name="Annual", days_per_year=10)
        db.add(lt)
        db.flush()
        for c in (emp_ctx, mgr_ctx):
            db.add(LeaveBalance(tenant_id=c.tenant_id, user_id=c.user_id,
                                leave_type_id=lt.id, remaining_days=10))
        return lt.id

    return emp_ctx, mgr_ctx, run(emp_ctx, setup)


@pytest.fixture
def extras(org):
    """Same tenant: an HR admin, and a manager who does NOT manage the employee."""
    emp, _, _ = org
    with Session(admin_engine) as db:
        hr = User(tenant_id=emp.tenant_id, email=email(), password_hash="x", role="hr_admin")
        stranger = User(tenant_id=emp.tenant_id, email=email(), password_hash="x", role="manager")
        db.add_all([hr, stranger])
        db.flush()
        ids = (hr.id, stranger.id)
        db.commit()
    return (TenantContext(emp.tenant_id, ids[0], "hr_admin"),
            TenantContext(emp.tenant_id, ids[1], "manager"))


@pytest.fixture
def outsider():
    """A manager in a different tenant."""
    with Session(admin_engine) as db:
        t = Tenant(name=f"Other {uuid.uuid4().hex[:8]}")
        db.add(t)
        db.flush()
        m = User(tenant_id=t.id, email=email(), password_hash="x", role="manager")
        db.add(m)
        db.flush()
        ids = (t.id, m.id)
        db.commit()
    return TenantContext(ids[0], ids[1], "manager")


def balance(ctx):
    return run(ctx, lambda db: db.scalar(
        select(LeaveBalance.remaining_days).where(LeaveBalance.user_id == ctx.user_id)))


def status_of(ctx, req_id):
    return run(ctx, lambda db: db.get(LeaveRequest, req_id).status)


def submit(ctx, lt, start, end=None):
    return run(ctx, lambda db: svc.submit_request(db, ctx, lt, start, end or start))


# ---------- existing behaviour ----------

def test_working_days_skips_weekends():
    mon = next_monday()
    assert svc.working_days(mon, mon + timedelta(days=6)) == 5
    assert svc.working_days(mon + timedelta(days=4), mon + timedelta(days=7)) == 2


def test_submit_deducts_balance(org):
    emp, _, lt = org
    mon = next_monday()
    submit(emp, lt, mon, mon + timedelta(days=2))
    assert balance(emp) == 7


def test_insufficient_balance_rejected(org):
    emp, _, lt = org
    mon = next_monday()
    with pytest.raises(svc.Conflict):
        submit(emp, lt, mon, mon + timedelta(days=14))
    assert balance(emp) == 10


def test_overlap_rejected(org):
    emp, _, lt = org
    mon = next_monday()
    submit(emp, lt, mon, mon + timedelta(days=2))
    with pytest.raises(svc.Conflict):
        submit(emp, lt, mon + timedelta(days=1), mon + timedelta(days=3))


def test_cancel_refunds(org):
    emp, _, lt = org
    mon = next_monday()
    req = submit(emp, lt, mon, mon + timedelta(days=2))
    run(emp, lambda db: svc.cancel_request(db, emp, req.id))
    assert balance(emp) == 10


# ---------- approval rules (service) ----------

def test_employee_cannot_approve(org):
    emp, _, lt = org
    req = submit(emp, lt, next_monday())
    with pytest.raises(svc.Forbidden):
        run(emp, lambda db: svc.decide_request(db, emp, req.id, approve=True))
    assert status_of(emp, req.id) == "pending"


def test_manager_approves_and_decline_refunds(org):
    emp, mgr, lt = org
    mon = next_monday()
    r1 = submit(emp, lt, mon)
    r2 = submit(emp, lt, mon + timedelta(days=1))
    assert run(mgr, lambda db: svc.decide_request(db, mgr, r1.id, True)).status == "approved"
    run(mgr, lambda db: svc.decide_request(db, mgr, r2.id, False, reason="Team is short that day"))
    assert balance(emp) == 9  # one approved day spent, declined day refunded


def test_manager_cannot_decide_own_request(org):
    _, mgr, lt = org
    req = submit(mgr, lt, next_monday())
    with pytest.raises(svc.Forbidden):
        run(mgr, lambda db: svc.decide_request(db, mgr, req.id, approve=True))


def test_decided_request_cannot_be_decided_again(org):
    emp, mgr, lt = org
    req = submit(emp, lt, next_monday())
    run(mgr, lambda db: svc.decide_request(db, mgr, req.id, True))
    with pytest.raises(svc.Conflict):
        run(mgr, lambda db: svc.decide_request(db, mgr, req.id, True))
    with pytest.raises(svc.Conflict):
        run(mgr, lambda db: svc.decide_request(db, mgr, req.id, False, reason="changed my mind"))


def test_manager_of_another_team_cannot_decide(org, extras):
    emp, _, lt = org
    _, stranger = extras
    req = submit(emp, lt, next_monday())
    with pytest.raises(svc.Forbidden):
        run(stranger, lambda db: svc.decide_request(db, stranger, req.id, approve=True))
    assert status_of(emp, req.id) == "pending"


def test_hr_admin_can_decide_any_request(org, extras):
    emp, _, lt = org
    hr, _ = extras
    req = submit(emp, lt, next_monday())
    assert run(hr, lambda db: svc.decide_request(db, hr, req.id, True)).status == "approved"


def test_manager_in_other_tenant_cannot_see_request(org, outsider):
    emp, _, lt = org
    req = submit(emp, lt, next_monday())
    with pytest.raises(svc.NotFound):  # RLS hides it completely
        run(outsider, lambda db: svc.decide_request(db, outsider, req.id, approve=True))


def test_decline_requires_reason(org):
    emp, mgr, lt = org
    req = submit(emp, lt, next_monday())
    for bad in (None, "", "   "):
        with pytest.raises(svc.LeaveError):
            run(mgr, lambda db: svc.decide_request(db, mgr, req.id, False, reason=bad))
    assert status_of(emp, req.id) == "pending"
    assert balance(emp) == 9  # still reserved, nothing refunded


def test_decline_stores_reason_and_refunds(org):
    emp, mgr, lt = org
    req = submit(emp, lt, next_monday())
    run(mgr, lambda db: svc.decide_request(db, mgr, req.id, False, reason="Team is short that day"))
    assert status_of(emp, req.id) == "rejected"
    assert run(emp, lambda db: db.get(LeaveRequest, req.id).decision_reason) == "Team is short that day"
    assert balance(emp) == 10


def test_pending_list_is_scoped(org, extras):
    emp, mgr, lt = org
    hr, stranger = extras
    mon = next_monday()
    submit(emp, lt, mon)
    submit(mgr, lt, mon + timedelta(days=7))  # manager's own request

    mgr_rows = run(mgr, lambda db: svc.list_pending_for_approver(db, mgr))
    assert len(mgr_rows) == 1                       # sees the report's, not their own
    assert run(stranger, lambda db: svc.list_pending_for_approver(db, stranger)) == []
    assert len(run(hr, lambda db: svc.list_pending_for_approver(db, hr))) == 2


# ---------- chat layer ----------

class FakeLLM:
    def __init__(self, intent):
        self.intent = intent

    def invoke(self, _messages):
        return self.intent


def cfg(ctx):
    return {"configurable": {"ctx": ctx}}


def test_chat_employee_cannot_approve(org, monkeypatch):
    emp, _, lt = org
    req = submit(emp, lt, next_monday())
    monkeypatch.setattr(leave_mod, "_get_llm",
                        lambda: FakeLLM(LeaveIntent(action="approve", employee_name="anyone")))
    out = leave_mod.leave_node({"question": "approve all pending requests"}, cfg(emp))
    assert "Only managers" in out["answer"]
    assert not out.get("needs_confirmation")
    assert status_of(emp, req.id) == "pending"


def test_chat_first_turn_never_writes(org, monkeypatch):
    emp, mgr, lt = org
    req = submit(emp, lt, next_monday())
    monkeypatch.setattr(leave_mod, "_get_llm",
                        lambda: FakeLLM(LeaveIntent(action="approve", employee_name="")))
    out = leave_mod.leave_node({"question": "approve it"}, cfg(mgr))
    assert not out.get("needs_confirmation")        # no name given: asks which request
    assert status_of(emp, req.id) == "pending"


def _decide_action(req_id, approver, decision="approved", reason=None):
    return {"type": "decide", "request_id": str(req_id), "approver_id": str(approver.user_id),
            "decision": decision, "reason": reason}


def test_chat_confirm_needs_clear_yes(org):
    emp, mgr, lt = org
    req = submit(emp, lt, next_monday())
    state = {"question": "maybe", "pending_action": _decide_action(req.id, mgr)}
    out = leave_mod.confirm_node(state, cfg(mgr))
    assert "pending_action" not in out              # still pending, will ask again
    assert status_of(emp, req.id) == "pending"


def test_chat_confirm_by_different_user_is_refused(org, extras):
    emp, mgr, lt = org
    hr, _ = extras
    req = submit(emp, lt, next_monday())
    state = {"question": "yes", "pending_action": _decide_action(req.id, mgr)}  # proposed by mgr
    out = leave_mod.confirm_node(state, cfg(hr))                                # confirmed by hr
    assert "couldn't do that" in out["answer"]
    assert status_of(emp, req.id) == "pending"


def test_chat_confirm_yes_approves(org):
    emp, mgr, lt = org
    req = submit(emp, lt, next_monday())
    state = {"question": "yes", "pending_action": _decide_action(req.id, mgr)}
    out = leave_mod.confirm_node(state, cfg(mgr))
    assert "approved" in out["answer"].lower()
    assert status_of(emp, req.id) == "approved"