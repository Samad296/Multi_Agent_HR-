from qdrant_client import models as qm

from app.api.deps import TenantContext
from app.core.config import settings
from app.rag.clients import embed, get_qdrant


def _allowed_levels(role: str) -> list[str]:
    return ["all", "hr_admin"] if role == "hr_admin" else ["all"]


def retrieve(ctx: TenantContext, query: str, k: int = 5, min_score: float | None = None) -> list[dict]:
    """The ONLY place that queries Qdrant. Tenant and role filters are not optional."""
    flt = qm.Filter(must=[
        qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=str(ctx.tenant_id))),
        qm.FieldCondition(key="access_level", match=qm.MatchAny(any=_allowed_levels(ctx.role))),
    ])
    res = get_qdrant().query_points(
        settings.QDRANT_COLLECTION,
        query=embed([query])[0],
        query_filter=flt,
        limit=k,
        score_threshold=settings.RETRIEVAL_MIN_SCORE if min_score is None else min_score,
        with_payload=True,
    )
    return [
        {
            "text": p.payload["text"], "doc_name": p.payload["doc_name"],
            "section": p.payload["section"], "chunk_index": p.payload["chunk_index"],
            "tenant_id": p.payload["tenant_id"], "score": p.score,
        }
        for p in res.points
    ]