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
from sqlalchemy import desc, func

from app.models.base import SessionLocal
from app.models.analytics import ChatFeedback, FeedbackRating
from app.models.chat import ChatJob, ChatJobStatus, ChatMessage, ChatRole, ChatSession
from app.models.audit import AuditLog
from app.models.document import Document, DocumentStatus, KnowledgeBase, KnowledgeBaseMembership, KnowledgeBaseRole
from app.models.ingestion import IngestionDeadLetter, IngestionJobReason
from app.models.tenant import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    Team,
    TeamKnowledgeBaseAccess,
    TeamMembership,
    TeamRole,
)
from app.models.user import User
from app.core.config import settings
from app.services.access import get_default_accessible_kb_id, list_user_knowledge_bases, require_kb_access
from app.services.analytics import build_rag_analytics_report
from app.services.audit import log_audit_event, parse_details
from app.services.context import assemble_context
from app.services.citations import append_citation_legend, enforce_citation_format
from app.services.embedding_versions import (
    fail_embedding_migration,
    list_embedding_registry,
    normalize_embedding_version,
    start_embedding_migration,
)
from app.services.faithfulness import faithfulness_signals as compute_faithfulness_signals
from app.services.ingestion_tracking import (
    VALID_INGESTION_REASONS,
    create_ingestion_job,
    get_connector_sync_state,
    list_dead_letters,
    mark_connector_sync,
    mark_ingestion_job_failed,
    mark_ingestion_job_queued,
    should_replace_existing_upload,
)
from app.services.llm import generate as llm_generate
from app.services.llm import generate_stream as llm_generate_stream
from app.services.onboarding import build_onboarding_status
from app.services.query_expansion import build_query_variants
from app.services.qdrant_client import delete_all_collections_for_kb, delete_document_chunks
from app.services.retrieval import hybrid_retrieve
from app.services.storage import delete_file, upload_file
from app.tasks.chat import process_chat_job
from app.tasks.ingestion import _update_doc_status, ingest_document, migrate_kb_embedding_namespace

VALID_KB_ROLES = {
    KnowledgeBaseRole.OWNER,
    KnowledgeBaseRole.EDITOR,
    KnowledgeBaseRole.VIEWER,
    KnowledgeBaseRole.API_USER,
}
VALID_FEEDBACK_RATINGS = {
    FeedbackRating.UP,
    FeedbackRating.DOWN,
}
VALID_ORG_ROLES = {
    OrganizationRole.OWNER,
    OrganizationRole.ADMIN,
    OrganizationRole.MEMBER,
}
VALID_TEAM_ROLES = {
    TeamRole.MANAGER,
    TeamRole.MEMBER,
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


def _compact_query_text(query: str, limit: int = 240) -> str:
    normalized = (query or "").replace("\n", " ").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(1, limit - 3)] + "..."


def _normalize_feedback_rating(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in VALID_FEEDBACK_RATINGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rating must be 'up' or 'down'",
        )
    return normalized


ORG_ROLE_RANK = {
    OrganizationRole.MEMBER: 1,
    OrganizationRole.ADMIN: 2,
    OrganizationRole.OWNER: 3,
}
TEAM_ROLE_RANK = {
    TeamRole.MEMBER: 1,
    TeamRole.MANAGER: 2,
}


def _role_at_least(rank_map: dict[str, int], role: str, min_role: str) -> bool:
    return rank_map.get(role, 0) >= rank_map.get(min_role, 0)


def _normalize_org_role(role: str | None, default: str = OrganizationRole.MEMBER) -> str:
    normalized = (role or default).strip().lower()
    if normalized not in VALID_ORG_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization role. Allowed roles: owner, admin, member.",
        )
    return normalized


def _normalize_team_role(role: str | None, default: str = TeamRole.MEMBER) -> str:
    normalized = (role or default).strip().lower()
    if normalized not in VALID_TEAM_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid team role. Allowed roles: manager, member.",
        )
    return normalized


def _require_org_membership(
    db,
    user_id: int,
    org_id: int,
    min_role: str = OrganizationRole.MEMBER,
) -> OrganizationMembership:
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == user_id,
        )
        .first()
    )
    if membership is None or not _role_at_least(ORG_ROLE_RANK, membership.role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for organization {org_id}",
        )
    return membership


def _require_team_membership(
    db,
    user_id: int,
    team_id: int,
    min_role: str = TeamRole.MEMBER,
) -> TeamMembership:
    membership = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.team_id == team_id,
            TeamMembership.user_id == user_id,
        )
        .first()
    )
    if membership is None or not _role_at_least(TEAM_ROLE_RANK, membership.role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for team {team_id}",
        )
    return membership


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


def _normalize_document_filename(filename: str) -> str:
    normalized = (filename or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="filename cannot be empty.")
    if len(normalized) > 512:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="filename exceeds 512 characters.")
    return normalized


def _document_filename_key(filename: str) -> str:
    return (filename or "").strip().lower()


