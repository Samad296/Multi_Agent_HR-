import time
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client import models as qm
from sentence_transformers import SentenceTransformer

from app.core.config import settings

VECTOR_SIZE = 384  # all-MiniLM-L6-v2


def qdrant_retry(fn, tries: int = 5):
    for attempt in range(tries):
        try:
            return fn()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)   # 1s, 2s, 4s, 8s


@lru_cache
def get_qdrant() -> QdrantClient:
    if not settings.QDRANT_URL:                      # no URL set -> local mode, no network
        return QdrantClient(path="./.qdrant_local")
    return QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=60,
        check_compatibility=False,
    )


@lru_cache
def _model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBED_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True, batch_size=32).tolist()


_collection_ready = False


def ensure_collection() -> None:
    global _collection_ready
    if _collection_ready:            # checked once per process, not on every call
        return
    client = get_qdrant()
    name = settings.QDRANT_COLLECTION
    if not qdrant_retry(lambda: client.collection_exists(name)):
        qdrant_retry(lambda: client.create_collection(
            name, vectors_config=qm.VectorParams(size=VECTOR_SIZE, distance=qm.Distance.COSINE)))
        if settings.QDRANT_URL:      # payload indexes only apply to a server, not local mode
            for field in ("tenant_id", "access_level", "doc_id"):
                qdrant_retry(lambda f=field: client.create_payload_index(
                    name, f, qm.PayloadSchemaType.KEYWORD))
    _collection_ready = True