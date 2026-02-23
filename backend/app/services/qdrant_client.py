"""Qdrant client and collection helpers."""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

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


def collection_exists(kb_id: int, embedding_version: str = DEFAULT_EMBEDDING_VERSION) -> bool:
    name = collection_name(kb_id, embedding_version)
    client = get_qdrant()
    collections = client.get_collections().collections
    return any(c.name == name for c in collections)


def delete_collection(kb_id: int, embedding_version: str = DEFAULT_EMBEDDING_VERSION) -> bool:
    """Delete an embedding collection for a KB if present."""
    if not collection_exists(kb_id, embedding_version):
        return False
    coll = collection_name(kb_id, embedding_version)
    get_qdrant().delete_collection(collection_name=coll)
    return True


def list_collections_for_kb(kb_id: int) -> list[str]:
    prefix = f"{COLLECTION_PREFIX}_kb{kb_id}_"
    client = get_qdrant()
    collections = client.get_collections().collections
    return [c.name for c in collections if c.name.startswith(prefix)]


def delete_all_collections_for_kb(kb_id: int) -> int:
    names = list_collections_for_kb(kb_id)
    for name in names:
        get_qdrant().delete_collection(collection_name=name)
    return len(names)


def upsert_chunks(collection: str, points: list[PointStruct]):
    get_qdrant().upsert(collection_name=collection, points=points)


def delete_document_chunks(kb_id: int, doc_id: int, embedding_version: str = DEFAULT_EMBEDDING_VERSION) -> None:
    """Delete all points for a document from a KB collection."""
    if not collection_exists(kb_id, embedding_version):
        return
    coll = collection_name(kb_id, embedding_version)
    query_filter = Filter(
        must=[
            FieldCondition(
                key="doc_id",
                match=MatchValue(value=doc_id),
            )
        ]
    )
    get_qdrant().delete(collection_name=coll, points_selector=query_filter, wait=True)


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
