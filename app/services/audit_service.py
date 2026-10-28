from app.api.deps import TenantContext
from app.db.models import AuditLog
def log(db, ctx: TenantContext, action: str, detail: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action=action,
        detail=detail or {},
    ))