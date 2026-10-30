from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.deps import TenantContext, get_context
from app.api.routes import auth, chat, documents, leave, users
from app.core.limiter import limiter
from app.db.models import Base
from app.db.session import admin_engine
from app.services.leave_service import LeaveError

Base.metadata.create_all(admin_engine)  # temporary: replaced by Alembic later

app = FastAPI(title="HR Knowledge Agent")

# rate limiting: the limiter object is shared, and over-limit calls get a clean 429
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(leave.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.exception_handler(LeaveError)
def leave_error_handler(request: Request, exc: LeaveError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/me")
def me(ctx: TenantContext = Depends(get_context)):
    return {"tenant_id": str(ctx.tenant_id), "user_id": str(ctx.user_id), "role": ctx.role}


@app.get("/health")
def health():
    return {"status": "ok"}