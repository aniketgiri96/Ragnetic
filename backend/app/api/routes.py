"""API routes for upload, search, and chat."""
import hashlib
import io
import uuid
from typing import Any, List

from fastapi import File, Query, UploadFile
from fastapi.responses import HTMLResponse

from app.ingestion.embedding import embed_texts
from app.models.base import SessionLocal
from app.models.document import Document, DocumentStatus, KnowledgeBase
from app.services.llm import generate as llm_generate
from app.services.qdrant_client import ensure_collection, get_qdrant
from app.services.storage import upload_file
from app.tasks.ingestion import ingest_document

# Fallback in-memory storage when DB/MinIO/Celery not fully available
_documents: List[bytes] = []


def _get_default_kb_id() -> int | None:
    db = SessionLocal()
    try:
        kb = db.query(KnowledgeBase).first()
        return kb.id if kb else None
    finally:
        db.close()


async def upload_document(file: UploadFile = File(...), kb_id: int = Query(None, description="Knowledge base ID")):
    content = await file.read()
    kb = kb_id or _get_default_kb_id()
    if kb is None:
        return {"filename": file.filename, "status": "queued", "message": "Using in-memory fallback (no KB)"}
    try:
        object_key = f"uploads/{uuid.uuid4().hex}/{file.filename}"
        content_hash = hashlib.sha256(content).hexdigest()
        upload_file(object_key, io.BytesIO(content), len(content), file.content_type or "application/octet-stream")
        db = SessionLocal()
        try:
            doc = Document(knowledge_base_id=kb, filename=file.filename, object_key=object_key, content_hash=content_hash)
            db.add(doc)
            db.commit()
            db.refresh(doc)
            ingest_document.delay(doc.id)
            return {"filename": file.filename, "status": "queued", "document_id": doc.id}
        finally:
            db.close()
    except Exception as e:
        _documents.append(content)
        return {"filename": file.filename, "status": "queued", "message": str(e)}


def get_documents() -> List[bytes]:
    return _documents


async def search_documents(query: str, kb_id: int = Query(None)):
    kb = kb_id or _get_default_kb_id()
    if kb is not None:
        try:
            coll = ensure_collection(kb)
            vectors = embed_texts([query])
            results = get_qdrant().search(collection_name=coll, query_vector=vectors[0], limit=5)
            return [
                {"snippet": r.payload.get("text", "")[:300], "score": r.score, "metadata": r.payload.get("metadata", {})}
                for r in results
            ]
        except Exception:
            pass
    docs = get_documents()
    return [
        {"snippet": doc.decode("utf-8", errors="replace")[:200]}
        for doc in docs
        if query.lower() in doc.decode("utf-8", errors="replace").lower()
    ]


def _retrieve_for_chat(kb_id: int, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return list of {snippet, metadata} for RAG context."""
    try:
        coll = ensure_collection(kb_id)
        vectors = embed_texts([query])
        results = get_qdrant().search(collection_name=coll, query_vector=vectors[0], limit=limit)
        return [
            {"snippet": r.payload.get("text", ""), "metadata": r.payload.get("metadata", {})}
            for r in results
        ]
    except Exception:
        return []


async def chat_rag(message: str, kb_id: int | None = None, session_id: str | None = None) -> dict:
    """RAG chat: retrieve chunks, build prompt, call LLM, return answer + sources."""
    kb = kb_id or _get_default_kb_id()
    sources: list[dict[str, Any]] = []
    if kb is not None:
        sources = _retrieve_for_chat(kb, message)
    context_blocks = "\n\n---\n\n".join(
        f"[Source {i+1}]\n{s['snippet']}" for i, s in enumerate(sources)
    )
    if not context_blocks:
        context_blocks = "(No relevant documents found in the knowledge base.)"
    system = (
        "Answer only using the following context. "
        "If the context does not contain enough information, say so. "
        "Mention which source number you use when possible."
    )
    user_prompt = f"Context:\n\n{context_blocks}\n\nQuestion: {message}"
    try:
        answer = await llm_generate(user_prompt, system=system)
    except Exception as e:
        answer = f"(LLM error: {e}. Ensure Ollama is running or set OPENAI_API_KEY.)"
    return {"answer": answer, "sources": sources}


async def chat(message: str) -> dict:
    """Legacy echo; use chat_rag with JSON body instead."""
    return {"message": f"You said: {message}"}


async def root() -> HTMLResponse:
    return HTMLResponse(
        "<h1>KnowAI — Open-Source RAG Knowledge Base Platform</h1>"
        "<p>API docs: <a href='/docs'>/docs</a></p>"
    )


def list_knowledge_bases() -> list:
    db = SessionLocal()
    try:
        kbs = db.query(KnowledgeBase).all()
        return [{"id": kb.id, "name": kb.name, "description": kb.description} for kb in kbs]
    finally:
        db.close()


def get_document_status(document_id: int) -> dict | None:
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return None
        return {"document_id": doc.id, "filename": doc.filename, "status": doc.status, "error_message": doc.error_message}
    finally:
        db.close()
