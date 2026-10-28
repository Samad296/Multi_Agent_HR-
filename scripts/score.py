import uuid
from pathlib import Path

from app.api.deps import TenantContext
from app.rag.ingest import ingest_text
from app.rag.retriever import retrieve

BASE = Path(__file__).resolve().parents[1]


def tenant(file, name):
    ctx = TenantContext(uuid.uuid4(), uuid.uuid4(), "hr_admin")
    ingest_text(ctx, name, (BASE / file).read_text(encoding="utf-8"))
    return ctx


acme, nw = tenant("sample_policy.md", "policy.md"), tenant("northwind_policy.md", "northwind.md")

CASES = [   # (tenant, question, should it be answered?)
    (acme, "Is alcohol reimbursable?", True),
    (acme, "Do I need a doctor's note for sick leave?", True),
    (acme, "How many days of annual leave do I get?", True),
    (acme, "What is the maternity leave policy?", False),
    (acme, "How many days of paternity leave do I get?", False),
    (acme, "What is the travel budget per trip?", False),
    (acme, "Is the probation period ever extended?", False),
    (nw, "What is the annual learning budget?", True),
    (nw, "How much notice must I give when resigning?", True),
    (nw, "Within how many days must I submit expense claims?", False),
    (nw, "What is the claim deadline for travel expenses?", False),
    (nw, "How many sick days carry over to next year?", False),
    (nw, "What is the overtime rate on public holidays?", False),
    (nw, "Is there a gym membership?", False),
]

rows = []
for ctx, q, answerable in CASES:
    hits = retrieve(ctx, q, k=1, min_score=0.0)
    rows.append((hits[0]["score"] if hits else 0.0, answerable, q))

for score, answerable, q in sorted(rows, reverse=True):
    print(f"{score:.2f}  {'ANSWER' if answerable else 'refuse'}  {q}")