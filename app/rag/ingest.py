import re
import uuid

from qdrant_client import models as qm

from app.api.deps import TenantContext
from app.core.config import settings
from app.rag.clients import embed, ensure_collection, get_qdrant, qdrant_retry

CHUNK_WORDS = 120      # about 160 tokens, safely under MiniLM's 256 cap
OVERLAP_WORDS = 25
BATCH_SIZE = 32
HEADING = re.compile(r"^(#{1,6}\s+.+|\d+(\.\d+)*[.)]?\s+[A-Z].*)$")


# ---------------- chunking ----------------
def _looks_like_heading(line: str, nxt: str) -> bool:
    words = line.split()
    if HEADING.match(line) and len(words) <= 12 and not line.endswith("."):
        return True                                   # markdown or numbered heading
    return (                                          # plain heading from a PDF or Word file
        1 <= len(words) <= 8
        and line[0].isupper()
        and not line.endswith((".", ",", ";", ":", "?"))
        and len(nxt.split()) > len(words)             # followed by a longer body line
    )


def split_sections(text: str) -> list[tuple[str, str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sections, title, buf = [], "General", []
    for i, s in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if _looks_like_heading(s, nxt):
            if buf:
                sections.append((title, " ".join(buf)))
            title, buf = s.lstrip("# ").strip(), []
        else:
            buf.append(s)
    if buf:
        sections.append((title, " ".join(buf)))
    return sections


def window(words: list[str]):
    step = CHUNK_WORDS - OVERLAP_WORDS
    for i in range(0, len(words), step):
        yield words[i : i + CHUNK_WORDS]
        if i + CHUNK_WORDS >= len(words):
            break


def make_chunks(text: str) -> list[dict]:
    chunks = []
    for title, body in split_sections(text):
        for w in window(body.split()):
            chunks.append({"section": title, "text": f"{title}: {' '.join(w)}"})
    return chunks


# ---------------- store helpers ----------------
def _tenant_filter(ctx: TenantContext, extra: list | None = None) -> qm.Filter:
    return qm.Filter(must=[
        qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=str(ctx.tenant_id))),
        *(extra or []),
    ])


def _doc_filter(ctx: TenantContext, doc_id: str) -> qm.Filter:
    return _tenant_filter(ctx, [qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])


# ---------------- operations ----------------
def ingest_text(ctx: TenantContext, doc_name: str, text: str, access_level: str = "all") -> int:
    """Caller (the route) must already have required the hr_admin role."""
    if access_level not in ("all", "hr_admin"):
        raise ValueError("access_level must be 'all' or 'hr_admin'")
    ensure_collection()
    client = get_qdrant()
    tenant = str(ctx.tenant_id)
    doc_id = str(uuid.uuid5(ctx.tenant_id, doc_name))   # same name re-ingests in place

    # chunk and embed first, so a bad file cannot wipe the existing version of the document
    chunks = make_chunks(text)
    if not chunks:
        return 0
    vectors = embed([c["text"] for c in chunks])

    qdrant_retry(lambda: client.delete(
        settings.QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(filter=_doc_filter(ctx, doc_id)),
    ))

    points = [
        qm.PointStruct(
            id=str(uuid.uuid5(uuid.UUID(doc_id), str(i))),
            vector=vec,
            payload={
                "tenant_id": tenant, "doc_id": doc_id, "doc_name": doc_name,
                "section": c["section"], "chunk_index": i, "text": c["text"],
                "access_level": access_level, "embed_model": settings.EMBED_MODEL,
            },
        )
        for i, (c, vec) in enumerate(zip(chunks, vectors))
    ]
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        qdrant_retry(lambda b=batch: client.upsert(settings.QDRANT_COLLECTION, points=b))
    return len(chunks)


def list_documents(ctx: TenantContext) -> list[dict]:
    ensure_collection()
    client, flt = get_qdrant(), _tenant_filter(ctx)
    docs: dict[str, dict] = {}
    offset = None
    while True:
        points, offset = qdrant_retry(lambda o=offset: client.scroll(
            settings.QDRANT_COLLECTION, scroll_filter=flt, limit=256, offset=o,
            with_payload=True, with_vectors=False))
        for p in points:
            d = docs.setdefault(p.payload["doc_name"],
                                {"doc_name": p.payload["doc_name"],
                                 "access_level": p.payload["access_level"], "chunks": 0})
            d["chunks"] += 1
        if offset is None:
            break
    return sorted(docs.values(), key=lambda d: d["doc_name"])


def delete_document(ctx: TenantContext, doc_name: str) -> None:
    ensure_collection()
    doc_id = str(uuid.uuid5(ctx.tenant_id, doc_name))
    client = get_qdrant()
    qdrant_retry(lambda: client.delete(
        settings.QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(filter=_doc_filter(ctx, doc_id)),
    ))