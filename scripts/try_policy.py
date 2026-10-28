import uuid

from app.agents.graph import build_graph
from app.api.deps import TenantContext
from app.rag.ingest import ingest_text

t = uuid.uuid4()
admin = TenantContext(t, uuid.uuid4(), "hr_admin")
ingest_text(admin, "policy.md", open("sample_policy.md", encoding="utf-8").read())

other = TenantContext(uuid.uuid4(), uuid.uuid4(), "employee")   # a different company, no documents
graph = build_graph()

for who, ctx in (("acme", admin), ("other company", other)):
    print(f"\n=== {who} ===")
    for q in ["How many days of annual leave do I get?",
              "How much notice do I give if I resign?",
              "What is the maternity leave policy?",
              "What is the dress code?"]:
        out = graph.invoke({"question": q}, config={"configurable": {"ctx": ctx}})
        print(f"Q: {q}\nA: {out['answer']}\n   sources: {out.get('citations')}\n")