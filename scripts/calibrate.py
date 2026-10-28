import uuid

from app.api.deps import TenantContext
from app.rag.ingest import ingest_text
from app.rag.retriever import retrieve

ANSWERABLE = [
    "How many days of annual leave do I get?",
    "Can I carry over unused leave?",
    "Do I need a doctor's note for sick leave?",
    "How many days can I work from home?",
    "What are the core hours for remote work?",
    "What are the working hours?",
    "How long is the probation period?",
    "How do I claim expenses?",
    "Is alcohol reimbursable?",
    "How much notice do I give if I resign?",
    "What happens to my unused leave when I resign?",
    "Is overtime paid?",
]
NOT_COVERED = [
    "What is the dress code?",
    "Do we get health insurance?",
    "What is the maternity leave policy?",
    "Can I bring my dog to the office?",
    "What is the CEO's salary?",
    "Who won the cricket match?",
    "Recipe for biryani",
]

t = uuid.uuid4()
admin = TenantContext(t, uuid.uuid4(), "hr_admin")
ingest_text(admin, "policy.md", open("sample_policy.md", encoding="utf-8").read())

def top(q):
    hits = retrieve(admin, q, min_score=0.0)
    return hits[0]["score"] if hits else 0.0

scored = [(q, top(q), True) for q in ANSWERABLE] + [(q, top(q), False) for q in NOT_COVERED]

print("\nAnswerable questions:")
for q, s, _ in sorted((x for x in scored if x[2]), key=lambda x: x[1]):
    print(f"  {s:.2f}  {q}")
print("\nNot covered:")
for q, s, _ in sorted((x for x in scored if not x[2]), key=lambda x: -x[1]):
    print(f"  {s:.2f}  {q}")

print("\nthreshold | wrongly refused | wrongly answered")
for th in (0.30, 0.35, 0.40, 0.45, 0.50):
    refused = sum(1 for _, s, a in scored if a and s < th)
    answered = sum(1 for _, s, a in scored if not a and s >= th)
    print(f"  {th:.2f}    | {refused:2d} / {len(ANSWERABLE)}        | {answered:2d} / {len(NOT_COVERED)}")