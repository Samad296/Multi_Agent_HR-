from contextlib import contextmanager

from sqlalchemy import text

from app.api.deps import TenantContext
from app.db.session import SessionLocal


@contextmanager
def tenant_session(ctx: TenantContext):
    """One transaction scoped to the tenant (so RLS applies), committed once on success."""
    db = SessionLocal()
    try:
        db.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant_id)})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()



    