"""Document ingestion Celery task: parse, chunk, embed, index."""
import uuid
from app.core.celery_app import celery_app
from app.ingestion.chunking import chunk_text
from app.ingestion.embedding import embed_texts
from app.ingestion.parsers import parse_document
from app.models.base import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.user import User  # noqa: F401 - ensure mapper registration for relationships
from app.core.config import settings
from app.services.embedding_versions import (
    complete_embedding_migration,
    fail_embedding_migration,
    get_active_embedding_version,
    normalize_embedding_version,
    update_embedding_migration_progress,
)
from app.services.ingestion_tracking import (
    mark_ingestion_job_completed,
    mark_ingestion_job_failed,
    mark_ingestion_job_running,
    resolve_dead_letters_for_document,
    update_ingestion_job_progress,
)
from app.services.embedding_versions import get_active_embedding_version
from app.services.qdrant_client import delete_document_chunks, ensure_collection, upsert_chunks
from app.services.storage import get_stream
from qdrant_client.models import PointStruct


def _update_doc_status(doc_id: int, status: str, error_message: str | None = None):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = status
            if error_message is not None:
                doc.error_message = error_message
            elif status != DocumentStatus.FAILED:
                doc.error_message = None
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True)
def ingest_document(
    self,
    document_id: int,
    ingestion_job_id: int | None = None,
    embedding_version: str | None = None,
) -> dict:
    """Parse, chunk, embed, and index a document."""
    def _job_running(progress: int | None = None) -> None:
        if ingestion_job_id is None:
            return
        dbj = SessionLocal()
        try:
            mark_ingestion_job_running(dbj, job_id=ingestion_job_id, progress=progress)
        finally:
            dbj.close()

    def _job_progress(progress: int) -> None:
        if ingestion_job_id is None:
            return
        dbj = SessionLocal()
        try:
            update_ingestion_job_progress(dbj, job_id=ingestion_job_id, progress=progress)
        finally:
            dbj.close()

    def _job_completed(progress: int = 100) -> None:
        if ingestion_job_id is None:
            return
        dbj = SessionLocal()
        try:
            mark_ingestion_job_completed(dbj, job_id=ingestion_job_id, progress=progress)
        finally:
            dbj.close()

    def _job_failed(error_message: str, stage: str) -> None:
        if ingestion_job_id is None:
            return
        dbj = SessionLocal()
        try:
            mark_ingestion_job_failed(
                dbj,
                job_id=ingestion_job_id,
                error_message=error_message,
                failure_stage=stage,
                record_dead_letter=True,
            )
        finally:
            dbj.close()

    def _resolve_dlq() -> None:
        dbj = SessionLocal()
        try:
            resolve_dead_letters_for_document(dbj, document_id=document_id)
        finally:
            dbj.close()

    _update_doc_status(document_id, DocumentStatus.PROCESSING)
    _job_running(progress=5)
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            _job_failed("document not found", "load")
            return {"document_id": document_id, "status": "not_found"}
        object_key = doc.object_key
        filename = doc.filename
        stream = get_stream(object_key)
        content = stream.read()
    except Exception as e:
        _update_doc_status(document_id, DocumentStatus.FAILED, str(e))
        _job_failed(str(e), "load")
        return {"document_id": document_id, "status": "failed", "error": str(e)}
    finally:
        db.close()

    stage = "parse"
    try:
        self.update_state(state="PROCESSING", meta={"progress": 10})
        _job_progress(10)
        text, parse_meta = parse_document(content, filename)
        stage = "chunk"
        self.update_state(state="PROCESSING", meta={"progress": 30})
        _job_progress(30)

        chunks = chunk_text(
            text,
            max_chunk_chars=settings.chunk_max_chars,
            overlap_chars=settings.chunk_overlap_chars,
            overlap_sentences=settings.chunk_overlap_sentences,
            min_chunk_chars=settings.chunk_min_chars,
            metadata_base={"source": filename, "doc_id": document_id, **parse_meta},
        )
        if not chunks:
            _update_doc_status(document_id, DocumentStatus.INDEXED)
            _job_completed(progress=100)
            _resolve_dlq()
            return {"document_id": document_id, "status": "indexed", "chunks": 0}

        stage = "embed"
        self.update_state(state="PROCESSING", meta={"progress": 50})
        _job_progress(50)
        texts = [c.text for c in chunks]
        vectors = embed_texts(texts)
        stage = "index"
        self.update_state(state="PROCESSING", meta={"progress": 70})
        _job_progress(70)

        db2 = SessionLocal()
        try:
            doc_ref = db2.query(Document).filter(Document.id == document_id).first()
            kb_id = doc_ref.knowledge_base_id if doc_ref else 1
            resolved_embedding_version = (embedding_version or "").strip() or get_active_embedding_version(db2, kb_id)
        finally:
            db2.close()

        coll = ensure_collection(kb_id, embedding_version=resolved_embedding_version)
        # Ensure re-indexing a document does not leave stale chunks behind.
        delete_document_chunks(
            kb_id=kb_id,
            doc_id=document_id,
            embedding_version=resolved_embedding_version,
        )
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
        _job_progress(100)
        _update_doc_status(document_id, DocumentStatus.INDEXED)
        _job_completed(progress=100)
        _resolve_dlq()
        return {"document_id": document_id, "status": "indexed", "chunks": len(chunks)}
    except Exception as e:
        _update_doc_status(document_id, DocumentStatus.FAILED, str(e))
        _job_failed(str(e), stage)
        return {"document_id": document_id, "status": "failed", "error": str(e)}


