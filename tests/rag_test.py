import uuid

import pytest
from qdrant_client import models as qm

from app.api.deps import TenantContext
from app.core.config import settings
from app.rag.clients import get_qdrant
from app.rag.ingest import ingest_text
from app.rag.retriever import retrieve

A_DOC = "# Sick Leave\nEvery Acme employee receives twelve days of paid sick leave per year."
B_DOC = "# Sick Leave\nEvery Beta employee receives five days of paid sick leave per year."
SECRET = "# Salary Bands\nAcme senior engineers are paid in band seven, confidential to HR."


def ctx(tenant, role="employee"):
    return TenantContext(tenant, uuid.uuid4(), role)


@pytest.fixture(scope="module")
def tenants():
    a, b = uuid.uuid4(), uuid.uuid4()
    ingest_text(ctx(a, "hr_admin"), "sick.md", A_DOC)
    ingest_text(ctx(a, "hr_admin"), "bands.md", SECRET, access_level="hr_admin")
    ingest_text(ctx(b, "hr_admin"), "sick.md", B_DOC)
    yield a, b
    for t in (a, b):
        get_qdrant().delete(settings.QDRANT_COLLECTION, points_selector=qm.FilterSelector(
            filter=qm.Filter(must=[qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=str(t)))])))


def test_tenant_sees_only_own_chunks(tenants):
    a, b = tenants
    hits = retrieve(ctx(a), "How many sick days do I get?", min_score=0.0)
    assert hits and all(h["tenant_id"] == str(a) for h in hits)
    assert not any("Beta" in h["text"] for h in hits)


def test_other_tenants_answer_never_leaks(tenants):
    a, b = tenants
    hits = retrieve(ctx(b), "How many sick days do I get?", min_score=0.0)
    assert hits and all("Acme" not in h["text"] for h in hits)


def test_employee_cannot_retrieve_hr_only_docs(tenants):
    a, _ = tenants
    hits = retrieve(ctx(a, "employee"), "salary band for senior engineers", min_score=0.0)
    assert not any("band seven" in h["text"] for h in hits)
    admin_hits = retrieve(ctx(a, "hr_admin"), "salary band for senior engineers", min_score=0.0)
    assert any("band seven" in h["text"] for h in admin_hits)