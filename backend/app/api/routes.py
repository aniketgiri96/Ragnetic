"""API routes for upload, search, and chat."""
from datetime import datetime
import hashlib
import io
import json
import logging
import re
import time
import uuid
from typing import Any

from fastapi import File, Query, UploadFile
from fastapi import HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import desc

from app.models.base import SessionLocal
from app.models.chat import ChatJob, ChatJobStatus, ChatMessage, ChatRole, ChatSession
from app.models.document import Document, DocumentStatus, KnowledgeBaseMembership, KnowledgeBaseRole
from app.models.user import User
from app.core.config import settings
from app.services.access import get_default_accessible_kb_id, list_user_knowledge_bases, require_kb_access
from app.services.llm import generate as llm_generate
from app.services.llm import generate_stream as llm_generate_stream
from app.services.retrieval import hybrid_retrieve
from app.services.storage import upload_file
from app.tasks.chat import process_chat_job
from app.tasks.ingestion import ingest_document

VALID_KB_ROLES = {
    KnowledgeBaseRole.OWNER,
    KnowledgeBaseRole.EDITOR,
    KnowledgeBaseRole.VIEWER,
}
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
ASYNC_HINT_RE = re.compile(
    r"\b(long|detailed|in-depth|comprehensive|elaborate|step[- ]by[- ]step|thorough|bullet)\b",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


def _normalize_session_id(session_id: str | None) -> str:
    if session_id is None:
        return uuid.uuid4().hex
    normalized = session_id.strip()
    if not normalized:
        return uuid.uuid4().hex
    if not SESSION_ID_RE.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id must be 1-128 chars and contain only letters, numbers, ., _, :, -",
        )
    return normalized


def _should_queue_async(message: str) -> bool:
    normalized = (message or "").strip()
    if len(normalized) >= 260:
        return True
    return bool(ASYNC_HINT_RE.search(normalized))


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


def _reasoning_event(step: str, detail: str, elapsed_ms: int) -> dict[str, Any]:
    return {
        "step": step,
        "detail": detail,
        "elapsed_ms": elapsed_ms,
    }


def _source_previews(sources: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for i, item in enumerate(sources[:limit]):
        metadata = item.get("metadata") or {}
        name = metadata.get("source") or metadata.get("filename") or f"Source {i + 1}"
        snippet = (item.get("snippet") or "").replace("\n", " ").strip()
        previews.append(
            {
                "name": name,
                "score": float(item.get("score", 0.0)),
                "snippet_preview": snippet[:120] + ("..." if len(snippet) > 120 else ""),
            }
        )
    return previews


def _get_or_create_chat_session(db, user_id: int, kb_id: int, session_id: str) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session:
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if session.knowledge_base_id != kb_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session belongs to a different knowledge base.",
            )
        return session
    session = ChatSession(id=session_id, user_id=user_id, knowledge_base_id=kb_id)
    db.add(session)
    db.flush()
    return session


def _history_for_prompt(db, session_id: str, max_messages: int = 10) -> str:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(desc(ChatMessage.id))
        .limit(max_messages)
        .all()
    )
    if not rows:
        return ""
    ordered = list(reversed(rows))
    lines = []
    for msg in ordered:
        speaker = "User" if msg.role == ChatRole.USER else "Assistant"
        lines.append(f"{speaker}: {msg.content}")
    return "\n".join(lines)


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
    except Exception as e:
        logger.exception("Chat retrieval failed for kb_id=%s", kb_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Retrieval backend unavailable: {e}",
        ) from e


def _build_chat_prompt(message: str, history: str, sources: list[dict[str, Any]]) -> tuple[str, str, str]:
    source_char_limit = max(120, settings.chat_context_max_chars_per_source)
    context_blocks = "\n\n---\n\n".join(
        f"[Source {i + 1}]\n{(s['snippet'] or '')[:source_char_limit]}" for i, s in enumerate(sources)
    )
    system = (
        "Answer only using the provided context blocks for factual claims. "
        "Use conversation history only for continuity. "
        "If context is insufficient, explicitly say so and do not fabricate facts. "
        "Mention source numbers when possible."
    )
    history_block = f"Conversation history:\n{history}\n\n" if history else ""
    user_prompt = f"{history_block}Context:\n\n{context_blocks}\n\nQuestion: {message}"
    return system, user_prompt, context_blocks


def _fallback_answer_from_sources(question: str, sources: list[dict[str, Any]], detail: str) -> str:
    snippets = [
        (s.get("snippet") or "").replace("\n", " ").strip()
        for s in sources
        if (s.get("snippet") or "").strip()
    ]
    if not snippets:
        return f"LLM unavailable ({detail}). No retrieved content is available yet."

    preview_lines = []
    for snippet in snippets[:3]:
        cut = snippet[:220] + ("..." if len(snippet) > 220 else "")
        preview_lines.append(f"- {cut}")
    return (
        f"LLM unavailable ({detail}). I could not generate a model answer. "
        "Top retrieved excerpts:\n" + "\n".join(preview_lines)
    )


