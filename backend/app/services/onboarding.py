"""Onboarding status helpers for first-time workspace setup."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.document import Document, DocumentStatus, KnowledgeBaseMembership
from app.models.tenant import OrganizationMembership

ONBOARDING_CHAT_ACTIONS = {
    "chat.query.sync",
    "chat.query.stream.completed",
    "chat.query.async.completed",
}


def build_onboarding_status(db: Session, user_id: int) -> dict[str, Any]:
    org_count = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user_id)
        .count()
    )
    kb_ids = [
        kb_id
        for (kb_id,) in (
            db.query(KnowledgeBaseMembership.knowledge_base_id)
            .filter(KnowledgeBaseMembership.user_id == user_id)
            .order_by(KnowledgeBaseMembership.created_at.asc(), KnowledgeBaseMembership.id.asc())
            .all()
        )
    ]
    primary_kb_id = kb_ids[0] if kb_ids else None
    kb_count = len(set(kb_ids))

    total_documents = 0
    indexed_documents = 0
    first_query_completed = False
    if primary_kb_id is not None:
        total_documents = (
            db.query(func.count(Document.id))
            .filter(Document.knowledge_base_id == primary_kb_id)
            .scalar()
            or 0
        )
        indexed_documents = (
            db.query(func.count(Document.id))
            .filter(
                Document.knowledge_base_id == primary_kb_id,
                Document.status == DocumentStatus.INDEXED,
            )
            .scalar()
            or 0
        )
        first_query_completed = (
            db.query(AuditLog.id)
            .filter(
                AuditLog.user_id == user_id,
                AuditLog.knowledge_base_id == primary_kb_id,
                AuditLog.action.in_(tuple(ONBOARDING_CHAT_ACTIONS)),
            )
            .first()
            is not None
        )

    steps = [
        {
            "id": "create_org",
            "label": "Create organization",
            "completed": org_count > 0,
            "detail": f"{org_count} organization(s)",
            "action_path": "/members",
        },
        {
            "id": "create_kb",
            "label": "Create first knowledge base",
            "completed": kb_count > 0,
            "detail": f"{kb_count} knowledge base(s)",
            "action_path": "/members",
        },
        {
            "id": "ingest_first_doc",
            "label": "Ingest first document",
            "completed": total_documents > 0,
            "detail": f"{total_documents} uploaded document(s)",
            "action_path": "/upload",
        },
        {
            "id": "ask_first_question",
            "label": "Ask first grounded question",
            "completed": first_query_completed,
            "detail": "Chat telemetry detected" if first_query_completed else "No chat queries yet",
            "action_path": "/chat",
        },
        {
            "id": "reach_ten_docs",
            "label": "Reach 10 indexed documents",
            "completed": indexed_documents >= 10,
            "detail": f"{indexed_documents}/10 indexed",
            "action_path": "/upload",
        },
    ]
    completed = sum(1 for step in steps if step["completed"])
    progress_percent = int((completed / max(1, len(steps))) * 100)
    next_step = next((step for step in steps if not step["completed"]), None)

    return {
        "primary_kb_id": primary_kb_id,
        "organization_count": org_count,
        "knowledge_base_count": kb_count,
        "total_documents": total_documents,
        "indexed_documents": indexed_documents,
        "first_query_completed": first_query_completed,
        "progress_percent": progress_percent,
        "completed_steps": completed,
        "total_steps": len(steps),
        "all_completed": completed == len(steps),
        "next_step": next_step,
        "steps": steps,
    }
