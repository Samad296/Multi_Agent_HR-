import logging
import sys

from sqlalchemy import select

from app.agents.graph import build_graph
from app.api.deps import TenantContext
from app.db.models import User
from app.db.session import SessionLocal

logging.basicConfig(level=logging.WARNING)

with SessionLocal() as db:
    u = db.scalar(select(User).where(User.email == sys.argv[1].lower()))
    if not u:
        sys.exit("no such user")
    ctx = TenantContext(u.tenant_id, u.id, u.role)

graph = build_graph()
cfg = {"configurable": {"ctx": ctx, "thread_id": f"{ctx.tenant_id}:{ctx.user_id}"}}

for msg in [
    "What's my leave balance?",
    "I need next Monday and Tuesday off",
    "yes",
    "show my requests",
    "What's my leave balance?",
    "I need Thursday and Friday of next week off",
    "no",
    "Cancel my leave request",
    "yes",
    "What's my leave balance?",
]:
    out = graph.invoke({"question": msg}, config=cfg)
    print(f"> {msg}\n{out['answer']}\n")