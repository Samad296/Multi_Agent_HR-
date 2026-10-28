import sys

from sqlalchemy import select, text

from app.db.models import LeaveBalance, LeaveType, User
from app.db.session import SessionLocal

email = sys.argv[1].lower()
db = SessionLocal()
user = db.scalar(select(User).where(User.email == email))
if not user:
    sys.exit(f"No user with email {email}")

db.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(user.tenant_id)})
lt = db.scalar(select(LeaveType)) or LeaveType(tenant_id=user.tenant_id, name="Annual", days_per_year=20)
db.add(lt)
db.flush()

for u in db.scalars(select(User).where(User.tenant_id == user.tenant_id)):
    has = db.scalar(select(LeaveBalance.id).where(
        LeaveBalance.user_id == u.id, LeaveBalance.leave_type_id == lt.id))
    if not has:
        db.add(LeaveBalance(tenant_id=user.tenant_id, user_id=u.id,
                            leave_type_id=lt.id, remaining_days=20))
db.commit()
print("seeded Annual leave (20 days) for every user in that company")