@celery_app.task(bind=True)
def migrate_kb_embedding_namespace(self, kb_id: int, target_version: str) -> dict:
    """Re-index all documents in a KB into target embedding namespace."""
    version = normalize_embedding_version(target_version)
    db = SessionLocal()
    try:
        docs = (
            db.query(Document)
            .filter(Document.knowledge_base_id == kb_id)
            .order_by(Document.id.asc())
            .all()
        )
    finally:
        db.close()

    total = len(docs)
    indexed_docs = 0
    errors: list[str] = []

    for idx, doc in enumerate(docs, start=1):
        stage = "load"
        try:
            content = get_stream(doc.object_key).read()
            stage = "parse"
            text, parse_meta = parse_document(content, doc.filename)
            stage = "chunk"
            chunks = chunk_text(
                text,
                max_chunk_chars=settings.chunk_max_chars,
                overlap_chars=settings.chunk_overlap_chars,
                overlap_sentences=settings.chunk_overlap_sentences,
                min_chunk_chars=settings.chunk_min_chars,
                metadata_base={"source": doc.filename, "doc_id": doc.id, **parse_meta},
            )
            stage = "embed"
            vectors = embed_texts([chunk.text for chunk in chunks]) if chunks else []
            stage = "index"
            coll = ensure_collection(kb_id, embedding_version=version)
            delete_document_chunks(kb_id=kb_id, doc_id=doc.id, embedding_version=version)
            if chunks:
                points = [
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vec,
                        payload={"text": chunk.text, "metadata": chunk.metadata, "doc_id": doc.id},
                    )
                    for chunk, vec in zip(chunks, vectors)
                ]
                upsert_chunks(coll, points)
            indexed_docs += 1
        except Exception as exc:
            errors.append(f"doc_id={doc.id},stage={stage},error={exc}")

        progress = int((idx / max(1, total)) * 100)
        dbp = SessionLocal()
        try:
            update_embedding_migration_progress(
                dbp,
                kb_id=kb_id,
                target_version=version,
                progress=progress,
                indexed_documents=indexed_docs,
            )
        finally:
            dbp.close()
        self.update_state(
            state="PROCESSING",
            meta={"kb_id": kb_id, "target_version": version, "progress": progress},
        )

    if errors:
        dbf = SessionLocal()
        try:
            fail_embedding_migration(
                dbf,
                kb_id=kb_id,
                error_message="; ".join(errors)[:3000],
            )
        finally:
            dbf.close()
        return {
            "kb_id": kb_id,
            "target_version": version,
            "status": "failed",
            "indexed_documents": indexed_docs,
            "errors": errors[:5],
        }

    dbc = SessionLocal()
    try:
        complete_embedding_migration(
            dbc,
            kb_id=kb_id,
            target_version=version,
            indexed_documents=indexed_docs,
        )
    finally:
        dbc.close()
    return {
        "kb_id": kb_id,
        "target_version": version,
        "status": "completed",
        "indexed_documents": indexed_docs,
        "total_documents": total,
    }
