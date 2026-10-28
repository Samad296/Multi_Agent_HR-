from functools import lru_cache

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.graph import build_graph
from app.api.deps import TenantContext, get_context

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


@router.post("", response_model=ChatOut)
def chat(body: ChatIn, ctx: TenantContext = Depends(get_context)):
    cfg = {"configurable": {"ctx": ctx, "thread_id": f"{ctx.tenant_id}:{ctx.user_id}"}}
    out = get_graph().invoke({"question": body.message}, config=cfg)
    return ChatOut(
        answer=out.get("answer", ""),
        citations=out.get("citations", []),
        needs_confirmation=bool(out.get("needs_confirmation", False)),
    )