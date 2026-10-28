import uuid

from app.api.deps import TenantContext
from app.rag.ingest import ingest_text
from app.rag.retriever import retrieve

t = uuid.uuid4()
admin = TenantContext(t, uuid.uuid4(), "hr_admin")
ingest_text(admin, "policy.md", open("sample_policy.md", encoding="utf-8").read())

for q in ["How many sick days do I get?", "Can I work from home?",
          "What is the dress code?", "Who won the cricket match?", "Recipe for biryani"]:
    hits = retrieve(admin, q, min_score=0.0)
    print(f"{q!r:35} top scores:", [round(h["score"], 2) for h in hits[:3]])