def _queue_async_chat_job(user: User, kb: int, session_key: str, message: str) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    db = SessionLocal()
    try:
        _get_or_create_chat_session(db, user_id=user.id, kb_id=kb, session_id=session_key)
        db.add(ChatMessage(session_id=session_key, role=ChatRole.USER, content=message))

        job = ChatJob(
            id=job_id,
            user_id=user.id,
            knowledge_base_id=kb,
            session_id=session_key,
            question=message,
            status=ChatJobStatus.QUEUED,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    try:
        process_chat_job.delay(job_id)
    except Exception as exc:
        db2 = SessionLocal()
        try:
            failed_job = db2.query(ChatJob).filter(ChatJob.id == job_id).first()
            if failed_job is not None:
                failed_job.status = ChatJobStatus.FAILED
                failed_job.error_message = str(exc)
                failed_job.finished_at = datetime.utcnow()
                db2.commit()
        finally:
            db2.close()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue chat job. Check worker and broker availability.",
        ) from exc
    return {"mode": "async", "status": ChatJobStatus.QUEUED, "job_id": job_id, "session_id": session_key}


async def chat_rag(
    user: User,
    message: str,
    kb_id: int | None = None,
    session_id: str | None = None,
    async_mode: bool | None = None,
) -> dict:
    """RAG chat: sync response for short queries, async job for long ones."""
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.VIEWER)
    session_key = _normalize_session_id(session_id)
    should_queue_async = async_mode if async_mode is not None else _should_queue_async(message)
    if should_queue_async:
        return _queue_async_chat_job(user=user, kb=kb, session_key=session_key, message=message)

    db = SessionLocal()
    try:
        session = _get_or_create_chat_session(db, user_id=user.id, kb_id=kb, session_id=session_key)
        history = _history_for_prompt(db, session_key, max_messages=10)

        source_limit = max(1, settings.chat_context_max_sources)
        sources: list[dict[str, Any]] = _retrieve_for_chat(kb, message, limit=source_limit)
        system, user_prompt, context_blocks = _build_chat_prompt(message=message, history=history, sources=sources)
        if not context_blocks:
            answer = "No relevant documents found in the selected knowledge base yet. Upload documents and try again."
            db.add(ChatMessage(session_id=session_key, role=ChatRole.USER, content=message))
            db.add(ChatMessage(session_id=session_key, role=ChatRole.ASSISTANT, content=answer))
            session.updated_at = datetime.utcnow()
            db.commit()
            return {"answer": answer, "sources": [], "session_id": session_key}

        try:
            answer = await llm_generate(user_prompt, system=system)
        except Exception as e:
            detail = str(e).strip() or e.__class__.__name__
            logger.warning("LLM generation failed for kb_id=%s session_id=%s: %s", kb, session_key, detail)
            answer = _fallback_answer_from_sources(message, sources, detail)

        db.add(ChatMessage(session_id=session_key, role=ChatRole.USER, content=message))
        db.add(ChatMessage(session_id=session_key, role=ChatRole.ASSISTANT, content=answer))
        session.updated_at = datetime.utcnow()
        db.commit()
        return {"answer": answer, "sources": sources, "session_id": session_key}
    finally:
        db.close()


