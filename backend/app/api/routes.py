"""API routes for upload, search, and chat."""
import hashlib
import io
import uuid
from typing import Any

from fastapi import File, Query, UploadFile
from fastapi import HTTPException, status
from fastapi.responses import HTMLResponse

from app.models.base import SessionLocal
from app.models.document import Document, DocumentStatus, KnowledgeBaseMembership, KnowledgeBaseRole
from app.models.user import User
from app.core.config import settings
from app.services.access import get_default_accessible_kb_id, list_user_knowledge_bases, require_kb_access
from app.services.llm import generate as llm_generate
from app.services.retrieval import hybrid_retrieve
from app.services.storage import upload_file
from app.tasks.ingestion import ingest_document

VALID_KB_ROLES = {
    KnowledgeBaseRole.OWNER,
    KnowledgeBaseRole.EDITOR,
    KnowledgeBaseRole.VIEWER,
}


def _resolve_kb_for_user(user: User, kb_id: int | None, min_role: str) -> int:
    db = SessionLocal()
    try:
        resolved = kb_id if kb_id is not None else get_default_accessible_kb_id(db, user.id, min_role=min_role)
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No accessible knowledge base found for this user.",
            )
        require_kb_access(db, user.id, resolved, min_role=min_role)
        return resolved
    finally:
        db.close()


async def upload_document(
    user: User,
    file: UploadFile = File(...),
    kb_id: int = Query(None, description="Knowledge base ID"),
):
    content = await file.read()
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.EDITOR)
    try:
        object_key = f"uploads/{uuid.uuid4().hex}/{file.filename}"
        content_hash = hashlib.sha256(content).hexdigest()
        db = SessionLocal()
        try:
            existing = (
                db.query(Document)
                .filter(
                    Document.knowledge_base_id == kb,
                    Document.content_hash == content_hash,
                    Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING, DocumentStatus.INDEXED]),
                )
                .order_by(Document.id.desc())
                .first()
            )
            if existing:
                return {
                    "filename": file.filename,
                    "status": "queued",
                    "document_id": existing.id,
                    "deduplicated": True,
                    "message": "Identical content already queued/indexed in this knowledge base.",
                }

            upload_file(object_key, io.BytesIO(content), len(content), file.content_type or "application/octet-stream")
            doc = Document(knowledge_base_id=kb, filename=file.filename, object_key=object_key, content_hash=content_hash)
            db.add(doc)
            db.commit()
            db.refresh(doc)
            ingest_document.delay(doc.id)
            return {"filename": file.filename, "status": "queued", "document_id": doc.id}
        finally:
            db.close()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Upload pipeline unavailable: {e}",
        ) from e


async def search_documents(user: User, query: str, kb_id: int = Query(None)):
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.VIEWER)
    try:
        results = hybrid_retrieve(kb_id=kb, query=query, top_k=5)
        return [
            {
                "snippet": (r.get("snippet") or "")[:300],
                "score": r.get("score", 0.0),
                "metadata": r.get("metadata", {}),
                "dense_score": r.get("dense_score", 0.0),
                "sparse_score": r.get("sparse_score", 0.0),
            }
            for r in results
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search backend unavailable: {e}",
        ) from e