def _normalize_kb_name(name: str) -> str:
    normalized = (name or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base name cannot be empty.")
    if len(normalized) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base name exceeds 255 characters.")
    return normalized


def _normalize_kb_description(description: str | None) -> str | None:
    if description is None:
        return None
    normalized = description.strip()
    if len(normalized) > 2000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base description exceeds 2000 characters.")
    return normalized or None


def _compute_confidence_score(sources: list[dict[str, Any]]) -> float:
    if not sources:
        return 0.0
    raw_scores = [float(s.get("score", 0.0)) for s in sources]
    top = max(raw_scores)
    top_n = sorted(raw_scores, reverse=True)[:3]
    avg_top = sum(top_n) / max(1, len(top_n))
    top_norm = top / (top + 0.05) if top > 0 else 0.0
    avg_norm = avg_top / (avg_top + 0.05) if avg_top > 0 else 0.0
    coverage = min(1.0, len(sources) / max(1, settings.chat_context_max_sources))
    score = (0.65 * top_norm) + (0.25 * avg_norm) + (0.10 * coverage)
    return round(max(0.0, min(1.0, score)), 3)


def _chat_quality_signals(sources: list[dict[str, Any]]) -> dict[str, Any]:
    confidence = _compute_confidence_score(sources)
    threshold = max(0.0, min(1.0, settings.chat_low_confidence_threshold))
    return {
        "confidence_score": confidence,
        "low_confidence": confidence < threshold,
    }


def _faithfulness_signals(answer: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    return compute_faithfulness_signals(
        answer=answer,
        sources=sources,
        threshold=settings.chat_faithfulness_threshold,
        enabled=settings.chat_enable_faithfulness_scoring,
    )


def _source_identity(source: dict[str, Any], index: int) -> str:
    metadata = source.get("metadata") or {}
    doc_id = metadata.get("doc_id")
    if doc_id is not None:
        return f"doc:{doc_id}"
    name = metadata.get("source") or metadata.get("filename") or metadata.get("title")
    if isinstance(name, str) and name.strip():
        return f"name:{name.strip().lower()}"
    return f"idx:{index}"


def _dedupe_sources_for_chat(sources: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not settings.chat_unique_sources_per_document:
        return sources[:limit]
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, source in enumerate(sources):
        key = _source_identity(source, idx)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
        if len(deduped) >= limit:
            break
    return deduped


def _enforce_citation_format(answer: str, sources: list[dict[str, Any]]) -> str:
    return enforce_citation_format(
        answer,
        sources,
        enabled=settings.chat_enforce_citation_format,
    )


def _append_citation_legend(answer: str, sources: list[dict[str, Any]]) -> str:
    return append_citation_legend(answer, sources, legend_header="Source references")


def _queue_document_ingestion_job(
    db,
    *,
    user_id: int | None,
    kb_id: int,
    document_id: int,
    reason: str,
) -> int:
    normalized_reason = (reason or "").strip().lower()
    if normalized_reason not in VALID_INGESTION_REASONS:
        normalized_reason = IngestionJobReason.RETRY

    job = create_ingestion_job(
        db,
        document_id=document_id,
        knowledge_base_id=kb_id,
        requested_by_user_id=user_id,
        reason=normalized_reason,
    )
    db.commit()
    db.refresh(job)

    try:
        queued = ingest_document.delay(document_id, job.id)
        task_id = getattr(queued, "id", None)
        mark_ingestion_job_queued(db, job_id=job.id, celery_task_id=task_id)
        return job.id
    except Exception as queue_err:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc is not None:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(queue_err)
            db.commit()
        mark_ingestion_job_failed(
            db,
            job_id=job.id,
            error_message=str(queue_err),
            failure_stage="queue",
            record_dead_letter=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue ingestion job.",
        ) from queue_err


async def upload_document(
    user: User,
    file: UploadFile = File(...),
    kb_id: int = Query(None, description="Knowledge base ID"),
    replace_existing: bool = True,
):
    content = await file.read()
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.EDITOR)
    filename = _normalize_document_filename(file.filename or "")
    filename_key = _document_filename_key(filename)
    try:
        object_key = f"uploads/{uuid.uuid4().hex}/{filename}"
        content_hash = hashlib.sha256(content).hexdigest()
        db = SessionLocal()
        try:
            existing_by_name = (
                db.query(Document)
                .filter(
                    Document.knowledge_base_id == kb,
                    func.lower(Document.filename) == filename_key,
                )
                .order_by(Document.id.desc())
                .first()
            )
            existing_by_hash = (
                db.query(Document)
                .filter(
                    Document.knowledge_base_id == kb,
                    Document.content_hash == content_hash,
                    Document.status.in_(
                        [
                            DocumentStatus.PENDING,
                            DocumentStatus.PROCESSING,
                            DocumentStatus.INDEXED,
                            DocumentStatus.FAILED,
                        ]
                    ),
                )
                .order_by(Document.id.desc())
                .first()
            )

            if (
                existing_by_name is not None
                and existing_by_name.content_hash == content_hash
                and existing_by_name.status
                in [DocumentStatus.PENDING, DocumentStatus.PROCESSING, DocumentStatus.INDEXED, DocumentStatus.FAILED]
            ):
                log_audit_event(
                    db,
                    user_id=user.id,
                    knowledge_base_id=kb,
                    action="document.upload.deduplicated",
                    resource_type="document",
                    resource_id=str(existing_by_name.id),
                    details={"filename": filename},
                )
                db.commit()
                if existing_by_name.status == DocumentStatus.FAILED:
                    return {
                        "filename": filename,
                        "status": "failed",
                        "document_id": existing_by_name.id,
                        "deduplicated": True,
                        "message": "Identical content already exists and last ingestion failed. Use retry ingestion for this document.",
                    }
                return {
                    "filename": filename,
                    "status": "queued",
                    "document_id": existing_by_name.id,
                    "deduplicated": True,
                    "message": "Identical content already queued/indexed in this knowledge base.",
                }

            if existing_by_name is not None:
                if should_replace_existing_upload(
                    existing_hash=existing_by_name.content_hash,
                    incoming_hash=content_hash,
                    replace_existing=bool(replace_existing),
                ):
                    previous_object_key = existing_by_name.object_key
                    upload_file(
                        object_key,
                        io.BytesIO(content),
                        len(content),
                        file.content_type or "application/octet-stream",
                    )
                    existing_by_name.object_key = object_key
                    existing_by_name.content_hash = content_hash
                    existing_by_name.status = DocumentStatus.PENDING
                    existing_by_name.error_message = None
                    log_audit_event(
                        db,
                        user_id=user.id,
                        knowledge_base_id=kb,
                        action="document.upload.replaced",
                        resource_type="document",
                        resource_id=str(existing_by_name.id),
                        details={"filename": filename},
                    )
                    db.commit()
                    db.refresh(existing_by_name)
                    try:
                        delete_file(previous_object_key)
                    except Exception:
                        pass

                    job_id = _queue_document_ingestion_job(
                        db,
                        user_id=user.id,
                        kb_id=kb,
                        document_id=existing_by_name.id,
                        reason=IngestionJobReason.REPLACE,
                    )
                    return {
                        "filename": filename,
                        "status": "queued",
                        "document_id": existing_by_name.id,
                        "ingestion_job_id": job_id,
                        "replaced": True,
                        "message": "Existing document replaced and re-indexing queued.",
                    }

                log_audit_event(
                    db,
                    user_id=user.id,
                    knowledge_base_id=kb,
                    action="document.upload.name_conflict",
                    resource_type="document",
                    resource_id=str(existing_by_name.id),
                    details={"filename": filename, "replace_existing": bool(replace_existing)},
                )
                db.commit()
                return {
                    "filename": filename,
                    "status": "exists",
                    "document_id": existing_by_name.id,
                    "replace_required": True,
                    "message": "Filename already exists in this knowledge base (case-insensitive). Set replace_existing=true to replace and re-index, or rename/delete the existing document first.",
                }

            if existing_by_hash:
                log_audit_event(
                    db,
                    user_id=user.id,
                    knowledge_base_id=kb,
                    action="document.upload.deduplicated",
                    resource_type="document",
                    resource_id=str(existing_by_hash.id),
                    details={"filename": filename},
                )
                db.commit()
                if existing_by_hash.status == DocumentStatus.FAILED:
                    return {
                        "filename": filename,
                        "status": "failed",
                        "document_id": existing_by_hash.id,
                        "deduplicated": True,
                        "message": "Identical content already exists and last ingestion failed. Use retry ingestion for this document.",
                    }
                return {
                    "filename": filename,
                    "status": "queued",
                    "document_id": existing_by_hash.id,
                    "deduplicated": True,
                    "message": "Identical content already exists in this knowledge base.",
                }

            upload_file(object_key, io.BytesIO(content), len(content), file.content_type or "application/octet-stream")
            doc = Document(knowledge_base_id=kb, filename=filename, object_key=object_key, content_hash=content_hash)
            db.add(doc)
            db.flush()
            log_audit_event(
                db,
                user_id=user.id,
                knowledge_base_id=kb,
                action="document.upload.queued",
                resource_type="document",
                resource_id=str(doc.id),
                details={"filename": filename},
            )
            db.commit()
            db.refresh(doc)
            job_id = _queue_document_ingestion_job(
                db,
                user_id=user.id,
                kb_id=kb,
                document_id=doc.id,
                reason=IngestionJobReason.UPLOAD,
            )
            return {"filename": filename, "status": "queued", "document_id": doc.id, "ingestion_job_id": job_id}
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Upload pipeline unavailable: {e}",
        ) from e


async def search_documents(user: User, query: str, kb_id: int = Query(None)):
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.VIEWER)
    started = time.monotonic()
    try:
        query_variants = await build_query_variants(query=query)
        results = hybrid_retrieve(kb_id=kb, query=query, top_k=5, query_variants=query_variants)
        retrieval_ms = int((time.monotonic() - started) * 1000)
        db = SessionLocal()
        try:
            log_audit_event(
                db,
                user_id=user.id,
                knowledge_base_id=kb,
                action="search.query",
                resource_type="knowledge_base",
                resource_id=str(kb),
                details={
                    "query_text": _compact_query_text(query),
                    "result_count": len(results),
                    "zero_result": len(results) == 0,
                    "retrieval_ms": retrieval_ms,
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("Failed to persist search analytics for kb_id=%s", kb)
        finally:
            db.close()
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


def _retrieve_for_chat(
    kb_id: int,
    query: str,
    limit: int = 5,
    query_variants: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return list of {snippet, metadata} for RAG context."""
    try:
        retrieval_limit = max(limit, limit * 3) if settings.chat_unique_sources_per_document else limit
        if query_variants:
            results = hybrid_retrieve(
                kb_id=kb_id,
                query=query,
                top_k=retrieval_limit,
                query_variants=query_variants,
            )
        else:
            # Backward-compatible invocation shape (used by existing tests/mocks).
            results = hybrid_retrieve(kb_id=kb_id, query=query, top_k=retrieval_limit)
        mapped = [
            {"snippet": r.get("snippet", ""), "metadata": r.get("metadata", {}), "score": r.get("score", 0.0)}
            for r in results
        ]
        return _dedupe_sources_for_chat(mapped, limit=limit)
    except Exception as e:
        logger.exception("Chat retrieval failed for kb_id=%s", kb_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Retrieval backend unavailable: {e}",
        ) from e


def _build_chat_prompt(
    message: str,
    history: str,
    sources: list[dict[str, Any]],
) -> tuple[str, str, str, list[dict[str, Any]], dict[str, int]]:
    source_char_limit = max(120, settings.chat_context_max_chars_per_source)
    source_limit = max(1, settings.chat_context_max_sources)
    assembly = assemble_context(
        query=message,
        history=history,
        sources=sources,
        max_sources=source_limit,
        per_source_char_limit=source_char_limit,
    )
    context_blocks = assembly.context_blocks
    system = (
        "You are a grounded assistant for this RAG system. "
        "Use only the provided context blocks for factual claims; never invent details. "
        "Use conversation history only for continuity. "
        "Answer the user directly from available evidence, regardless of document type "
        "(for example PRDs, runbooks, policies, specs, tickets, or notes). "
        "If partial evidence exists, provide what is known and mark missing parts as "
        "\"Not specified in provided context.\" "
        "Do not ask for more context unless zero relevant evidence exists. "
        "Do not say \"I couldn't find\" when at least one relevant fact is available. "
        "When the question asks for lists (features, phases, requirements, steps, risks), "
        "respond in a concise structured list. "
        "For every factual bullet/sentence, append citations in the form [Source N]."
    )
    history_block = f"Conversation history:\n{history}\n\n" if history else ""
    user_prompt = f"{history_block}Context:\n\n{context_blocks}\n\nQuestion: {message}"
    return (
        system,
        user_prompt,
        context_blocks,
        assembly.sources,
        {
            "token_budget": int(assembly.token_budget),
            "token_used": int(assembly.token_used),
            "compressed_sources": int(assembly.compressed_sources),
        },
    )


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
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb,
            action="chat.query.queued",
            resource_type="chat_job",
            resource_id=job_id,
            details={"session_id": session_key, "message_length": len((message or "").strip())},
        )
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
                log_audit_event(
                    db2,
                    user_id=user.id,
                    knowledge_base_id=kb,
                    action="chat.query.queue_failed",
                    resource_type="chat_job",
                    resource_id=job_id,
                    details={"detail": str(exc)},
                )
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
        retrieval_started = time.monotonic()
        query_variants = await build_query_variants(query=message, history=history)
        retrieved_sources: list[dict[str, Any]] = _retrieve_for_chat(
            kb,
            message,
            limit=source_limit,
            query_variants=query_variants,
        )
        retrieval_ms = int((time.monotonic() - retrieval_started) * 1000)
        system, user_prompt, context_blocks, sources, context_stats = _build_chat_prompt(
            message=message,
            history=history,
            sources=retrieved_sources,
        )
        if not context_blocks:
            answer = "No relevant documents found in the selected knowledge base yet. Upload documents and try again."
            quality = _chat_quality_signals(sources=[])
            faithfulness = _faithfulness_signals(answer=answer, sources=[])
            db.add(ChatMessage(session_id=session_key, role=ChatRole.USER, content=message))
            assistant_message = ChatMessage(session_id=session_key, role=ChatRole.ASSISTANT, content=answer)
            db.add(assistant_message)
            db.flush()
            session.updated_at = datetime.utcnow()
            log_audit_event(
                db,
                user_id=user.id,
                knowledge_base_id=kb,
                action="chat.query.sync",
                resource_type="chat_session",
                resource_id=session_key,
                details={
                    "message_length": len((message or "").strip()),
                    "query_text": _compact_query_text(message),
                    "source_count": 0,
                    "zero_result": True,
                    "retrieval_ms": retrieval_ms,
                    "confidence_score": quality["confidence_score"],
                    "low_confidence": quality["low_confidence"],
                    "context_token_budget": context_stats["token_budget"],
                    "context_token_used": context_stats["token_used"],
                    "context_compressed_sources": context_stats["compressed_sources"],
                    "faithfulness_score": faithfulness["faithfulness_score"],
                    "low_faithfulness": faithfulness["low_faithfulness"],
                },
            )
            db.commit()
            return {
                "answer": answer,
                "sources": [],
                "session_id": session_key,
                "assistant_message_id": assistant_message.id,
                "citation_enforced": False,
                "context_token_budget": context_stats["token_budget"],
                "context_token_used": context_stats["token_used"],
                **quality,
                **faithfulness,
            }

        try:
            answer = await llm_generate(user_prompt, system=system)
        except Exception as e:
            detail = str(e).strip() or e.__class__.__name__
            logger.warning("LLM generation failed for kb_id=%s session_id=%s: %s", kb, session_key, detail)
            answer = _fallback_answer_from_sources(message, sources, detail)
        answer = _enforce_citation_format(answer, sources)
        answer = _append_citation_legend(answer, sources)
        quality = _chat_quality_signals(sources)
        faithfulness = _faithfulness_signals(answer=answer, sources=sources)

        db.add(ChatMessage(session_id=session_key, role=ChatRole.USER, content=message))
        assistant_message = ChatMessage(session_id=session_key, role=ChatRole.ASSISTANT, content=answer)
        db.add(assistant_message)
        db.flush()
        session.updated_at = datetime.utcnow()
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb,
            action="chat.query.sync",
            resource_type="chat_session",
            resource_id=session_key,
            details={
                "message_length": len((message or "").strip()),
                "query_text": _compact_query_text(message),
                "source_count": len(sources),
                "zero_result": len(sources) == 0,
                "retrieval_ms": retrieval_ms,
                "confidence_score": quality["confidence_score"],
                "low_confidence": quality["low_confidence"],
                "context_token_budget": context_stats["token_budget"],
                "context_token_used": context_stats["token_used"],
                "context_compressed_sources": context_stats["compressed_sources"],
                "faithfulness_score": faithfulness["faithfulness_score"],
                "low_faithfulness": faithfulness["low_faithfulness"],
            },
        )
        db.commit()
        return {
            "answer": answer,
            "sources": sources,
            "session_id": session_key,
            "assistant_message_id": assistant_message.id,
            "citation_enforced": bool(settings.chat_enforce_citation_format and sources),
            "context_token_budget": context_stats["token_budget"],
            "context_token_used": context_stats["token_used"],
            **quality,
            **faithfulness,
        }
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
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb,
            action="chat.query.stream.started",
            resource_type="chat_session",
            resource_id=session_key,
            details={"message_length": len((message or "").strip())},
        )
        db.commit()
    finally:
        db.close()

    async def event_stream():
        started_at = time.monotonic()
        retrieval_started = time.monotonic()
        retrieval_ms = 0
        source_limit = max(1, settings.chat_context_max_sources)
        sources: list[dict[str, Any]] = []
        context_stats: dict[str, int] = {
            "token_budget": 0,
            "token_used": 0,
            "compressed_sources": 0,
        }
        answer = ""
        fallback = False
        last_heartbeat = started_at

        def elapsed_ms() -> int:
            return int((time.monotonic() - started_at) * 1000)

        yield _sse("meta", {"session_id": session_key, "trace_mode": "public"})
        yield _sse("reasoning", _reasoning_event("understand", "Understanding your question.", elapsed_ms()))
        yield _sse("reasoning", _reasoning_event("retrieve", "Searching relevant knowledge base content.", elapsed_ms()))

        try:
            query_variants = await build_query_variants(query=message, history=history)
            sources = _retrieve_for_chat(
                kb,
                message,
                limit=source_limit,
                query_variants=query_variants,
            )
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
        finally:
            retrieval_ms = int((time.monotonic() - retrieval_started) * 1000)

        system = ""
        user_prompt = ""
        context_blocks = ""
        if not fallback:
            system, user_prompt, context_blocks, sources, context_stats = _build_chat_prompt(
                message=message,
                history=history,
                sources=sources,
            )

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

        answer = _enforce_citation_format(answer, sources)
        answer = _append_citation_legend(answer, sources)
        quality = _chat_quality_signals(sources)
        faithfulness = _faithfulness_signals(answer=answer, sources=sources)
        citation_enforced = bool(settings.chat_enforce_citation_format and sources)
        assistant_message_id: int | None = None

        db2 = SessionLocal()
        try:
            session = _get_or_create_chat_session(db2, user_id=user.id, kb_id=kb, session_id=session_key)
            assistant_message = ChatMessage(session_id=session_key, role=ChatRole.ASSISTANT, content=answer)
            db2.add(assistant_message)
            db2.flush()
            assistant_message_id = assistant_message.id
            session.updated_at = datetime.utcnow()
            log_audit_event(
                db2,
                user_id=user.id,
                knowledge_base_id=kb,
                action="chat.query.stream.completed",
                resource_type="chat_session",
                resource_id=session_key,
                details={
                    "query_text": _compact_query_text(message),
                    "source_count": len(sources),
                    "zero_result": len(sources) == 0,
                    "fallback": fallback,
                    "retrieval_ms": retrieval_ms,
                    "elapsed_ms": elapsed_ms(),
                    "confidence_score": quality["confidence_score"],
                    "low_confidence": quality["low_confidence"],
                    "context_token_budget": context_stats["token_budget"],
                    "context_token_used": context_stats["token_used"],
                    "context_compressed_sources": context_stats["compressed_sources"],
                    "faithfulness_score": faithfulness["faithfulness_score"],
                    "low_faithfulness": faithfulness["low_faithfulness"],
                },
            )
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
                "assistant_message_id": assistant_message_id,
                "fallback": fallback,
                "elapsed_ms": elapsed_ms(),
                "citation_enforced": citation_enforced,
                "context_token_budget": context_stats["token_budget"],
                "context_token_used": context_stats["token_used"],
                **quality,
                **faithfulness,
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
        assistant_message_id = None
        if job.status == ChatJobStatus.COMPLETED:
            row = (
                db.query(ChatMessage.id)
                .filter(
                    ChatMessage.session_id == job.session_id,
                    ChatMessage.role == ChatRole.ASSISTANT,
                )
                .order_by(desc(ChatMessage.id))
                .first()
            )
            assistant_message_id = int(row[0]) if row else None
        feedback_rating = None
        if assistant_message_id is not None:
            feedback_row = (
                db.query(ChatFeedback)
                .filter(
                    ChatFeedback.user_id == user.id,
                    ChatFeedback.chat_message_id == assistant_message_id,
                )
                .first()
            )
            if feedback_row is not None:
                feedback_rating = feedback_row.rating
        quality = _chat_quality_signals(sources)
        answer_text = job.answer or ""
        faithfulness = _faithfulness_signals(answer=answer_text, sources=sources)
        return {
            "job_id": job.id,
            "status": job.status,
            "session_id": job.session_id,
            "answer": job.answer,
            "sources": sources,
            "assistant_message_id": assistant_message_id,
            "feedback_rating": feedback_rating,
            "citation_enforced": bool(settings.chat_enforce_citation_format and sources),
            **quality,
            **faithfulness,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
    finally:
        db.close()


def submit_chat_feedback(
    user: User,
    message_id: int,
    rating: str,
    comment: str | None = None,
) -> dict[str, Any]:
    normalized_rating = _normalize_feedback_rating(rating)
    normalized_comment = (comment or "").strip()[:1000] or None

    db = SessionLocal()
    try:
        message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat message not found")
        if message.role != ChatRole.ASSISTANT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feedback is only allowed for assistant messages")

        session = db.query(ChatSession).filter(ChatSession.id == message.session_id).first()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
        if session.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat message not found")
        require_kb_access(db, user.id, session.knowledge_base_id, min_role=KnowledgeBaseRole.VIEWER)

        row = (
            db.query(ChatFeedback)
            .filter(
                ChatFeedback.user_id == user.id,
                ChatFeedback.chat_message_id == message.id,
            )
            .first()
        )
        if row is None:
            row = ChatFeedback(
                user_id=user.id,
                knowledge_base_id=session.knowledge_base_id,
                session_id=session.id,
                chat_message_id=message.id,
                rating=normalized_rating,
                comment=normalized_comment,
            )
            db.add(row)
        else:
            row.rating = normalized_rating
            row.comment = normalized_comment
            row.knowledge_base_id = session.knowledge_base_id
            row.session_id = session.id

        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=session.knowledge_base_id,
            action="chat.feedback.submit",
            resource_type="chat_message",
            resource_id=str(message.id),
            details={
                "rating": normalized_rating,
                "comment_length": len(normalized_comment or ""),
                "session_id": session.id,
            },
        )
        db.commit()
        db.refresh(row)
        return {
            "message_id": message.id,
            "session_id": session.id,
            "kb_id": session.knowledge_base_id,
            "rating": row.rating,
            "comment": row.comment,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    finally:
        db.close()


def get_kb_rag_analytics(user: User, kb_id: int, days: int | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        return build_rag_analytics_report(db, kb_id=kb_id, days=days)
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


def get_onboarding_status(user: User) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return build_onboarding_status(db, user_id=user.id)
    finally:
        db.close()


def create_onboarding_sample_kb(user: User) -> dict[str, Any]:
    sample_kb_name = "Ragnatic Starter KB"
    sample_kb_description = "Preloaded starter knowledge base for first-time onboarding."
    sample_filename = "Ragnatic-starter-guide.md"
    sample_text = (
        "# Ragnatic Starter Guide\n\n"
        "## Welcome\n"
        "This starter knowledge base helps you run your first grounded query quickly.\n\n"
        "## Suggested Questions\n"
        "- What are the first onboarding steps?\n"
        "- How do we verify retrieval quality?\n"
        "- Which endpoints are used for uploads and chat?\n\n"
        "## Validation Checklist\n"
        "1. Upload at least one document.\n"
        "2. Run search for a policy term.\n"
        "3. Ask a chat question and verify citations.\n"
    )
    content = sample_text.encode("utf-8")
    content_hash = hashlib.sha256(content).hexdigest()
    object_key = f"uploads/{uuid.uuid4().hex}/{sample_filename}"

    db = SessionLocal()
    try:
        kb = KnowledgeBase(name=sample_kb_name, description=sample_kb_description)
        db.add(kb)
        db.flush()
        db.add(
            KnowledgeBaseMembership(
                knowledge_base_id=kb.id,
                user_id=user.id,
                role=KnowledgeBaseRole.OWNER,
            )
        )
        upload_file(object_key, io.BytesIO(content), len(content), "text/markdown")
        doc = Document(
            knowledge_base_id=kb.id,
            filename=sample_filename,
            object_key=object_key,
            content_hash=content_hash,
            status=DocumentStatus.PENDING,
        )
        db.add(doc)
        db.flush()
        job_id = create_ingestion_job(
            db,
            requested_by_user_id=user.id,
            kb_id=kb.id,
            document_id=doc.id,
            reason=IngestionJobReason.UPLOAD,
        )
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb.id,
            action="onboarding.sample_kb.create",
            resource_type="knowledge_base",
            resource_id=str(kb.id),
            details={"sample_document": sample_filename, "ingestion_job_id": job_id},
        )
        db.commit()
    finally:
        db.close()

    try:
        ingest_document.delay(doc.id, content, sample_filename, object_key)
    except Exception as exc:
        db2 = SessionLocal()
        try:
            _update_doc_status(doc.id, DocumentStatus.FAILED, str(exc))
            mark_ingestion_job_failed(db2, job_id=job_id, error_message=str(exc), progress=0)
            db2.commit()
        finally:
            db2.close()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue onboarding sample ingestion job.",
        ) from exc

    return {
        "kb_id": kb.id,
        "kb_name": sample_kb_name,
        "document_id": doc.id,
        "ingestion_job_id": job_id,
        "status": "queued",
    }


def list_organizations(user: User) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Organization, OrganizationMembership.role)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == Organization.id,
            )
            .filter(OrganizationMembership.user_id == user.id)
            .order_by(Organization.created_at.asc(), Organization.id.asc())
            .all()
        )
        return [
            {
                "id": org.id,
                "name": org.name,
                "description": org.description,
                "role": role,
                "created_at": org.created_at.isoformat() if org.created_at else None,
            }
            for org, role in rows
        ]
    finally:
        db.close()


def create_organization(user: User, name: str, description: str | None = None) -> dict[str, Any]:
    org_name = _normalize_kb_name(name)
    org_description = _normalize_kb_description(description)
    db = SessionLocal()
    try:
        org = Organization(name=org_name, description=org_description)
        db.add(org)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=org.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
            )
        )
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=None,
            action="org.create",
            resource_type="organization",
            resource_id=str(org.id),
            details={"name": org_name},
        )
        db.commit()
        return {
            "id": org.id,
            "name": org.name,
            "description": org.description,
            "role": OrganizationRole.OWNER,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        }
    finally:
        db.close()


def add_organization_member(user: User, org_id: int, email: str, role: str) -> dict[str, Any]:
    target_role = _normalize_org_role(role)
    db = SessionLocal()
    try:
        _require_org_membership(db, user.id, org_id, min_role=OrganizationRole.ADMIN)
        target_user = db.query(User).filter(User.email == email.strip().lower()).first()
        if target_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{email}' not found.")

        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.user_id == target_user.id,
            )
            .first()
        )
        if membership is None:
            membership = OrganizationMembership(
                organization_id=org_id,
                user_id=target_user.id,
                role=target_role,
            )
            db.add(membership)
        else:
            membership.role = target_role
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=None,
            action="org.member.upsert",
            resource_type="organization_membership",
            resource_id=f"{org_id}:{target_user.id}",
            details={"email": target_user.email, "role": target_role},
        )
        db.commit()
        return {
            "org_id": org_id,
            "user_id": target_user.id,
            "email": target_user.email,
            "role": membership.role,
            "created_at": membership.created_at.isoformat() if membership.created_at else None,
        }
    finally:
        db.close()


def list_organization_teams(user: User, org_id: int) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        _require_org_membership(db, user.id, org_id, min_role=OrganizationRole.MEMBER)
        rows = (
            db.query(Team)
            .filter(Team.organization_id == org_id)
            .order_by(Team.created_at.asc(), Team.id.asc())
            .all()
        )
        return [
            {
                "id": team.id,
                "organization_id": team.organization_id,
                "name": team.name,
                "description": team.description,
                "created_at": team.created_at.isoformat() if team.created_at else None,
            }
            for team in rows
        ]
    finally:
        db.close()


def create_organization_team(user: User, org_id: int, name: str, description: str | None = None) -> dict[str, Any]:
    team_name = _normalize_kb_name(name)
    team_description = _normalize_kb_description(description)
    db = SessionLocal()
    try:
        _require_org_membership(db, user.id, org_id, min_role=OrganizationRole.ADMIN)
        team = Team(organization_id=org_id, name=team_name, description=team_description)
        db.add(team)
        db.flush()
        db.add(
            TeamMembership(
                team_id=team.id,
                user_id=user.id,
                role=TeamRole.MANAGER,
            )
        )
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=None,
            action="team.create",
            resource_type="team",
            resource_id=str(team.id),
            details={"organization_id": org_id, "name": team_name},
        )
        db.commit()
        return {
            "id": team.id,
            "organization_id": team.organization_id,
            "name": team.name,
            "description": team.description,
            "created_at": team.created_at.isoformat() if team.created_at else None,
        }
    finally:
        db.close()


def add_team_member(user: User, team_id: int, email: str, role: str) -> dict[str, Any]:
    target_role = _normalize_team_role(role)
    db = SessionLocal()
    try:
        team = db.query(Team).filter(Team.id == team_id).first()
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        _require_org_membership(db, user.id, team.organization_id, min_role=OrganizationRole.ADMIN)

        target_user = db.query(User).filter(User.email == email.strip().lower()).first()
        if target_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{email}' not found.")

        org_membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == team.organization_id,
                OrganizationMembership.user_id == target_user.id,
            )
            .first()
        )
        if org_membership is None:
            org_membership = OrganizationMembership(
                organization_id=team.organization_id,
                user_id=target_user.id,
                role=OrganizationRole.MEMBER,
            )
            db.add(org_membership)

        membership = (
            db.query(TeamMembership)
            .filter(
                TeamMembership.team_id == team_id,
                TeamMembership.user_id == target_user.id,
            )
            .first()
        )
        if membership is None:
            membership = TeamMembership(team_id=team_id, user_id=target_user.id, role=target_role)
            db.add(membership)
        else:
            membership.role = target_role

        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=None,
            action="team.member.upsert",
            resource_type="team_membership",
            resource_id=f"{team_id}:{target_user.id}",
            details={"email": target_user.email, "role": target_role},
        )
        db.commit()
        return {
            "team_id": team_id,
            "user_id": target_user.id,
            "email": target_user.email,
            "role": membership.role,
            "created_at": membership.created_at.isoformat() if membership.created_at else None,
        }
    finally:
        db.close()


def assign_team_kb_access(user: User, team_id: int, kb_id: int, role: str) -> dict[str, Any]:
    target_role = _assert_valid_kb_role(role)
    db = SessionLocal()
    try:
        team = db.query(Team).filter(Team.id == team_id).first()
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        _require_org_membership(db, user.id, team.organization_id, min_role=OrganizationRole.ADMIN)
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)

        row = (
            db.query(TeamKnowledgeBaseAccess)
            .filter(
                TeamKnowledgeBaseAccess.team_id == team_id,
                TeamKnowledgeBaseAccess.knowledge_base_id == kb_id,
            )
            .first()
        )
        if row is None:
            row = TeamKnowledgeBaseAccess(team_id=team_id, knowledge_base_id=kb_id, role=target_role)
            db.add(row)
        else:
            row.role = target_role

        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb_id,
            action="team.kb_access.upsert",
            resource_type="team_kb_access",
            resource_id=f"{team_id}:{kb_id}",
            details={"team_id": team_id, "role": target_role},
        )
        db.commit()
        return {
            "team_id": team_id,
            "kb_id": kb_id,
            "role": row.role,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    finally:
        db.close()


def list_kb_team_access(user: User, kb_id: int) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.VIEWER)
        rows = (
            db.query(TeamKnowledgeBaseAccess, Team)
            .join(Team, Team.id == TeamKnowledgeBaseAccess.team_id)
            .filter(TeamKnowledgeBaseAccess.knowledge_base_id == kb_id)
            .order_by(TeamKnowledgeBaseAccess.created_at.asc(), TeamKnowledgeBaseAccess.id.asc())
            .all()
        )
        return [
            {
                "team_id": access.team_id,
                "team_name": team.name,
                "organization_id": team.organization_id,
                "kb_id": access.knowledge_base_id,
                "role": access.role,
                "created_at": access.created_at.isoformat() if access.created_at else None,
            }
            for access, team in rows
        ]
    finally:
        db.close()


def get_embedding_registry(user: User, kb_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        return list_embedding_registry(db, kb_id)
    finally:
        db.close()


def start_embedding_migration_for_kb(user: User, kb_id: int, target_version: str) -> dict[str, Any]:
    version = normalize_embedding_version(target_version)
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        namespace = start_embedding_migration(
            db,
            kb_id=kb_id,
            target_version=version,
            model_name=None,
        )
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb_id,
            action="embedding.migration.start",
            resource_type="embedding_namespace",
            resource_id=str(kb_id),
            details={"target_version": version},
        )
        db.commit()

        try:
            queued = migrate_kb_embedding_namespace.delay(kb_id, version)
            task_id = getattr(queued, "id", None)
        except Exception as queue_err:
            fail_embedding_migration(
                db,
                kb_id=kb_id,
                error_message=str(queue_err),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to queue embedding migration job.",
            ) from queue_err

        return {
            "kb_id": kb_id,
            "active_version": namespace.active_version,
            "target_version": namespace.target_version,
            "migration_status": namespace.migration_status,
            "migration_progress": namespace.migration_progress,
            "task_id": task_id,
        }
    finally:
        db.close()


def create_knowledge_base(user: User, name: str, description: str | None = None) -> dict[str, Any]:
    kb_name = _normalize_kb_name(name)
    kb_description = _normalize_kb_description(description)
    db = SessionLocal()
    try:
        kb = KnowledgeBase(name=kb_name, description=kb_description)
        db.add(kb)
        db.flush()
        db.add(
            KnowledgeBaseMembership(
                knowledge_base_id=kb.id,
                user_id=user.id,
                role=KnowledgeBaseRole.OWNER,
            )
        )
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb.id,
            action="kb.create",
            resource_type="knowledge_base",
            resource_id=str(kb.id),
            details={"name": kb_name},
        )
        db.commit()
        return {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "role": KnowledgeBaseRole.OWNER,
        }
    finally:
        db.close()


def update_knowledge_base(user: User, kb_id: int, name: str | None = None, description: str | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        membership = require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if kb is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

        changed_fields: dict[str, Any] = {}
        if name is not None:
            kb.name = _normalize_kb_name(name)
            changed_fields["name"] = kb.name
        if description is not None:
            kb.description = _normalize_kb_description(description)
            changed_fields["description"] = kb.description
        if not changed_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide name and/or description to update.",
            )

        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb_id,
            action="kb.update",
            resource_type="knowledge_base",
            resource_id=str(kb_id),
            details=changed_fields,
        )
        db.commit()
        return {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "role": membership.role,
        }
    finally:
        db.close()


def delete_knowledge_base(user: User, kb_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if kb is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

        processing_doc = (
            db.query(Document)
            .filter(Document.knowledge_base_id == kb_id, Document.status == DocumentStatus.PROCESSING)
            .first()
        )
        if processing_doc is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete knowledge base while documents are processing.",
            )

        docs = db.query(Document).filter(Document.knowledge_base_id == kb_id).all()
        deleted_docs = 0
        for doc in docs:
            try:
                delete_document_chunks(kb_id=kb_id, doc_id=doc.id)
            except Exception as cleanup_err:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to remove vector chunks for document {doc.id}: {cleanup_err}",
                ) from cleanup_err
            try:
                delete_file(doc.object_key)
            except Exception as storage_err:
                logger.warning("KB delete storage cleanup skipped for document_id=%s: %s", doc.id, storage_err)
            db.delete(doc)
            deleted_docs += 1

        session_ids = [
            sid
            for (sid,) in db.query(ChatSession.id).filter(ChatSession.knowledge_base_id == kb_id).all()
        ]
        if session_ids:
            db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
        deleted_jobs = (
            db.query(ChatJob)
            .filter(ChatJob.knowledge_base_id == kb_id)
            .delete(synchronize_session=False)
        )
        deleted_sessions = (
            db.query(ChatSession)
            .filter(ChatSession.knowledge_base_id == kb_id)
            .delete(synchronize_session=False)
        )
        db.query(KnowledgeBaseMembership).filter(
            KnowledgeBaseMembership.knowledge_base_id == kb_id
        ).delete(synchronize_session=False)
        db.delete(kb)
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb_id,
            action="kb.delete",
            resource_type="knowledge_base",
            resource_id=str(kb_id),
            details={
                "name": kb.name,
                "documents_deleted": deleted_docs,
                "chat_jobs_deleted": int(deleted_jobs or 0),
                "chat_sessions_deleted": int(deleted_sessions or 0),
            },
        )
        db.commit()
    finally:
        db.close()

    try:
        delete_all_collections_for_kb(kb_id=kb_id)
    except Exception as exc:
        logger.warning("KB collection cleanup skipped for kb_id=%s: %s", kb_id, exc)
    return {"message": "Knowledge base deleted.", "kb_id": kb_id}


def list_audit_logs(user: User, kb_id: int, limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.OWNER)
        safe_limit = max(1, min(500, limit))
        q = (
            db.query(AuditLog)
            .filter(AuditLog.knowledge_base_id == kb_id)
            .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        )
        if action:
            q = q.filter(AuditLog.action == action.strip())
        rows = q.limit(safe_limit).all()
        user_ids = {row.user_id for row in rows if row.user_id is not None}
        user_by_id = {}
        if user_ids:
            user_rows = db.query(User).filter(User.id.in_(user_ids)).all()
            user_by_id = {u.id: u.email for u in user_rows}
        return [
            {
                "id": row.id,
                "kb_id": row.knowledge_base_id,
                "user_id": row.user_id,
                "user_email": user_by_id.get(row.user_id),
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "details": parse_details(row.details_json),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
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


def list_documents(user: User, kb_id: int | None = None) -> list[dict[str, Any]]:
    kb = _resolve_kb_for_user(user, kb_id, min_role=KnowledgeBaseRole.VIEWER)
    db = SessionLocal()
    try:
        docs = (
            db.query(Document)
            .filter(Document.knowledge_base_id == kb)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .all()
        )
        return [
            {
                "document_id": d.id,
                "kb_id": d.knowledge_base_id,
                "filename": d.filename,
                "status": d.status,
                "error_message": d.error_message,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    finally:
        db.close()


def list_ingestion_dead_letters(
    user: User,
    kb_id: int,
    limit: int = 100,
    resolved: bool = False,
) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.EDITOR)
        return list_dead_letters(
            db,
            knowledge_base_id=kb_id,
            limit=limit,
            resolved=resolved,
        )
    finally:
        db.close()


def retry_ingestion_dead_letter(user: User, dead_letter_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = db.query(IngestionDeadLetter).filter(IngestionDeadLetter.id == dead_letter_id).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dead-letter entry not found")

        require_kb_access(db, user.id, row.knowledge_base_id, min_role=KnowledgeBaseRole.EDITOR)
        doc = db.query(Document).filter(Document.id == row.document_id).first()
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        if doc.status == DocumentStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document is currently processing. Retry is blocked until processing finishes.",
            )

        doc.status = DocumentStatus.PENDING
        doc.error_message = None
        row.retry_count = int(row.retry_count or 0) + 1
        row.updated_at = datetime.utcnow()
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=row.knowledge_base_id,
            action="document.dlq.retry",
            resource_type="ingestion_dead_letter",
            resource_id=str(row.id),
            details={"document_id": row.document_id},
        )
        db.commit()

        job_id = _queue_document_ingestion_job(
            db,
            user_id=user.id,
            kb_id=row.knowledge_base_id,
            document_id=row.document_id,
            reason=IngestionJobReason.RETRY,
        )
        return {
            "dead_letter_id": row.id,
            "document_id": row.document_id,
            "kb_id": row.knowledge_base_id,
            "ingestion_job_id": job_id,
            "message": "Dead-letter retry queued.",
        }
    finally:
        db.close()


def get_connector_sync_cursor(user: User, kb_id: int, source_type: str, scope_key: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.EDITOR)
        row = get_connector_sync_state(
            db,
            knowledge_base_id=kb_id,
            source_type=(source_type or "").strip(),
            scope_key=(scope_key or "").strip(),
        )
        if row is None:
            return {
                "kb_id": kb_id,
                "source_type": source_type,
                "scope_key": scope_key,
                "cursor": None,
                "last_synced_at": None,
                "last_success_at": None,
                "last_error": None,
            }
        return {
            "kb_id": row.knowledge_base_id,
            "source_type": row.source_type,
            "scope_key": row.scope_key,
            "cursor": row.cursor,
            "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
            "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
            "last_error": row.last_error,
        }
    finally:
        db.close()


def upsert_connector_sync_cursor(
    user: User,
    kb_id: int,
    source_type: str,
    scope_key: str,
    cursor: str | None,
    last_synced_at: datetime | None,
    successful: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        require_kb_access(db, user.id, kb_id, min_role=KnowledgeBaseRole.EDITOR)
        row = mark_connector_sync(
            db,
            knowledge_base_id=kb_id,
            source_type=(source_type or "").strip(),
            scope_key=(scope_key or "").strip(),
            cursor=cursor,
            synced_at=last_synced_at,
            error=error,
            successful=successful,
        )
        return {
            "kb_id": row.knowledge_base_id,
            "source_type": row.source_type,
            "scope_key": row.scope_key,
            "cursor": row.cursor,
            "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
            "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
            "last_error": row.last_error,
        }
    finally:
        db.close()


def rename_document(user: User, document_id: int, filename: str) -> dict[str, Any]:
    new_filename = _normalize_document_filename(filename)
    new_filename_key = _document_filename_key(new_filename)
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        require_kb_access(db, user.id, doc.knowledge_base_id, min_role=KnowledgeBaseRole.EDITOR)

        conflict = (
            db.query(Document)
            .filter(
                Document.knowledge_base_id == doc.knowledge_base_id,
                func.lower(Document.filename) == new_filename_key,
                Document.id != doc.id,
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another document with the same filename already exists in this knowledge base.",
            )
        if doc.filename == new_filename:
            return {
                "document_id": doc.id,
                "kb_id": doc.knowledge_base_id,
                "filename": doc.filename,
                "status": doc.status,
                "message": "Filename unchanged. No re-indexing queued.",
            }
        if doc.status == DocumentStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document is currently processing. Rename is blocked until processing finishes.",
            )

        old_filename = doc.filename
        doc.filename = new_filename
        doc.status = DocumentStatus.PENDING
        doc.error_message = None
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=doc.knowledge_base_id,
            action="document.rename",
            resource_type="document",
            resource_id=str(doc.id),
            details={"from": old_filename, "to": new_filename},
        )
        db.commit()
        db.refresh(doc)

        try:
            delete_document_chunks(kb_id=doc.knowledge_base_id, doc_id=doc.id)
        except Exception as cleanup_err:
            logger.warning(
                "Rename pre-cleanup skipped for kb_id=%s document_id=%s: %s",
                doc.knowledge_base_id,
                doc.id,
                cleanup_err,
            )

        job_id = _queue_document_ingestion_job(
            db,
            user_id=user.id,
            kb_id=doc.knowledge_base_id,
            document_id=doc.id,
            reason=IngestionJobReason.REINDEX,
        )

        return {
            "document_id": doc.id,
            "kb_id": doc.knowledge_base_id,
            "filename": doc.filename,
            "status": doc.status,
            "ingestion_job_id": job_id,
            "message": "Document renamed and re-indexing queued.",
        }
    finally:
        db.close()


def retry_document_ingestion(user: User, document_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        require_kb_access(db, user.id, doc.knowledge_base_id, min_role=KnowledgeBaseRole.EDITOR)
        if doc.status == DocumentStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document is currently processing. Retry is blocked until processing finishes.",
            )
        previous_status = doc.status
        doc.status = DocumentStatus.PENDING
        doc.error_message = None
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=doc.knowledge_base_id,
            action="document.retry",
            resource_type="document",
            resource_id=str(doc.id),
            details={"filename": doc.filename, "previous_status": previous_status},
        )
        db.commit()
        job_id = _queue_document_ingestion_job(
            db,
            user_id=user.id,
            kb_id=doc.knowledge_base_id,
            document_id=doc.id,
            reason=IngestionJobReason.RETRY,
        )
        return {
            "document_id": doc.id,
            "kb_id": doc.knowledge_base_id,
            "filename": doc.filename,
            "status": doc.status,
            "ingestion_job_id": job_id,
            "message": "Document retry queued.",
        }
    finally:
        db.close()


def delete_document(user: User, document_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        require_kb_access(db, user.id, doc.knowledge_base_id, min_role=KnowledgeBaseRole.EDITOR)
        if doc.status == DocumentStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document is currently processing. Delete is blocked until processing finishes.",
            )

        try:
            delete_document_chunks(kb_id=doc.knowledge_base_id, doc_id=doc.id)
        except Exception as cleanup_err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to remove document chunks from vector store: {cleanup_err}",
            ) from cleanup_err

        delete_file(doc.object_key)

        payload = {"message": "Document deleted.", "document_id": doc.id}
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=doc.knowledge_base_id,
            action="document.delete",
            resource_type="document",
            resource_id=str(doc.id),
            details={"filename": doc.filename},
        )
        db.delete(doc)
        db.commit()
        return payload
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
        assistant_ids = [m.id for m in rows if m.role == ChatRole.ASSISTANT]
        feedback_by_message: dict[int, str] = {}
        if assistant_ids:
            feedback_rows = (
                db.query(ChatFeedback.chat_message_id, ChatFeedback.rating)
                .filter(
                    ChatFeedback.user_id == user.id,
                    ChatFeedback.chat_message_id.in_(assistant_ids),
                )
                .all()
            )
            feedback_by_message = {int(mid): rating for mid, rating in feedback_rows}
        messages = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                "feedback_rating": feedback_by_message.get(m.id),
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
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=session.knowledge_base_id,
            action="chat.session.delete",
            resource_type="chat_session",
            resource_id=session.id,
            details=None,
        )
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
            detail=f"Invalid role '{role}'. Allowed roles: owner, editor, viewer, api_user.",
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
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb_id,
            action="kb.member.upsert",
            resource_type="membership",
            resource_id=f"{kb_id}:{target_user.id}",
            details={"email": target_user.email, "role": target_role},
        )
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
        previous_role = membership.role
        membership.role = target_role
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb_id,
            action="kb.member.role_update",
            resource_type="membership",
            resource_id=f"{kb_id}:{member_user_id}",
            details={"from": previous_role, "to": target_role},
        )
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
        target_email = membership.user.email if membership.user else None
        role = membership.role
        log_audit_event(
            db,
            user_id=user.id,
            knowledge_base_id=kb_id,
            action="kb.member.remove",
            resource_type="membership",
            resource_id=f"{kb_id}:{member_user_id}",
            details={"email": target_email, "role": role},
        )
        db.delete(membership)
        db.commit()
        return {"message": "Member removed."}
    finally:
        db.close()