async def chat_rag_stream(
    user: User,
    message: str,
    kb_id: int | None = None,
    session_id: str | None = None,
) -> StreamingResponse:
    """RAG chat streaming endpoint returning SSE token events."""
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.VIEWER)
    session_key = _normalize_session_id(session_id)

    db = SessionLocal()
    try:
        session = _get_or_create_chat_session(db, user_id=user.id, kb_id=kb, session_id=session_key)
        history = _history_for_prompt(db, session_key, max_messages=10)
        db.add(ChatMessage(session_id=session_key, role=ChatRole.USER, content=message))
        session.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    async def event_stream():
        started_at = time.monotonic()
        source_limit = max(1, settings.chat_context_max_sources)
        sources: list[dict[str, Any]] = []
        answer = ""
        fallback = False
        last_heartbeat = started_at

        def elapsed_ms() -> int:
            return int((time.monotonic() - started_at) * 1000)

        yield _sse("meta", {"session_id": session_key, "trace_mode": "public"})
        yield _sse("reasoning", _reasoning_event("understand", "Understanding your question.", elapsed_ms()))
        yield _sse("reasoning", _reasoning_event("retrieve", "Searching relevant knowledge base content.", elapsed_ms()))

        try:
            sources = _retrieve_for_chat(kb, message, limit=source_limit)
        except HTTPException as e:
            detail = str(e.detail).strip() if getattr(e, "detail", None) else "Retrieval backend unavailable"
            fallback = True
            answer = f"Retrieval unavailable ({detail}). Please try again shortly."
            yield _sse("error", {"detail": detail, "stage": "retrieve"})
            yield _sse("reasoning", _reasoning_event("fallback", "Switching to fallback mode.", elapsed_ms()))
            sources = []
        else:
            yield _sse(
                "reasoning",
                _reasoning_event("evidence", f"Found {len(sources)} relevant chunks.", elapsed_ms()),
            )
            previews = _source_previews(sources, limit=3)
            if previews:
                yield _sse("sources_preview", {"sources": previews, "elapsed_ms": elapsed_ms()})

        system = ""
        user_prompt = ""
        context_blocks = ""
        if not fallback:
            system, user_prompt, context_blocks = _build_chat_prompt(message=message, history=history, sources=sources)

            if not context_blocks:
                fallback = True
                answer = "No relevant documents found in the selected knowledge base yet. Upload documents and try again."
                yield _sse("reasoning", _reasoning_event("no_context", "No grounded context found for this question.", elapsed_ms()))
            else:
                chunks: list[str] = []
                first_token = True
                yield _sse("reasoning", _reasoning_event("draft", "Drafting an answer from retrieved evidence.", elapsed_ms()))
                try:
                    async for chunk in llm_generate_stream(user_prompt, system=system):
                        if not chunk:
                            continue
                        if first_token:
                            first_token = False
                            yield _sse("reasoning", _reasoning_event("evolve", "Evolving response in real time.", elapsed_ms()))
                        chunks.append(chunk)
                        yield _sse("token", {"delta": chunk})
                        now = time.monotonic()
                        if now - last_heartbeat >= 2.5:
                            last_heartbeat = now
                            yield _sse(
                                "heartbeat",
                                {
                                    "state": "generating",
                                    "elapsed_ms": elapsed_ms(),
                                    "tokens": len(chunks),
                                },
                            )
                except Exception as e:
                    detail = str(e).strip() or e.__class__.__name__
                    logger.warning("Streaming LLM failed for kb_id=%s session_id=%s: %s", kb, session_key, detail)
                    fallback = True
                    answer = _fallback_answer_from_sources(message, sources, detail)
                    yield _sse("error", {"detail": detail, "stage": "generate"})
                    yield _sse("reasoning", _reasoning_event("fallback", "LLM unavailable. Returning extractive fallback.", elapsed_ms()))
                if not fallback:
                    answer = "".join(chunks).strip() or "No response generated."

        db2 = SessionLocal()
        try:
            session = _get_or_create_chat_session(db2, user_id=user.id, kb_id=kb, session_id=session_key)
            db2.add(ChatMessage(session_id=session_key, role=ChatRole.ASSISTANT, content=answer))
            session.updated_at = datetime.utcnow()
            db2.commit()
        finally:
            db2.close()

        yield _sse("reasoning", _reasoning_event("finalize", "Finalizing response and sources.", elapsed_ms()))
        yield _sse(
            "done",
            {
                "answer": answer,
                "sources": sources,
                "session_id": session_key,
                "fallback": fallback,
                "elapsed_ms": elapsed_ms(),
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def get_chat_job(user: User, job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        job = (
            db.query(ChatJob)
            .filter(ChatJob.id == job_id, ChatJob.user_id == user.id)
            .first()
        )
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat job not found")
        require_kb_access(db, user.id, job.knowledge_base_id, min_role=KnowledgeBaseRole.VIEWER)
        sources: list[dict[str, Any]] = []
        if job.sources_json:
            try:
                parsed = json.loads(job.sources_json)
                if isinstance(parsed, list):
                    sources = parsed
            except json.JSONDecodeError:
                sources = []
        return {
            "job_id": job.id,
            "status": job.status,
            "session_id": job.session_id,
            "answer": job.answer,
            "sources": sources,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
    finally:
        db.close()


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


def list_chat_sessions(user: User, kb_id: int | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        kb_filter = None
        if kb_id is not None:
            require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.VIEWER)
            kb_filter = kb_id

        q = db.query(ChatSession).filter(ChatSession.user_id == user.id)
        if kb_filter is not None:
            q = q.filter(ChatSession.knowledge_base_id == kb_filter)
        sessions = q.order_by(desc(ChatSession.updated_at), desc(ChatSession.created_at)).all()

        out = []
        for s in sessions:
            latest = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == s.id)
                .order_by(desc(ChatMessage.id))
                .first()
            )
            count = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).count()
            out.append(
                {
                    "session_id": s.id,
                    "kb_id": s.knowledge_base_id,
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                    "message_count": count,
                    "last_message_preview": (latest.content[:140] + "...") if latest and len(latest.content) > 140 else (latest.content if latest else ""),
                }
            )
        return out
    finally:
        db.close()


def get_chat_session(user: User, session_id: str, limit: int = 100) -> dict:
    db = SessionLocal()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user.id)
            .first()
        )
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        require_kb_access(db, user.id, session.knowledge_base_id, min_role=KnowledgeBaseRole.VIEWER)
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(desc(ChatMessage.id))
            .limit(limit)
            .all()
        )
        messages = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(rows)
        ]
        return {
            "session_id": session.id,
            "kb_id": session.knowledge_base_id,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "messages": messages,
        }
    finally:
        db.close()


def delete_chat_session(user: User, session_id: str) -> dict:
    db = SessionLocal()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user.id)
            .first()
        )
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        require_kb_access(db, user.id, session.knowledge_base_id, min_role=KnowledgeBaseRole.VIEWER)
        db.delete(session)
        db.commit()
        return {"message": "Session deleted."}
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
