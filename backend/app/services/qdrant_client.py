"""Qdrant client and collection helpers."""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.ingestion.embedding import get_embedding_dim

_client: QdrantClient | None = None
COLLECTION_PREFIX = "ragnetic"
DEFAULT_EMBEDDING_VERSION = "v1"


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url)
    return _client


def collection_name(kb_id: int, embedding_version: str = DEFAULT_EMBEDDING_VERSION) -> str:
    return f"{COLLECTION_PREFIX}_kb{kb_id}_{embedding_version}"


def ensure_collection(kb_id: int, embedding_version: str = DEFAULT_EMBEDDING_VERSION) -> str:
    name = collection_name(kb_id, embedding_version)
    dim = get_embedding_dim()
    client = get_qdrant()
    collections = client.get_collections().collections
    if not any(c.name == name for c in collections):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    return name


def upsert_chunks(collection: str, points: list[PointStruct]):
    get_qdrant().upsert(collection_name=collection, points=points)


def search_collection(collection: str, vector: list[float], limit: int = 5):
    client = get_qdrant()
    # qdrant-client compatibility across versions:
    # - older: client.search(...)
    # - newer: client.query_points(...)
    if hasattr(client, "search"):
        return client.search(collection_name=collection, query_vector=vector, limit=limit)
    response = client.query_points(
        collection_name=collection,
        query=vector,
        limit=limit,
        with_payload=True,
    )
    return getattr(response, "points", response)