def _retrieve_for_chat(kb_id: int, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return list of {snippet, metadata} for RAG context."""
    try:
        results = hybrid_retrieve(kb_id=kb_id, query=query, top_k=limit)
        return [
            {"snippet": r.get("snippet", ""), "metadata": r.get("metadata", {}), "score": r.get("score", 0.0)}
            for r in results
        ]
    except Exception:
        return []


async def chat_rag(user: User, message: str, kb_id: int | None = None, session_id: str | None = None) -> dict:
    """RAG chat: retrieve chunks, build prompt, call LLM, return answer + sources."""
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.VIEWER)
    sources: list[dict[str, Any]] = _retrieve_for_chat(kb, message)
    context_blocks = "\n\n---\n\n".join(
        f"[Source {i+1}]\n{s['snippet']}" for i, s in enumerate(sources)
    )
    if not context_blocks:
        return {
            "answer": "No relevant documents found in the selected knowledge base yet. Upload documents and try again.",
            "sources": [],
        }
    system = (
        "Answer only using the following context. "
        "If the context does not contain enough information, say so. "
        "Mention which source number you use when possible."
    )
    user_prompt = f"Context:\n\n{context_blocks}\n\nQuestion: {message}"
    try:
        answer = await llm_generate(user_prompt, system=system)
    except Exception as e:
        detail = str(e).strip() or e.__class__.__name__
        if sources:
            excerpt = (sources[0].get("snippet") or "").strip().replace("\n", " ")
            excerpt = excerpt[:400] + ("..." if len(excerpt) > 400 else "")
            answer = (
                f"LLM unavailable ({detail}). Using top retrieved source instead: {excerpt}"
            )
        else:
            answer = (
                f"(LLM error: {detail}. Ensure Ollama is running with model "
                f"'{settings.ollama_model}' or set OPENAI_API_KEY.)"
            )
    return {"answer": answer, "sources": sources}


async def chat(message: str) -> dict:
    """Legacy echo; use chat_rag with JSON body instead."""
    return {"message": f"You said: {message}"}


async def root() -> HTMLResponse:
    return HTMLResponse(
        "<h1>Ragnetic — Open-Source RAG Knowledge Base Platform</h1>"
        "<p>API docs: <a href='/docs'>/docs</a></p>"
    )


def list_knowledge_bases(user: User) -> list:
    db = SessionLocal()
    try:
        return list_user_knowledge_bases(db, user.id)
    finally:
        db.close()


def get_document_status(user: User, document_id: int) -> dict | None:
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return None
        require_kb_access(db, user.id, doc.knowledge_base_id, min_role=KnowledgeBaseRole.VIEWER)
        return {"document_id": doc.id, "filename": doc.filename, "status": doc.status, "error_message": doc.error_message}
    finally:
        db.close()


def _assert_valid_kb_role(role: str) -> str:
    normalized = (role or "").strip().lower()
    if normalized not in VALID_KB_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{role}'. Allowed roles: owner, editor, viewer.",
        )
    return normalized


def _count_kb_owners(db, kb_id: int) -> int:
    return (
        db.query(KnowledgeBaseMembership)
        .filter(
            KnowledgeBaseMembership.knowledge_base_id == kb_id,
            KnowledgeBaseMembership.role == KnowledgeBaseRole.OWNER,
        )
        .count()
    )


def list_kb_members(user: User, kb_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.VIEWER)
        rows = (
            db.query(KnowledgeBaseMembership, User)
            .join(User, User.id == KnowledgeBaseMembership.user_id)
            .filter(KnowledgeBaseMembership.knowledge_base_id == kb_id)
            .order_by(KnowledgeBaseMembership.created_at.asc())
            .all()
        )
        return [
            {
                "kb_id": kb_id,
                "user_id": u.id,
                "email": u.email,
                "role": m.role,
                "created_at": m.created_at.isoformat(),
            }
            for m, u in rows
        ]
    finally:
        db.close()


def add_kb_member(user: User, kb_id: int, email: str, role: str) -> dict:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        target_role = _assert_valid_kb_role(role)
        target_user = db.query(User).filter(User.email == email).first()
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{email}' not found. User must register before being added.",
            )
        membership = (
            db.query(KnowledgeBaseMembership)
            .filter(
                KnowledgeBaseMembership.knowledge_base_id == kb_id,
                KnowledgeBaseMembership.user_id == target_user.id,
            )
            .first()
        )
        if membership:
            membership.role = target_role
        else:
            membership = KnowledgeBaseMembership(
                knowledge_base_id=kb_id,
                user_id=target_user.id,
                role=target_role,
            )
            db.add(membership)
        db.commit()
        return {
            "kb_id": kb_id,
            "user_id": target_user.id,
            "email": target_user.email,
            "role": membership.role,
            "created_at": membership.created_at.isoformat(),
        }
    finally:
        db.close()


def update_kb_member_role(user: User, kb_id: int, member_user_id: int, role: str) -> dict:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        target_role = _assert_valid_kb_role(role)
        membership = (
            db.query(KnowledgeBaseMembership)
            .filter(
                KnowledgeBaseMembership.knowledge_base_id == kb_id,
                KnowledgeBaseMembership.user_id == member_user_id,
            )
            .first()
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found for this knowledge base.")

        if membership.role == KnowledgeBaseRole.OWNER and target_role != KnowledgeBaseRole.OWNER:
            if _count_kb_owners(db, kb_id) <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change role of the last owner.",
                )
        membership.role = target_role
        db.commit()

        target_user = db.query(User).filter(User.id == member_user_id).first()
        return {
            "kb_id": kb_id,
            "user_id": member_user_id,
            "email": target_user.email if target_user else None,
            "role": membership.role,
            "created_at": membership.created_at.isoformat(),
        }
    finally:
        db.close()


def remove_kb_member(user: User, kb_id: int, member_user_id: int) -> dict:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        membership = (
            db.query(KnowledgeBaseMembership)
            .filter(
                KnowledgeBaseMembership.knowledge_base_id == kb_id,
                KnowledgeBaseMembership.user_id == member_user_id,
            )
            .first()
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found for this knowledge base.")
        if membership.role == KnowledgeBaseRole.OWNER and _count_kb_owners(db, kb_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner.",
            )
        db.delete(membership)
        db.commit()
        return {"message": "Member removed."}
    finally:
        db.close()
