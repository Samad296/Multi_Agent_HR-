import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.models import LeaveRequest, LeaveType, Tenant, User
from app.db.session import SessionLocal, admin_engine
from sqlalchemy.orm import Session


def tenant_session(tenant_id: uuid.UUID) -> Session:
    """Session as the restricted app_user, scoped to one tenant."""
    db = SessionLocal()
    db.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    return db


@pytest.fixture(scope="module")
def two_tenants():
    ids = {}
    with Session(admin_engine) as db:  # owner bypasses nothing we rely on: setup only
        for name in ("IsoTest Acme", "IsoTest Beta"):
            t = Tenant(name=f"{name} {uuid.uuid4().hex[:6]}")
            db.add(t)
            db.flush()
            u = User(tenant_id=t.id, email=f"{uuid.uuid4().hex[:8]}@iso.test",
                     password_hash="x", role="employee")
            db.add(u)
            db.flush()
            ids[name] = (t.id, u.id)
        db.commit()
    return ids


def seed_leave(tenant_id, user_id):
    db = tenant_session(tenant_id)
    lt = LeaveType(tenant_id=tenant_id, name="Annual", days_per_year=20)
    db.add(lt)
    db.flush()
    db.add(LeaveRequest(tenant_id=tenant_id, user_id=user_id, leave_type_id=lt.id,
                        start_date=date(2026, 11, 1), end_date=date(2026, 11, 3)))
    db.commit()
    db.close()


def test_each_tenant_sees_only_own_rows(two_tenants):
    (a_t, a_u), (b_t, b_u) = two_tenants["IsoTest Acme"], two_tenants["IsoTest Beta"]
    seed_leave(a_t, a_u)
    seed_leave(b_t, b_u)

    db = tenant_session(a_t)
    rows = db.scalars(select(LeaveRequest)).all()
    assert rows and all(r.tenant_id == a_t for r in rows)
    db.close()


def test_no_tenant_context_returns_nothing(two_tenants):
    db = SessionLocal()  # no set_config -> fail closed
    assert db.scalars(select(LeaveRequest)).all() == []
    db.close()


def test_cannot_insert_into_other_tenant(two_tenants):
    (a_t, a_u), (b_t, _) = two_tenants["IsoTest Acme"], two_tenants["IsoTest Beta"]
    db = tenant_session(a_t)
    lt = db.scalars(select(LeaveType)).first()
    db.add(LeaveRequest(tenant_id=b_t, user_id=a_u, leave_type_id=lt.id,
                        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2)))
    with pytest.raises(DBAPIError):
        db.commit()
    db.rollback()
    db.close()