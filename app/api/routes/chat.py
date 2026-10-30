import logging
import time
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agents.graph import build_graph
from app.api.deps import TenantContext, get_context
from app.core.config import settings
from app.core.limiter import limiter, user_key
from app.db.models import AuditLog
from app.db.tenant import tenant_session
from app.services import audit_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@lru_cache
def get_graph():
    return build_graph()    # compiled once, reused for every request


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatOut(BaseModel):
    answer: str
    citations: list[str] = []
    needs_confirmation: bool = False


def _used_today(ctx: TenantContext) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with tenant_session(ctx) as db:        # row-level security scopes the count to this company
        return db.scalar(
            select(func.count()).select_from(AuditLog)
            .where(AuditLog.action == "chat", AuditLog.created_at >= start)
        ) or 0


@router.post("", response_model=ChatOut)
@limiter.limit("20/minute", key_func=user_key)
def chat(request: Request, body: ChatIn, ctx: TenantContext = Depends(get_context)):
    if _used_today(ctx) >= settings.CHAT_DAILY_LIMIT:
        raise HTTPException(429, "Your company has reached today's assistant limit. Please try again tomorrow.")

    cfg = {"configurable": {"ctx": ctx, "thread_id": f"{ctx.tenant_id}:{ctx.user_id}"}}
    t = time.time()
    out = get_graph().invoke({"question": body.message}, config=cfg)
    ms = int((time.time() - t) * 1000)

    try:    # usage record: intent and timing only, never the message text
        with tenant_session(ctx) as db:
            audit_service.log(db, ctx, "chat", {
                "intent": out.get("intent"),
                "latency_ms": ms,
                "cited": len(out.get("citations", [])),
            })
    except Exception as e:
        log.warning("usage logging failed: %r", e)    # logging must never break the answer

    return ChatOut(
        answer=out.get("answer", ""),
        citations=out.get("citations", []),
        needs_confirmation=bool(out.get("needs_confirmation", False)),
    )