from fastapi import FastAPI, Request
from app.api.routes import auth, leave, users, chat, documents
from app.api.deps import get_context, TenantContext
from fastapi import Depends
from app.db.models import Base
from app.db.session import admin_engine
from fastapi.responses import JSONResponse
from app.services.leave_service import LeaveError

Base.metadata.create_all(admin_engine)  # temporary: replaced by Alembic later

app = FastAPI(title="HR Knowledge Agent")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(leave.router)
app.include_router(chat.router)
app.include_router(documents.router)
@app.exception_handler(LeaveError)
def leave_error_handler(request: Request, exc: LeaveError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})
@app.get("/me")
def me(ctx: TenantContext = Depends(get_context)):
    return {"tenant_id": str(ctx.tenant_id), "user_id": str(ctx.user_id), "role": ctx.role}

@app.get("/health")
def health():
    return {"status": "ok"}