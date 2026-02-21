"""Document ingestion Celery task: parse, chunk, embed, index."""
import hashlib
import uuid
from app.core.celery_app import celery_app
from app.ingestion.chunking import chunk_text
from app.ingestion.embedding import embed_texts
from app.ingestion.parsers import parse_document
from app.models.base import SessionLocal, Base
from app.models.document import Document, DocumentStatus
from app.models.user import User  # noqa: F401 - ensure mapper registration for relationships
from app.services.qdrant_client import ensure_collection, upsert_chunks, collection_name
from app.services.storage import get_stream
from qdrant_client.models import PointStruct


def _update_doc_status(doc_id: int, status: str, error_message: str | None = None):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = status
            if error_message:
                doc.error_message = error_message
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True)
def ingest_document(self, document_id: int) -> dict:
    """Parse, chunk, embed, and index a document."""
    _update_doc_status(document_id, DocumentStatus.PROCESSING)
    db = SessionLocal()
    doc = None
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return {"document_id": document_id, "status": "not_found"}
        object_key = doc.object_key
        filename = doc.filename
        stream = get_stream(object_key)
        content = stream.read()
    except Exception as e:
        _update_doc_status(document_id, DocumentStatus.FAILED, str(e))
        return {"document_id": document_id, "status": "failed", "error": str(e)}
    finally:
        db.close()

    self.update_state(state="PROCESSING", meta={"progress": 10})
    text, parse_meta = parse_document(content, filename)
    self.update_state(state="PROCESSING", meta={"progress": 30})

    chunks = chunk_text(text, metadata_base={"source": doc.filename, "doc_id": document_id, **parse_meta})
    if not chunks:
        _update_doc_status(document_id, DocumentStatus.INDEXED)
        return {"document_id": document_id, "status": "indexed", "chunks": 0}

    self.update_state(state="PROCESSING", meta={"progress": 50})
    texts = [c.text for c in chunks]
    vectors = embed_texts(texts)
    self.update_state(state="PROCESSING", meta={"progress": 70})

    db2 = SessionLocal()
    doc_ref = db2.query(Document).filter(Document.id == document_id).first()
    kb_id = doc_ref.knowledge_base_id if doc_ref else 1
    db2.close()
    coll = ensure_collection(kb_id)
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload={"text": c.text, "metadata": c.metadata, "doc_id": document_id},
        )
        for c, vec in zip(chunks, vectors)
    ]
    upsert_chunks(coll, points)
    self.update_state(state="PROCESSING", meta={"progress": 100})
    _update_doc_status(document_id, DocumentStatus.INDEXED)
    return {"document_id": document_id, "status": "indexed", "chunks": len(chunks)}
