import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from app.core.security import decode_token
from app.db.session import SessionLocal

bearer = HTTPBearer()


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str


def get_context(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> TenantContext:
    try:
        claims = decode_token(creds.credentials)
        return TenantContext(
            tenant_id=uuid.UUID(claims["tid"]),
            user_id=uuid.UUID(claims["sub"]),
            role=claims["role"],
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_db(ctx: TenantContext = Depends(get_context)):
    with SessionLocal() as db:
        db.execute(
            text("select set_config('app.tenant_id', :t, true)"),
            {"t": str(ctx.tenant_id)},
        )
        yield db


def require_role(*roles: str):
    def check(ctx: TenantContext = Depends(get_context)) -> TenantContext:
        if ctx.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return ctx

    return check