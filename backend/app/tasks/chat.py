"""Background chat generation jobs."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
import time

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.base import SessionLocal
from app.models.chat import ChatJob, ChatJobStatus, ChatMessage, ChatRole, ChatSession
from app.services.audit import log_audit_event
from app.services.context import assemble_context
from app.services.citations import append_citation_legend, enforce_citation_format
from app.services.faithfulness import faithfulness_signals as compute_faithfulness_signals
from app.services.llm import generate as llm_generate
from app.services.query_expansion import build_query_variants_sync
from app.services.retrieval import hybrid_retrieve

logger = logging.getLogger(__name__)


def _history_for_prompt(db, session_id: str, max_messages: int = 10) -> str:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
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


def _get_or_create_chat_session(db, user_id: int, kb_id: int, session_id: str) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session is not None:
        return session
    session = ChatSession(id=session_id, user_id=user_id, knowledge_base_id=kb_id)
    db.add(session)
    db.flush()
    return session


def _retrieve_for_chat(
    kb_id: int,
    query: str,
    limit: int,
    query_variants: list[str] | None = None,
) -> list[dict]:
    retrieval_limit = max(limit, limit * 3) if settings.chat_unique_sources_per_document else limit
    rows = hybrid_retrieve(
        kb_id=kb_id,
        query=query,
        top_k=retrieval_limit,
        query_variants=query_variants,
    )
    mapped = [{"snippet": r.get("snippet", ""), "metadata": r.get("metadata", {}), "score": r.get("score", 0.0)} for r in rows]
    return _dedupe_sources_for_chat(mapped, limit=limit)


def _source_identity(source: dict, index: int) -> str:
    metadata = source.get("metadata") or {}
    doc_id = metadata.get("doc_id")
    if doc_id is not None:
        return f"doc:{doc_id}"
    name = metadata.get("source") or metadata.get("filename") or metadata.get("title")
    if isinstance(name, str) and name.strip():
        return f"name:{name.strip().lower()}"
    return f"idx:{index}"


def _dedupe_sources_for_chat(sources: list[dict], limit: int) -> list[dict]:
    if not settings.chat_unique_sources_per_document:
        return sources[:limit]
    deduped: list[dict] = []
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


def _fallback_answer_from_sources(sources: list[dict], detail: str) -> str:
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


def _enforce_citation_format(answer: str, sources: list[dict]) -> str:
    return enforce_citation_format(
        answer,
        sources,
        enabled=settings.chat_enforce_citation_format,
    )


def _append_citation_legend(answer: str, sources: list[dict]) -> str:
    return append_citation_legend(answer, sources, legend_header="Source references")


def _compact_query_text(query: str, limit: int = 240) -> str:
    normalized = (query or "").replace("\n", " ").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(1, limit - 3)] + "..."


def _compute_confidence_score(sources: list[dict]) -> float:
    if not sources:
        return 0.0
    raw_scores = [float(s.get("score", 0.0)) for s in sources]
    dense_component = 0.0
    if raw_scores:
        top = max(raw_scores)
        avg = sum(raw_scores) / len(raw_scores)
        dense_component = max(0.0, min(1.0, 0.7 * top + 0.3 * avg))
    coverage = min(1.0, len(sources) / max(1, settings.chat_context_max_sources))
    return round((0.75 * dense_component) + (0.25 * coverage), 4)


def _chat_quality_signals(sources: list[dict]) -> dict[str, float | bool]:
    confidence = _compute_confidence_score(sources)
    threshold = max(0.0, min(1.0, settings.chat_low_confidence_threshold))
    return {
        "confidence_score": confidence,
        "low_confidence": confidence < threshold,
    }


@celery_app.task(bind=True)
def process_chat_job(self, job_id: str) -> dict:
    """Execute a queued chat request and persist assistant reply."""
    db = SessionLocal()
    try:
        job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
        if job is None:
            return {"job_id": job_id, "status": "not_found"}

        job.status = ChatJobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        session = _get_or_create_chat_session(
            db=db,
            user_id=job.user_id,
            kb_id=job.knowledge_base_id,
            session_id=job.session_id,
        )
        history = _history_for_prompt(db, job.session_id, max_messages=10)

        source_limit = max(1, settings.chat_context_max_sources)
        retrieval_started = time.monotonic()
        query_variants = build_query_variants_sync(query=job.question, history=history)
        sources = _retrieve_for_chat(
            job.knowledge_base_id,
            job.question,
            limit=source_limit,
            query_variants=query_variants,
        )
        retrieval_ms = int((time.monotonic() - retrieval_started) * 1000)
        assembly = assemble_context(
            query=job.question,
            history=history,
            sources=sources,
            max_sources=source_limit,
            per_source_char_limit=max(120, settings.chat_context_max_chars_per_source),
        )
        sources = assembly.sources
        context_blocks = assembly.context_blocks

        if not context_blocks:
            answer = "No relevant documents found in the selected knowledge base yet. Upload documents and try again."
        else:
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
            user_prompt = f"{history_block}Context:\n\n{context_blocks}\n\nQuestion: {job.question}"
            try:
                answer = asyncio.run(llm_generate(user_prompt, system=system))
            except Exception as exc:
                detail = str(exc).strip() or exc.__class__.__name__
                logger.warning("Async chat LLM failed for job_id=%s: %s", job_id, detail)
                answer = _fallback_answer_from_sources(sources, detail)
            answer = _enforce_citation_format(answer, sources)
            answer = _append_citation_legend(answer, sources)

        quality = _chat_quality_signals(sources)
        faithfulness = compute_faithfulness_signals(
            answer=answer,
            sources=sources,
            threshold=settings.chat_faithfulness_threshold,
            enabled=settings.chat_enable_faithfulness_scoring,
        )

        db.add(ChatMessage(session_id=job.session_id, role=ChatRole.ASSISTANT, content=answer))
        session.updated_at = datetime.utcnow()
        job.answer = answer
        job.sources_json = json.dumps(sources)
        job.status = ChatJobStatus.COMPLETED
        job.finished_at = datetime.utcnow()
        log_audit_event(
            db,
            user_id=job.user_id,
            knowledge_base_id=job.knowledge_base_id,
            action="chat.query.async.completed",
            resource_type="chat_job",
            resource_id=job.id,
            details={
                "query_text": _compact_query_text(job.question),
                "source_count": len(sources),
                "zero_result": len(sources) == 0,
                "retrieval_ms": retrieval_ms,
                "confidence_score": quality["confidence_score"],
                "low_confidence": quality["low_confidence"],
                "faithfulness_score": faithfulness["faithfulness_score"],
                "low_faithfulness": faithfulness["low_faithfulness"],
            },
        )
        db.commit()
        return {"job_id": job_id, "status": "completed"}
    except Exception as exc:
        db.rollback()
        try:
            job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
            if job is not None:
                job.status = ChatJobStatus.FAILED
                job.error_message = str(exc)
                job.finished_at = datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
        logger.exception("Async chat job failed job_id=%s", job_id)
        return {"job_id": job_id, "status": "failed", "error": str(exc)}
    finally:
        db.close()
